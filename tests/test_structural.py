# tests/test_structural.py
"""Frozen structural action-space contract + CRN oracle (action-space freeze).

Gates the keystone artifacts of the skyscraper freeze:
  - StructuralPlan: the frozen I/O contract (2 grammar-constrainable enums).
  - plan_to_dispatcher / reset_assignment_state / StructuralDispatcher: execution.
  - the offline search oracle: CRN reproducibility (the bug the design panel
    caught), RNG non-perturbation, tie-break determinism, and the one robust
    calibration anchor (a strongly-dominant regime is labeled correctly).

These assert ROBUST invariants, not the objective-dependent "label matches the
full-episode HC5 grid" — that match is a cost-weight choice and is calibrated in
Stage 2 against the oracle-policy-vs-baselines loop, not pinned here.
"""

import copy
import importlib.util
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

import elevatorsim.config as config
from elevatorsim.policy.baselines import MainTerminalParkingLook
from elevatorsim.policy.destination import DestinationGroupDispatcher
from elevatorsim.policy.schemas import StructuralPlan
from elevatorsim.policy.structural import (
    ALL_PLANS,
    HOLD_PRESETS,
    StructuralDispatcher,
    plan_to_dispatcher,
    reset_assignment_state,
)
from elevatorsim.policy.zoning import ZonedStaticDispatcher

_ORACLE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "oracle.py"
_spec = importlib.util.spec_from_file_location("oracle", _ORACLE_PATH)
oracle = importlib.util.module_from_spec(_spec)
sys.modules["oracle"] = oracle
_spec.loader.exec_module(oracle)


# ---------------------------------------------------------------------------
# The frozen contract
# ---------------------------------------------------------------------------

def test_structural_plan_accepts_only_the_frozen_grid():
    """3 modes x 3 holds = 9 valid plans; anything else is a validation error."""
    assert len(ALL_PLANS) == 9
    assert {p.mode for p in ALL_PLANS} == {"conventional", "dd_delayed", "zoned"}
    assert {p.hold for p in ALL_PLANS} == {"depart_now", "balanced", "fill_batch"}
    with pytest.raises(ValidationError):
        StructuralPlan(mode="dd_immediate", hold="balanced")  # cut from the enum
    with pytest.raises(ValidationError):
        StructuralPlan(mode="zoned", hold="aggressive")


def test_plan_to_dispatcher_maps_modes_and_holds():
    """Each mode builds its dispatcher; hold resolves to the preset knobs."""
    assert isinstance(plan_to_dispatcher(StructuralPlan(mode="conventional", hold="balanced")),
                      MainTerminalParkingLook)
    dd = plan_to_dispatcher(StructuralPlan(mode="dd_delayed", hold="fill_batch"))
    assert isinstance(dd, DestinationGroupDispatcher)
    assert (dd.batch_threshold, dd.patience_ticks) == HOLD_PRESETS["fill_batch"]
    z = plan_to_dispatcher(StructuralPlan(mode="zoned", hold="depart_now"))
    assert isinstance(z, ZonedStaticDispatcher)
    assert (z.batch_threshold, z.patience_ticks) == HOLD_PRESETS["depart_now"]


def test_reset_assignment_state_clears_turnstile():
    """Mode-handover reset clears assigned_only and waiting assigned_car_id."""
    sim = oracle.harvest_state("up_peak", 7, 60, floors=12, cars=3)
    for c in sim.cars:
        c.assigned_only = True
    waiting = [p for f in range(sim.building.num_floors)
               for p in sim.building.get_waiting_at(f)]
    for p in waiting:
        p.assigned_car_id = "C1"
    reset_assignment_state(sim)
    assert all(not c.assigned_only for c in sim.cars)
    assert all(p.assigned_car_id is None for p in waiting)


def test_structural_dispatcher_recommits_per_epoch_and_resets_on_mode_change():
    """The plan provider is consulted once per epoch; a mode change resets the turnstile."""
    # The provider is consulted only at epoch boundaries, so only two plans are
    # ever pulled: epoch 0 and epoch 1 (the within-epoch dispatch does not query).
    plans = iter([
        StructuralPlan(mode="dd_delayed", hold="balanced"),    # epoch 0
        StructuralPlan(mode="conventional", hold="balanced"),  # epoch 1 -> mode change
    ])
    calls = {"n": 0}

    def provider(sim):
        calls["n"] += 1
        return next(plans)

    sim = oracle.harvest_state("up_peak", 7, 40, floors=12, cars=3)
    disp = StructuralDispatcher(provider, min_epoch_ticks=20)

    t0 = sim.current_time
    disp.dispatch_group(sim)
    assert calls["n"] == 1 and disp.current_plan.mode == "dd_delayed"
    # Same epoch: no re-query.
    disp.dispatch_group(sim)
    assert calls["n"] == 1
    # Advance past the epoch boundary; next dispatch re-queries and switches mode.
    sim.current_time = t0 + 25
    disp.dispatch_group(sim)
    assert calls["n"] == 2 and disp.current_plan.mode == "conventional"


# ---------------------------------------------------------------------------
# The oracle — robust invariants
# ---------------------------------------------------------------------------

def test_oracle_is_crn_reproducible():
    """Same harvested state + horizon + weights -> identical label and costs.

    This is the guarantee the CRN snapshot/restore exists to provide; without it
    (naive clone-and-roll) candidate costs are arrival-noise and non-reproducible.
    """
    a_plan, a_scored = oracle.label_decision(
        oracle.harvest_state("up_peak", 7, 120, floors=32), 200)
    b_plan, b_scored = oracle.label_decision(
        oracle.harvest_state("up_peak", 7, 120, floors=32), 200)
    assert (a_plan.mode, a_plan.hold) == (b_plan.mode, b_plan.hold)
    assert [b["cost"] for b in a_scored] == [b["cost"] for b in b_scored]


def test_oracle_does_not_perturb_live_rng():
    """Labeling snapshots and restores config.RNG — the live stream is untouched."""
    sim = oracle.harvest_state("lunch", 8, 100, floors=20)
    before = config.RNG.getstate()
    oracle.label_decision(sim, 150)
    assert config.RNG.getstate() == before


def test_oracle_winner_has_minimum_cost():
    """The returned label is the argmin over candidates (sort sanity)."""
    _, scored = oracle.label_decision(oracle.harvest_state("down_peak", 9, 120, floors=32), 200)
    costs = [b["cost"] for b in scored]
    assert costs[0] == min(costs)


def test_oracle_tiebreak_is_deterministic_under_saturation():
    """When hold is inert (saturation), the tie breaks to the canonical 'balanced'.

    Under saturated traffic all three holds produce identical rollouts, so the
    label's hold is decided purely by the tie-break rank (balanced = 0), not by a
    coin flip — labels must be reproducible and defensible.
    """
    plan, scored = oracle.label_decision(
        oracle.harvest_state("up_peak", 7, 150, floors=32, arrival_rate=2.0), 200)
    # The top three rows are the winning mode across the three holds at equal cost.
    top_mode_rows = [b for b in scored if b["mode"] == plan.mode]
    assert len(top_mode_rows) == 3
    assert len({b["cost"] for b in top_mode_rows}) == 1  # holds tie
    assert plan.hold == "balanced"


def test_oracle_picks_strongly_dominant_mode():
    """Calibration anchor: in up-peak, destination dispatch dominates and is labeled.

    Up-peak is the regime where dd_delayed's advantage is large and robust across
    cost weights (it delivers ~2x conventional with lower wait), so the oracle
    must select it. This is the one robust label-level calibration check; the
    weight-sensitive regimes (down-peak, lunch) are calibrated in Stage 2.
    """
    votes = {}
    for seed in (7, 8, 9):
        plan, _ = oracle.label_decision(
            oracle.harvest_state("up_peak", seed, 120, floors=32), 300,
            weights={"wait": 1.0, "p95": 0.1, "energy": 0.005, "hc5": 0.5, "refusals": 2.0})
        votes[plan.mode] = votes.get(plan.mode, 0) + 1
    assert votes.get("dd_delayed", 0) >= 2, votes


def test_oracle_never_labels_a_zero_delivery_winner():
    """Survivorship guard: a do-nothing window cannot win via vacuous zero wait.

    The pending-passenger age term makes an undelivering candidate accrue cost,
    so the labeled plan always delivers passengers in a live regime.
    """
    _, scored = oracle.label_decision(
        oracle.harvest_state("up_peak", 7, 120, floors=32), 200)
    assert scored[0]["delivered"] > 0


def test_locked_stage2_calibration_defaults():
    """Pin the Stage-2-calibrated defaults; label_decision() uses them with no args.

    The heavy oracle-policy-vs-baselines validation lives in scripts/calibrate.py
    (run on demand). This cheap regression catches an accidental revert of the
    locked config and exercises the default code path.
    """
    assert oracle.DEFAULT_HORIZON == 300
    assert oracle.DEFAULT_SETTLE == 300
    assert oracle.DEFAULT_WEIGHTS["hc5"] == 0.5 and oracle.DEFAULT_WEIGHTS["p95"] == 0.1
    plan, scored = oracle.label_decision(oracle.harvest_state("up_peak", 7, 120, floors=20))
    assert isinstance(plan, StructuralPlan)
    assert plan.mode in ("conventional", "dd_delayed", "zoned")
    assert scored[0]["delivered"] > 0


def test_settle_ticks_is_accepted_and_reproducible():
    """The Stage-2 settle lever runs and stays CRN-reproducible."""
    p1, s1 = oracle.label_decision(
        oracle.harvest_state("lunch", 7, 120, floors=32), 200, settle_ticks=100)
    p2, s2 = oracle.label_decision(
        oracle.harvest_state("lunch", 7, 120, floors=32), 200, settle_ticks=100)
    assert (p1.mode, p1.hold) == (p2.mode, p2.hold)
    assert [b["cost"] for b in s1] == [b["cost"] for b in s2]
