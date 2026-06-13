#!/usr/bin/env python3
# scripts/oracle.py
"""Offline search oracle for structural-dispatch labels (training-plan Stage 2).

Given a harvested decision-point state, enumerate the 9 candidate StructuralPlans
(3 modes x 3 holds), roll each forward H ticks on a clone of the state, score by
the project cost function, and return the argmin as the label. Gemma then clones
the oracle (behavior cloning) — the oracle decides, Gemini explains.

THE CRN INVARIANT (the bug the design panel caught — do not remove):
The simulator draws stochastic arrivals from the module-global ``config.RNG``,
which ``deepcopy`` does NOT clone. So naively cloning a state and rolling two
candidates gives each a DIFFERENT arrival stream — the cost difference would be
arrival noise, not action quality, silently mislabeling exactly the near-tie
decisions this project exists to capture (confirmed: two clones of one state
rolled with the SAME dispatcher diverge). The fix here is Common Random Numbers:
snapshot ``config.RNG`` state and restore it before every candidate rollout, so
all 9 candidates face the identical future and differ ONLY by their action.

Horizon discipline: H must be >= one measured round trip for the cell (RTT is
~60-200 ticks depending on height/load), or batching's stop-collapse never
materialises in the window and all candidates deliver the same count — the label
becomes noise. ``label_decision`` requires an explicit horizon; calibrate it
against the arena's full-episode winner grid before bulk labeling (the
calibration gate in tests/test_structural.py pins this).
"""

import argparse
import copy
import math
from typing import Any, Dict, List, Optional, Tuple

import elevatorsim.config as config
from elevatorsim.core.building import Building
from elevatorsim.core.car import Car
from elevatorsim.core.events import BoardingRefused
from elevatorsim.core.metrics import MetricsCollector
from elevatorsim.core.simulation import Simulation
from elevatorsim.core.traffic import TrafficGenerator
from elevatorsim.policy.baselines import MainTerminalParkingLook
from elevatorsim.policy.schemas import StructuralPlan
from elevatorsim.policy.structural import (
    ALL_PLANS, StructuralDispatcher, plan_to_dispatcher, reset_assignment_state,
)
from elevatorsim.config import seed_rng

REGIME_PROFILE = {
    "uniform": "UNIFORM", "down_peak": "DOWN_PEAK",
    "up_peak": "UP_PEAK", "lunch": "LUNCH",
}

# Cost-function weights. cost = w_wait*mean_effective_wait + w_p95*p95_tail
#   + w_energy*energy - w_hc5*hc5 + w_refusals*refusals. Lower is better.
# mean_effective_wait counts the age of STILL-WAITING passengers as well as the
# wait of delivered ones, so a do-nothing candidate accrues cost instead of
# scoring a vacuous 0 — the survivorship guard.
#
# LOCKED by the Stage-2 calibration (scripts/calibrate.py, 2026-06-12). With
# DEFAULT_HORIZON + DEFAULT_SETTLE below, the oracle POLICY (StructuralDispatcher
# driven by label_decision) beats or matches the best fixed mode on full-episode
# HC5 in EVERY regime, validated on held-out seeds AND a held-out height (48fl):
# the lunch myopia that the freeze flagged (oracle ~12% below fixed `zoned`) is
# closed (ratio 0.88 -> 1.02). See docs/training-plan.md Stage 2.
DEFAULT_WEIGHTS: Dict[str, float] = {
    "wait": 1.0,
    "p95": 0.1,
    "energy": 0.005,
    "hc5": 0.5,
    "refusals": 2.0,
}

# Locked labeling horizon and settle period (Stage-2 calibration). settle lets a
# candidate establish its mode before scoring, crediting the steady-state
# advantage of slow-starting modes (zoned) that a purely myopic window misses —
# this is the lever that closed the lunch gap. horizon=settle=300 is robust
# across heights 32-48 (a fixed pair beats per-cell RTT tuning in validation).
DEFAULT_HORIZON: int = 300
DEFAULT_SETTLE: int = 300

# Tie-break ranks (lower wins on an exact cost tie): prefer the operationally
# simpler mode, then the canonical 'balanced' hold. Makes labels deterministic
# and defensible rather than coin-flips on the measured near-ties.
_MODE_RANK = {"conventional": 0, "zoned": 1, "dd_delayed": 2}
_HOLD_RANK = {"balanced": 0, "depart_now": 1, "fill_batch": 2}


def _percentile(data: List[float], q: float) -> float:
    if not data:
        return 0.0
    s = sorted(data)
    n = len(s)
    if n == 1:
        return float(s[0])
    rank = (q / 100.0) * (n - 1)
    lo, hi = math.floor(rank), math.ceil(rank)
    if lo == hi:
        return float(s[lo])
    return float(s[lo] + (s[hi] - s[lo]) * (rank - lo))


def score_candidate(
    base_sim: Any, plan: StructuralPlan, horizon: int, weights: Dict[str, float],
    settle_ticks: int = 0,
) -> Tuple[float, Dict[str, Any]]:
    """Roll one candidate plan H ticks on a clone of ``base_sim``; return (cost, breakdown).

    The caller is responsible for the CRN snapshot/restore around this call so the
    rollout's arrivals match every sibling candidate's.

    ``settle_ticks`` (default 0 = myopic) rolls the candidate that many ticks to
    establish its mode BEFORE scoring begins, then scores the next ``horizon``
    ticks. This is the calibration lever for the measured lunch blind spot: a
    purely myopic window rewards fast-start modes (conventional) over modes whose
    advantage is steady-state (zoned), because the mode-switch transient lands
    inside the scored window. Letting a candidate settle first removes that
    transient. Partial mitigation only — full resolution is a Stage-2 task that
    jointly tunes settle, horizon, and the cost weights against the oracle-policy-
    vs-baselines validation [docs/training-plan.md Stage 2].
    """
    clone = copy.deepcopy(base_sim)
    clone.dispatcher = plan_to_dispatcher(plan)
    reset_assignment_state(clone)  # clean mode handover from the harvested state

    for _ in range(settle_ticks):
        clone.step()

    done_before = {p.passenger_id for p in clone.metrics.completed_passengers}
    energy_before = clone.metrics.total_energy
    refusals = {"n": 0}
    clone.register_listener(
        lambda e: refusals.__setitem__("n", refusals["n"] + 1)
        if isinstance(e, BoardingRefused)
        else None
    )

    for _ in range(horizon):
        clone.step()
    now = clone.current_time

    window = [
        p for p in clone.metrics.completed_passengers
        if p.passenger_id not in done_before and p.wait_time is not None
    ]
    waits = [p.wait_time for p in window]
    delivered = len(window)
    energy_window = clone.metrics.total_energy - energy_before
    pending = [
        now - p.spawn_time
        for f in range(clone.building.num_floors)
        for p in clone.building.get_waiting_at(f)
    ]
    n_considered = delivered + len(pending)
    mean_eff_wait = (sum(waits) + sum(pending)) / n_considered if n_considered else 0.0
    p95 = _percentile(waits, 95)
    hc5 = delivered / horizon * 300 if horizon else 0.0

    cost = (
        weights["wait"] * mean_eff_wait
        + weights["p95"] * p95
        + weights["energy"] * energy_window
        + weights["refusals"] * refusals["n"]
        - weights["hc5"] * hc5
    )
    breakdown = {
        "mode": plan.mode, "hold": plan.hold, "cost": round(cost, 3),
        "delivered": delivered, "pending": len(pending),
        "mean_eff_wait": round(mean_eff_wait, 2), "p95": round(p95, 2),
        "hc5": round(hc5, 2), "energy": round(energy_window, 1), "refusals": refusals["n"],
    }
    return cost, breakdown


def label_decision(
    base_sim: Any,
    horizon: Optional[int] = None,
    weights: Optional[Dict[str, float]] = None,
    settle_ticks: Optional[int] = None,
) -> Tuple[StructuralPlan, List[Dict[str, Any]]]:
    """Enumerate all 9 plans under Common Random Numbers; return (best_plan, scored).

    With no overrides, uses the LOCKED Stage-2 calibration (DEFAULT_WEIGHTS /
    DEFAULT_HORIZON / DEFAULT_SETTLE) — the config validated to make the oracle
    policy beat/match every fixed mode per regime. ``scored`` is the full
    candidate list sorted best-first, for inspection and Tier-B teacher
    prompting. The global RNG is left exactly as it was found.
    """
    weights = weights or DEFAULT_WEIGHTS
    horizon = DEFAULT_HORIZON if horizon is None else horizon
    settle_ticks = DEFAULT_SETTLE if settle_ticks is None else settle_ticks
    rng_state = config.RNG.getstate()
    scored: List[Tuple] = []
    try:
        for idx, plan in enumerate(ALL_PLANS):
            config.RNG.setstate(rng_state)  # identical future for every candidate
            cost, breakdown = score_candidate(base_sim, plan, horizon, weights, settle_ticks)
            scored.append((cost, _MODE_RANK[plan.mode], _HOLD_RANK[plan.hold], idx, plan, breakdown))
    finally:
        config.RNG.setstate(rng_state)  # restore: labeling must not advance live RNG

    scored.sort(key=lambda r: (r[0], r[1], r[2], r[3]))
    best_plan = scored[0][4]
    return best_plan, [r[5] for r in scored]


# Deterministic mode-cycling order for the "switching" warmup policy. No RNG —
# the only stochasticity in a harvested state is the (seeded) traffic, so two
# reconstructions of the same descriptor are byte-identical.
_SWITCH_CYCLE = ("conventional", "dd_delayed", "zoned")


def _build_warmup_dispatcher(warmup: str):
    """Build the policy that runs before the harvested decision point.

    A single StructuralPlan mode maps to its concrete dispatcher; the
    ``"switching"`` sentinel (WO-001) rotates conventional -> dd_delayed ->
    zoned every epoch via ``StructuralDispatcher``, so the harvest corpus covers
    the mixed-mode states a real adaptive policy produces, not just single-mode
    backlogs (the warmup-bias finding from the freeze).
    """
    if warmup == "switching":
        counter = {"i": 0}

        def provider(_sim):
            plan = StructuralPlan(
                mode=_SWITCH_CYCLE[counter["i"] % len(_SWITCH_CYCLE)], hold="balanced")
            counter["i"] += 1
            return plan

        return StructuralDispatcher(provider, min_epoch_ticks=150)
    return plan_to_dispatcher(StructuralPlan(mode=warmup, hold="balanced"))


def harvest_state(
    regime: str,
    seed: int,
    harvest_tick: int,
    *,
    floors: int = 32,
    cars: int = 8,
    capacity: int = 24,
    arrival_rate: float = 2.0,
    stop_ticks: int = 9,
    transfer_ticks: int = 1,
    warmup: str = "conventional",
    weight_limit: Optional[float] = None,
) -> Simulation:
    """Run a warmup policy to ``harvest_tick`` and return the live mid-episode sim.

    A decision point: the state a structural policy would face at an epoch
    boundary. ``warmup`` is the policy running before the decision (defaults to
    conventional — a neutral prior): a single StructuralPlan mode, or the
    ``"switching"`` sentinel (a deterministic mode-cycling policy — see
    ``_build_warmup_dispatcher``) that produces the mixed-mode backlogs an
    adaptive policy actually faces [WO-001 Stage-1 warmup sweep]. ``weight_limit``
    (kg) applies a per-car cap for refusal-curriculum cells. Reseeds the global
    RNG, so the returned sim's future is reproducible for the oracle (the CRN
    snapshot is taken inside ``label_decision``).
    """
    seed_rng(seed)
    building = Building(num_floors=floors)
    cars_list = [
        Car(f"C{i + 1}", 0, capacity=capacity, max_weight_kg=weight_limit)
        for i in range(cars)
    ]
    sim = Simulation(
        building, cars_list[0], _build_warmup_dispatcher(warmup), MetricsCollector(),
        traffic_generator=TrafficGenerator(floors, arrival_rate, REGIME_PROFILE[regime]),
        verbose=False, extra_cars=cars_list[1:],
        stop_ticks=stop_ticks, transfer_ticks=transfer_ticks,
    )
    for _ in range(harvest_tick):
        sim.step()
    return sim


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect the structural oracle on one decision point.")
    parser.add_argument("--regime", default="up_peak", choices=list(REGIME_PROFILE))
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--harvest-tick", type=int, default=120)
    parser.add_argument("--horizon", type=int, default=DEFAULT_HORIZON)
    parser.add_argument("--settle", type=int, default=DEFAULT_SETTLE)
    parser.add_argument("--floors", type=int, default=32)
    parser.add_argument("--cars", type=int, default=8)
    args = parser.parse_args(argv)

    sim = harvest_state(
        args.regime, args.seed, args.harvest_tick, floors=args.floors, cars=args.cars
    )
    best, scored = label_decision(sim, args.horizon, settle_ticks=args.settle)
    print(f"regime={args.regime} seed={args.seed} harvest_tick={args.harvest_tick} "
          f"horizon={args.horizon} settle={args.settle} floors={args.floors} cars={args.cars}")
    print(f"ORACLE LABEL: mode={best.mode} hold={best.hold}\n")
    print(f"{'rank':>4} {'mode':12} {'hold':11} {'cost':>9} {'deliv':>6} {'pend':>5} "
          f"{'mwait':>7} {'p95':>7} {'hc5':>7}")
    for i, b in enumerate(scored):
        print(f"{i:>4} {b['mode']:12} {b['hold']:11} {b['cost']:9.2f} {b['delivered']:>6} "
              f"{b['pending']:>5} {b['mean_eff_wait']:>7.1f} {b['p95']:>7.1f} {b['hc5']:>7.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
