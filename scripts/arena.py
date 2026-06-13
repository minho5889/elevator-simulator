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
from elevatorsim.core.events import BoardingRefused, DoorOpened, PassengerBoarded
from elevatorsim.core.metrics import MetricsCollector
from elevatorsim.core.simulation import Simulation
from elevatorsim.core.traffic import TrafficGenerator
from elevatorsim.policy.baselines import (
    ETACostDispatcher,
    FCFSDispatcher,
    MainTerminalParkingLook,
    NearestCallDispatcher,
)
from elevatorsim.policy.destination import DestinationGroupDispatcher
from elevatorsim.policy.heuristic import GroupHeuristicDispatcher
from elevatorsim.policy.zoning import ZonedStaticDispatcher
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
    # LOOK + main-terminal parking: the conventional-control reference (gate S2)
    "look_park": MainTerminalParkingLook,
    # Destination dispatch — assignment timing held explicit (gates S3/S5)
    "dd_delayed": lambda: DestinationGroupDispatcher("delayed"),
    "dd_immediate": lambda: DestinationGroupDispatcher("immediate"),
    # Ablation: same holding/turnstile/routing, FIFO batches, no destination
    # info — dd-vs-shuttle isolates the kiosk's information channel (gate S3)
    "shuttle": lambda: DestinationGroupDispatcher("delayed", batch_style="fifo"),
    # Static zoning: one contiguous zone per car, signage via assigned boarding
    # — the classical conventional up-peak strategy (P5 gate)
    "zoned": ZonedStaticDispatcher,
}


def _make_dispatcher(name: str) -> Any:
    """Build a dispatcher by name. Learned policies are imported lazily so the
    arena runs headless without an LLM provider configured."""
    if name in DISPATCHERS:
        return DISPATCHERS[name]()
    if name.startswith("structural"):
        # The learned structural policy (P7). `structural` uses the configured
        # Ollama model (set OLLAMA_MODEL_ID=elevator-gemma for the fine-tuned
        # model at Stage 5); `structural:<model_id>` overrides it inline. Lazy
        # import — pulls in the Ollama client the baseline ladder doesn't need.
        from elevatorsim.policy.structural_agent import make_structural_dispatcher

        model_id = name.split(":", 1)[1] if ":" in name else None
        return make_structural_dispatcher(model_id=model_id)
    if name in ("agent", "gemma", "elevator-gemma"):
        # Legacy mid-rise agent (GroupDispatchDecision). Superseded by the
        # `structural` rung for skyscraper scale; kept for Tier-2 comparisons.
        from elevatorsim.policy.agentic import DispatcherAgent

        return DispatcherAgent()
    raise ValueError(f"Unknown dispatcher: {name!r} (known: {', '.join(DISPATCHERS)} | structural[:model])")


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


# ---------------------------------------------------------------------------
# Analytic up-peak sizing chain [Report §6] — the published reference arithmetic
# the simulator instrument is calibrated against (gate S2, skyscraper-plan.md).
# N is the number of floors ABOVE the main terminal; P is passengers per trip.
# ---------------------------------------------------------------------------

def expected_stops(n_upper: int, p: float) -> float:
    """Expected stops per up-peak round trip: S = N · (1 − (1 − 1/N)^P)."""
    return n_upper * (1.0 - (1.0 - 1.0 / n_upper) ** p)


def highest_reversal(n_upper: int, p: float) -> float:
    """Expected highest reversal floor: H = N − Σ_{i=1}^{N−1} (i/N)^P."""
    return n_upper - sum((i / n_upper) ** p for i in range(1, n_upper))


def analytic_rtt(n_upper: int, p: float, t_v: float, t_s: float, t_p: float) -> float:
    """Round-trip time: RTT ≈ 2·H·t_v + (S + 1)·t_s + 2·P·t_p."""
    return (
        2.0 * highest_reversal(n_upper, p) * t_v
        + (expected_stops(n_upper, p) + 1.0) * t_s
        + 2.0 * p * t_p
    )


def hc5_from_interval(p: float, uppint: float) -> float:
    """5-minute handling capacity from the up-peak interval: HC5 = 300·P / UPPINT."""
    return 300.0 * p / uppint if uppint > 0 else 0.0


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
    capacity: int = 8,
    population: int = 0,
) -> Dict[str, Any]:
    """Run a single deterministic episode and return its metrics panel.

    Tier-3 "skyscraper" time costs are opt-in [docs/skyscraper-plan.md P1]:
        stop_ticks      t_s — door/stop penalty per stop (legacy 2)
        transfer_ticks  t_p — per-passenger board/alight time (legacy 0 = instant)
        floor_ticks     t_v — ticks to traverse one floor; car speed = 1/floor_ticks
                              (legacy 1.0 -> speed 1.0, one floor per tick)
    Defaults reproduce the Tier 0-2 fixed-tick contract exactly.

    ``capacity`` is per-car headcount; ``population`` (optional) enables the
    %POP sizing metric: pct_pop = HC5 / population [Report §5.3].
    """
    if regime not in REGIMES:
        raise ValueError(f"Unknown regime: {regime!r} (known: {', '.join(REGIMES)})")

    # Reset the global RNG so traffic is identical across dispatchers at this seed.
    seed_rng(seed)

    speed = 1.0 / floor_ticks
    building = Building(num_floors=floors)
    primary = Car(car_id="C1", initial_floor=0, speed=speed, capacity=capacity,
                  max_weight_kg=weight_limit)
    extra = [
        Car(car_id=f"C{i + 1}", initial_floor=0, speed=speed, capacity=capacity,
            max_weight_kg=weight_limit)
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

    # Event-stream instrumentation: weight refusals (G3) and per-car lobby
    # round-trip cycles for RTT/UPPINT [Report §6]. A cycle is lobby door-open
    # to lobby door-open, counted only if the car visited an upper floor in
    # between; standing time at the lobby is included, which is what makes
    # measured UPPINT the actual departure interval.
    refusals = {"n": 0}
    lobby_state = {c.car_id: {"last": None, "upper": False} for c in sim.cars}
    rtt_cycles: List[int] = []
    lobby_sessions = {"sessions": 0, "boards": 0}

    def _observe(e: Any) -> None:
        if isinstance(e, BoardingRefused):
            refusals["n"] += 1
        elif isinstance(e, DoorOpened):
            st = lobby_state.get(e.car_id)
            if st is None:
                return
            if e.floor == 0:
                if st["last"] is not None and st["upper"]:
                    rtt_cycles.append(e.time - st["last"])
                st["last"] = e.time
                st["upper"] = False
                lobby_sessions["sessions"] += 1
            else:
                st["upper"] = True
        elif isinstance(e, PassengerBoarded) and e.floor == 0:
            lobby_sessions["boards"] += 1

    sim.register_listener(_observe)

    sim.run_until_complete(max_ticks=ticks)

    completed = metrics.completed_passengers
    waits = [p.wait_time for p in completed if p.wait_time is not None]
    totals = [p.total_time for p in completed if p.total_time is not None]

    spawned = len(metrics.all_passengers)
    delivered = len(completed)
    n_ref = refusals["n"]
    hc5 = round(delivered / ticks * 300, 3) if ticks else 0.0
    rtt_mean = round(sum(rtt_cycles) / len(rtt_cycles), 3) if rtt_cycles else None
    n_sessions = lobby_sessions["sessions"]

    return {
        "dispatcher": dispatcher_name,
        "regime": regime,
        "seed": seed,
        "floors": floors,
        "cars": cars,
        "capacity": capacity,
        "weight_limit": weight_limit,
        "arrival_rate": arrival_rate,
        "ticks": ticks,
        "stop_ticks": stop_ticks,
        "transfer_ticks": transfer_ticks,
        "floor_ticks": floor_ticks,
        # Gate S5: assignment timing is logged on every destination-dispatch
        # run so interface constraints are never conflated with algorithm
        # quality [Report §8, Sorsa 2019]. None for conventional dispatchers.
        "dd_assignment": getattr(dispatcher, "assignment_mode", None),
        # Wait-quality metrics are None (not 0.0) when nobody completed —
        # a zero here is survivorship bias, not service quality.
        "awt": round(sum(waits) / len(waits), 3) if waits else None,
        "attd": round(sum(totals) / len(totals), 3) if totals else None,
        "sq_wait": round(sum(w * w for w in waits) / len(waits), 3) if waits else None,
        "p95_wait": round(percentile(waits, 95), 3) if waits else None,
        "max_wait": max(waits) if waits else None,
        "energy": round(metrics.total_energy, 2),
        "hc5": hc5,
        "pct_pop": round(hc5 / population * 100, 2) if population else None,
        "rtt_mean": rtt_mean,
        "uppint": round(rtt_mean / cars, 3) if rtt_mean is not None else None,
        "p_bar": round(lobby_sessions["boards"] / n_sessions, 3) if n_sessions else None,
        "delivered": delivered,
        "spawned": spawned,
        "completion": round(delivered / spawned, 3) if spawned else 0.0,
        "refusals": n_ref,
        "ref_per_del": round(n_ref / delivered, 4) if delivered else 0.0,
    }


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
