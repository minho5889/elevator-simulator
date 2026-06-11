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
    hc5_equiv    handling capacity: passengers delivered per 50 ticks
    delivered    passengers completed
    spawned      passengers that arrived
    completion   delivered / spawned — guards against AWT survivorship bias
    refusals     weight-limit boarding refusals (G3 lever)
    ref_per_del  refusals per delivered passenger

A single blended average across regimes is disqualifying [Report §8]; the ladder
summary therefore reports each regime separately, never pooled.

Usage (from repo root):
    uv run python scripts/arena.py
    uv run python scripts/arena.py --regimes lunch --cars 2 --weight-limit 200
    uv run python scripts/arena.py --dispatchers look,eta --seeds 40 --out arena.json
"""

import argparse
import json
import math
import sys
from typing import Any, Callable, Dict, List, Optional

from elevatorsim.core.building import Building
from elevatorsim.core.car import Car
from elevatorsim.core.events import BoardingRefused
from elevatorsim.core.metrics import MetricsCollector
from elevatorsim.core.simulation import Simulation
from elevatorsim.core.traffic import TrafficGenerator
from elevatorsim.policy.baselines import (
    ETACostDispatcher,
    FCFSDispatcher,
    NearestCallDispatcher,
)
from elevatorsim.policy.heuristic import GroupHeuristicDispatcher
from elevatorsim.config import seed_rng


# Regime name -> TrafficGenerator profile. Lunch is the bidirectional regime
# added for this plan (traffic.py); the others are the engine's originals.
REGIMES: Dict[str, str] = {
    "uniform": "UNIFORM",
    "down_peak": "DOWN_PEAK",
    "up_peak": "UP_PEAK",
    "lunch": "LUNCH",
}

# Dispatcher name -> zero-arg factory (fresh instance per run, no cross-seed state).
# Ordered weakest -> strongest so the ladder reads top to bottom.
DISPATCHERS: Dict[str, Callable[[], Any]] = {
    "fcfs": FCFSDispatcher,
    "nearest": NearestCallDispatcher,
    "eta": ETACostDispatcher,
    "look": GroupHeuristicDispatcher,
}


def _make_dispatcher(name: str) -> Any:
    """Build a dispatcher by name. Learned policies are imported lazily so the
    arena runs headless without an LLM provider configured."""
    if name in DISPATCHERS:
        return DISPATCHERS[name]()
    if name in ("agent", "gemma", "elevator-gemma"):
        # Deferred: the learned policy is wired here once a fine-tuned model
        # exists (training-plan Stage 5). Import is lazy because it pulls in the
        # Strands/LLM stack, which the baseline ladder does not need.
        from elevatorsim.policy.agentic import DispatcherAgent

        return DispatcherAgent()
    raise ValueError(f"Unknown dispatcher: {name!r} (known: {', '.join(DISPATCHERS)})")


def percentile(data: List[float], q: float) -> float:
    """Linear-interpolation percentile (numpy default method), pure-Python.

    numpy isn't a project dependency, so this avoids one. ``q`` in [0, 100].
    """
    if not data:
        return 0.0
    s = sorted(data)
    n = len(s)
    if n == 1:
        return float(s[0])
    rank = (q / 100.0) * (n - 1)
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return float(s[lo])
    return float(s[lo] + (s[hi] - s[lo]) * (rank - lo))


def run_one(
    dispatcher_name: str,
    regime: str,
    seed: int,
    *,
    floors: int = 5,
    cars: int = 1,
    weight_limit: Optional[float] = None,
    arrival_rate: float = 0.3,
    ticks: int = 200,
    stop_ticks: int = 2,
    transfer_ticks: int = 0,
    floor_ticks: float = 1.0,
) -> Dict[str, Any]:
    """Run a single deterministic episode and return its metrics panel.

    Tier-3 "skyscraper" time costs are opt-in [docs/skyscraper-plan.md P1]:
        stop_ticks      t_s — door/stop penalty per stop (legacy 2)
        transfer_ticks  t_p — per-passenger board/alight time (legacy 0 = instant)
        floor_ticks     t_v — ticks to traverse one floor; car speed = 1/floor_ticks
                              (legacy 1.0 -> speed 1.0, one floor per tick)
    Defaults reproduce the Tier 0-2 fixed-tick contract exactly.
    """
    if regime not in REGIMES:
        raise ValueError(f"Unknown regime: {regime!r} (known: {', '.join(REGIMES)})")

    # Reset the global RNG so traffic is identical across dispatchers at this seed.
    seed_rng(seed)

    speed = 1.0 / floor_ticks
    building = Building(num_floors=floors)
    primary = Car(car_id="C1", initial_floor=0, speed=speed, max_weight_kg=weight_limit)
    extra = [
        Car(car_id=f"C{i + 1}", initial_floor=0, speed=speed, max_weight_kg=weight_limit)
        for i in range(1, cars)
    ]
    dispatcher = _make_dispatcher(dispatcher_name)
    metrics = MetricsCollector()
    traffic = TrafficGenerator(
        num_floors=floors, arrival_rate=arrival_rate, profile=REGIMES[regime]
    )

    sim = Simulation(
        building,
        primary,
        dispatcher,
        metrics,
        traffic_generator=traffic,
        verbose=False,
        extra_cars=extra or None,
        stop_ticks=stop_ticks,
        transfer_ticks=transfer_ticks,
    )

    # Count weight-limit refusals straight off the event stream (G3 lever).
    refusals = {"n": 0}
    sim.register_listener(
        lambda e: refusals.__setitem__("n", refusals["n"] + 1)
        if isinstance(e, BoardingRefused)
        else None
    )

    sim.run_until_complete(max_ticks=ticks)

    completed = metrics.completed_passengers
    waits = [p.wait_time for p in completed if p.wait_time is not None]
    totals = [p.total_time for p in completed if p.total_time is not None]

    spawned = len(metrics.all_passengers)
    delivered = len(completed)
    n_ref = refusals["n"]

    return {
        "dispatcher": dispatcher_name,
        "regime": regime,
        "seed": seed,
        "floors": floors,
        "cars": cars,
        "weight_limit": weight_limit,
        "arrival_rate": arrival_rate,
        "ticks": ticks,
        "stop_ticks": stop_ticks,
        "transfer_ticks": transfer_ticks,
        "floor_ticks": floor_ticks,
        "awt": round(sum(waits) / len(waits), 3) if waits else 0.0,
        "attd": round(sum(totals) / len(totals), 3) if totals else 0.0,
        "sq_wait": round(sum(w * w for w in waits) / len(waits), 3) if waits else 0.0,
        "p95_wait": round(percentile(waits, 95), 3),
        "max_wait": max(waits) if waits else 0,
        "energy": round(metrics.total_energy, 2),
        "hc5_equiv": round(delivered / ticks * 50, 3) if ticks else 0.0,
        "delivered": delivered,
        "spawned": spawned,
        "completion": round(delivered / spawned, 3) if spawned else 0.0,
        "refusals": n_ref,
        "ref_per_del": round(n_ref / delivered, 4) if delivered else 0.0,
    }


# Metrics where a higher value is better (everything else: lower is better).
_HIGHER_BETTER = {"hc5_equiv", "delivered", "completion"}
# Metrics shown in the aggregate ladder table, in column order.
_AGG_KEYS = ["awt", "p95_wait", "sq_wait", "attd", "energy", "completion", "ref_per_del"]


def run_cell(
    dispatcher_name: str,
    regime: str,
    seeds: List[int],
    **kwargs: Any,
) -> Dict[str, Any]:
    """Run a dispatcher over a seed list for one regime; return per-run + means."""
    runs = [run_one(dispatcher_name, regime, s, **kwargs) for s in seeds]
    means = {
        k: round(sum(r[k] for r in runs) / len(runs), 3)
        for k in (
            "awt", "attd", "sq_wait", "p95_wait", "max_wait", "energy",
            "hc5_equiv", "delivered", "spawned", "completion", "refusals", "ref_per_del",
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


def _fmt(value: float, key: str, best: bool) -> str:
    star = "*" if best else " "
    return f"{value:>9.3f}{star}"


def print_ladder(cells: List[Dict[str, Any]], regimes: List[str], dispatchers: List[str]) -> None:
    """Print one table per regime; '*' marks the best dispatcher per metric."""
    by_key = {(c["dispatcher"], c["regime"]): c for c in cells}

    for regime in regimes:
        print(f"\n=== regime: {regime} " + "=" * (60 - len(regime)))
        header = "dispatcher  " + "".join(f"{k:>10}" for k in _AGG_KEYS)
        print(header)
        print("-" * len(header))

        # Find the best value per metric column across dispatchers.
        best_val: Dict[str, float] = {}
        for key in _AGG_KEYS:
            vals = [
                by_key[(d, regime)]["mean"][key]
                for d in dispatchers
                if (d, regime) in by_key
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
                row += _fmt(v, key, best=math.isclose(v, best_val.get(key, v)))
            print(row)
    print("\n(* = best in column; lower is better except hc5_equiv/delivered/completion)")


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
                        help="t_v: ticks to traverse one floor; car speed = 1/floor_ticks")
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
                floor_ticks=args.floor_ticks,
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
