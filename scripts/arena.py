#!/usr/bin/env python3
# scripts/arena.py
"""Headless evaluation arena for elevator dispatchers (training-plan Stage 0).

Runs a dispatcher across a grid of (regime x floors x cars x weight-limit x seed)
cells and reports the full report-metrics panel per run, so labels, data filters,
and release gates all score against the same instrument [docs/training-plan.md
Stage 0]. Every later stage of the fine-tuning plan depends on this; building it
first means we never train or gate blind.

Metrics logged for every run [Report §8 metrics discipline]:
    AWT          average waiting time (spawn -> board), over completed passengers
    ATTD         average time-to-destination (spawn -> arrive)
    sq_wait      mean squared wait — penalises the tail, where greedy fails
    p95_wait     95th-percentile wait — the starvation gate (G2)
    max_wait     worst single wait — hard starvation signal
    energy       simulator energy units (moves + motor starts + door cycles)
    hc5          5-minute handling capacity: delivered per 300 ticks (1 tick ≈ 1 s)
    pct_pop      HC5 as % of building population (when --population given) [§5.3]
    rtt_mean     measured per-car round trip: lobby door-open to lobby door-open,
                 counting only cycles that visited an upper floor [§6]
    uppint       up-peak interval = rtt_mean / cars [§6]
    p_bar        mean passengers boarded per lobby door session (observed P)
    delivered    passengers completed
    spawned      passengers that arrived
    completion   delivered / spawned — conditions every other number
    refusals     weight-limit boarding refusals (G3 lever)
    ref_per_del  refusals per delivered passenger

Survivorship discipline: wait-quality metrics over completed passengers are
uninterpretable when almost nobody completes. Runs with zero deliveries report
None (printed as —), and best-in-column stars are only awarded to dispatchers
whose completion is within 90% of the regime's best [Report §8; the Denning
starvation trap]. A single blended average across regimes is disqualifying
[Report §8]; the ladder reports each regime separately, never pooled.

The reusable engine (the regime/dispatcher catalog, single-run scorer, and
analytic sizing chain) now lives in the importable ``elevatorsim.arena`` package
so the web server can share it; this module re-exports it and keeps the CLI,
the ladder table, and the survivorship-gated star logic.

Usage (from repo root):
    uv run python scripts/arena.py
    uv run python scripts/arena.py --regimes lunch --cars 2 --weight-limit 200
    uv run python scripts/arena.py --dispatchers look,eta --seeds 40 --out arena.json
"""

import argparse
import json
import math
import sys
from typing import Any, Dict, List, Optional

# The engine was lifted into the importable arena package; re-export the names
# the CLI, the existing tests, and any callers expect from this module.
from elevatorsim.arena.registry import (  # noqa: F401
    DISPATCHERS,
    REGIMES,
    _make_dispatcher,
    make_dispatcher,
)
from elevatorsim.arena.run import (  # noqa: F401
    analytic_rtt,
    expected_stops,
    hc5_from_interval,
    highest_reversal,
    percentile,
    run_one,
)


# Metrics where a higher value is better (everything else: lower is better).
_HIGHER_BETTER = {"hc5", "delivered", "completion", "pct_pop", "p_bar"}
# Throughput metrics that self-condition (a starving policy scores badly on
# them by construction) — every OTHER metric is gameable by delivering nobody,
# so stars there require completion eligibility.
_SELF_CONDITIONING = {"hc5", "delivered", "completion", "pct_pop"}
# Metrics shown in the aggregate ladder table, in column order.
_AGG_KEYS = ["awt", "p95_wait", "attd", "hc5", "energy", "completion", "ref_per_del"]


def _mean(values: List[Any]) -> Optional[float]:
    """Mean over non-None values; None if no run produced the metric."""
    present = [v for v in values if v is not None]
    return round(sum(present) / len(present), 3) if present else None


def star_eligible(completions: Dict[str, float], threshold: float = 0.9) -> set:
    """Dispatchers eligible for best-in-column stars on gameable metrics.

    A policy can post vacuously good waits/energy over a handful of survivors
    while abandoning the rest (the §8 survivorship trap — observed live when a
    deliver-3% policy starred 'best AWT'). Stars on non-throughput metrics are
    restricted to dispatchers within ``threshold`` of the regime's best
    completion rate.
    """
    if not completions:
        return set()
    best = max(completions.values())
    if best <= 0:
        return set()
    return {d for d, c in completions.items() if c >= threshold * best}


def run_cell(
    dispatcher_name: str,
    regime: str,
    seeds: List[int],
    **kwargs: Any,
) -> Dict[str, Any]:
    """Run a dispatcher over a seed list for one regime; return per-run + means."""
    runs = [run_one(dispatcher_name, regime, s, **kwargs) for s in seeds]
    means = {
        k: _mean([r[k] for r in runs])
        for k in (
            "awt", "attd", "sq_wait", "p95_wait", "max_wait", "energy",
            "hc5", "pct_pop", "rtt_mean", "uppint", "p_bar",
            "delivered", "spawned", "completion", "refusals", "ref_per_del",
        )
    }
    return {
        "dispatcher": dispatcher_name,
        "regime": regime,
        "seeds": seeds,
        "mean": means,
        "runs": runs,
    }


def _parse_seeds(spec: str, count: int, base: int) -> List[int]:
    """Either an explicit comma list ('1,2,3') or ``count`` seeds from ``base``."""
    spec = spec.strip()
    if spec:
        return [int(x) for x in spec.split(",") if x.strip()]
    return list(range(base, base + count))


def _fmt(value: Optional[float], best: bool) -> str:
    if value is None:
        return f"{'—':>9} "
    star = "*" if best else " "
    return f"{value:>9.3f}{star}"


def print_ladder(cells: List[Dict[str, Any]], regimes: List[str], dispatchers: List[str]) -> None:
    """Print one table per regime; '*' marks the best eligible dispatcher per metric."""
    by_key = {(c["dispatcher"], c["regime"]): c for c in cells}

    for regime in regimes:
        print(f"\n=== regime: {regime} " + "=" * (60 - len(regime)))
        header = "dispatcher  " + "".join(f"{k:>10}" for k in _AGG_KEYS)
        print(header)
        print("-" * len(header))

        completions = {
            d: by_key[(d, regime)]["mean"]["completion"] or 0.0
            for d in dispatchers
            if (d, regime) in by_key
        }
        eligible = star_eligible(completions)

        # Best value per column — gameable metrics compete among eligible only.
        best_val: Dict[str, float] = {}
        for key in _AGG_KEYS:
            pool = dispatchers if key in _SELF_CONDITIONING else [
                d for d in dispatchers if d in eligible
            ]
            vals = [
                by_key[(d, regime)]["mean"][key]
                for d in pool
                if (d, regime) in by_key and by_key[(d, regime)]["mean"][key] is not None
            ]
            if not vals:
                continue
            best_val[key] = max(vals) if key in _HIGHER_BETTER else min(vals)

        for d in dispatchers:
            cell = by_key.get((d, regime))
            if not cell:
                continue
            row = f"{d:<12}"
            for key in _AGG_KEYS:
                v = cell["mean"][key]
                can_star = (key in _SELF_CONDITIONING or d in eligible) and v is not None
                row += _fmt(v, best=can_star and math.isclose(v, best_val.get(key, v)))
            print(row)
    print(
        "\n(* = best in column among dispatchers with completion >= 90% of the"
        "\n regime's best; lower is better except hc5/completion; — = no data)"
    )


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Elevator dispatcher evaluation arena.")
    parser.add_argument("--dispatchers", default="fcfs,nearest,eta,look",
                        help="comma list (known: %s)" % ", ".join(DISPATCHERS))
    parser.add_argument("--regimes", default="uniform,down_peak,up_peak,lunch",
                        help="comma list (known: %s)" % ", ".join(REGIMES))
    parser.add_argument("--floors", type=int, default=5)
    parser.add_argument("--cars", type=int, default=1)
    parser.add_argument("--weight-limit", default="none",
                        help="kg weight cap per car, or 'none'")
    parser.add_argument("--arrival-rate", type=float, default=0.3)
    parser.add_argument("--ticks", type=int, default=200)
    parser.add_argument("--stop-ticks", type=int, default=2,
                        help="t_s: door/stop penalty per stop (Tier-3 time-cost model)")
    parser.add_argument("--transfer-ticks", type=int, default=0,
                        help="t_p: per-passenger board/alight ticks (0 = legacy instant boarding)")
    parser.add_argument("--floor-ticks", type=float, default=1.0,
                        help="t_v: ticks to traverse one floor; car speed = 1/floor_ticks "
                             "(0.25 = express, 4 floors/tick)")
    parser.add_argument("--capacity", type=int, default=8,
                        help="per-car passenger headcount")
    parser.add_argument("--population", type=int, default=0,
                        help="building population for the %%POP sizing metric "
                             "(0 = off) [Report §5.3]")
    parser.add_argument("--seeds", default="",
                        help="explicit comma list of seeds; overrides --num-seeds")
    parser.add_argument("--num-seeds", type=int, default=20)
    parser.add_argument("--seed-base", type=int, default=1000)
    parser.add_argument("--out", default="", help="write full results JSON to this path")
    args = parser.parse_args(argv)

    dispatchers = [d.strip() for d in args.dispatchers.split(",") if d.strip()]
    regimes = [r.strip() for r in args.regimes.split(",") if r.strip()]
    weight_limit = None if args.weight_limit.lower() in ("none", "") else float(args.weight_limit)
    seeds = _parse_seeds(args.seeds, args.num_seeds, args.seed_base)

    print(
        f"arena: {len(dispatchers)} dispatchers x {len(regimes)} regimes x {len(seeds)} seeds "
        f"| floors={args.floors} cars={args.cars} weight_limit={weight_limit} "
        f"arrival_rate={args.arrival_rate} ticks={args.ticks}"
    )

    cells: List[Dict[str, Any]] = []
    for regime in regimes:
        for d in dispatchers:
            cell = run_cell(
                d, regime, seeds,
                floors=args.floors, cars=args.cars, weight_limit=weight_limit,
                arrival_rate=args.arrival_rate, ticks=args.ticks,
                stop_ticks=args.stop_ticks, transfer_ticks=args.transfer_ticks,
                floor_ticks=args.floor_ticks, capacity=args.capacity,
                population=args.population,
            )
            cells.append(cell)

    print_ladder(cells, regimes, dispatchers)

    if args.out:
        payload = {
            "config": {
                "dispatchers": dispatchers, "regimes": regimes, "seeds": seeds,
                "floors": args.floors, "cars": args.cars, "weight_limit": weight_limit,
                "arrival_rate": args.arrival_rate, "ticks": args.ticks,
            },
            "cells": cells,
        }
        with open(args.out, "w") as fh:
            json.dump(payload, fh, indent=2)
        print(f"\nwrote {args.out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
