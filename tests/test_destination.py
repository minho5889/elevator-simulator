# tests/test_destination.py
"""Destination dispatch (P4): turnstile boarding, batching, and gates S3/S5.

Gate cell: the Report §6 reference building (19 floors above terminal, 8 cars,
capacity 24) at super-saturated demand (2 spawns/tick = 600 per 5 min), Tier-3
time costs t_v=1 / t_s=9 / t_p=1 — the same calibrated configuration that
reproduces the KONE 12.0%-pop conventional anchor (gate S2).
"""

import importlib.util
import random
import sys
from pathlib import Path

import pytest

from elevatorsim.core.building import Building
from elevatorsim.core.car import Car
from elevatorsim.core.metrics import MetricsCollector
from elevatorsim.core.passenger import Passenger
from elevatorsim.core.simulation import Simulation
from elevatorsim.core.traffic import TrafficGenerator
from elevatorsim.policy.destination import DestinationGroupDispatcher
from elevatorsim.config import seed_rng

_ARENA_PATH = Path(__file__).resolve().parents[1] / "scripts" / "arena.py"
_spec = importlib.util.spec_from_file_location("arena_dd", _ARENA_PATH)
arena = importlib.util.module_from_spec(_spec)
sys.modules["arena_dd"] = arena
_spec.loader.exec_module(arena)

CELL = dict(floors=20, cars=8, capacity=24, arrival_rate=2.0, ticks=900,
            stop_ticks=9, transfer_ticks=1, population=1900)
SEEDS = (7, 8)


def _mean_pct(dispatcher: str, regime: str) -> float:
    runs = [arena.run_one(dispatcher, regime, s, **CELL) for s in SEEDS]
    return sum(r["pct_pop"] for r in runs) / len(runs)


# ---------------------------------------------------------------------------
# Engine mechanics: assigned boarding and the kiosk turnstile
# ---------------------------------------------------------------------------

class _NullGroupDispatcher:
    """Dispatcher that never assigns targets — for door-driven unit tests."""

    def dispatch_group(self, simulation):
        return {}


def test_assigned_passenger_steps_aside_for_other_cars():
    """A passenger assigned to C2 never boards C1; walk-ins board normally."""
    seed_rng(0)
    building = Building(num_floors=5)
    c1, c2 = Car("C1", 0), Car("C2", 0)
    sim = Simulation(building, c1, _NullGroupDispatcher(), MetricsCollector(),
                     verbose=False, extra_cars=[c2])
    walk_in = Passenger("W1", 0, 3, 1)
    claimed = Passenger("W2", 0, 4, 1)
    claimed.assigned_car_id = "C2"
    sim.schedule_passenger(1, walk_in)
    sim.schedule_passenger(1, claimed)

    c1.open_doors(3)
    sim.step()
    ids = {p.passenger_id for p in c1.passengers}
    assert "W1" in ids, "conventional walk-in should board the open car"
    assert "W2" not in ids, "passenger assigned to C2 must not board C1"

    # The claimed passenger boards their own car when it opens.
    c2.open_doors(3)
    sim.step()
    assert {p.passenger_id for p in c2.passengers} == {"W2"}


def test_kiosk_turnstile_blocks_walk_ins():
    """An assigned_only car admits no unassigned passengers (deadlock guard).

    Without the turnstile, walk-ins steal committed batch seats, the batch is
    stranded still-assigned, and a full car re-targets its own floor forever —
    the measured all-eight-cars lobby gridlock this rule exists to prevent.
    """
    seed_rng(0)
    building = Building(num_floors=5)
    car = Car("C1", 0)
    car.assigned_only = True
    sim = Simulation(building, car, _NullGroupDispatcher(), MetricsCollector(),
                     verbose=False)
    stranger = Passenger("S1", 0, 2, 1)
    invited = Passenger("S2", 0, 3, 1)
    invited.assigned_car_id = "C1"
    sim.schedule_passenger(1, stranger)
    sim.schedule_passenger(1, invited)

    car.open_doors(3)
    sim.step()
    assert {p.passenger_id for p in car.passengers} == {"S2"}


def test_immediate_assignment_locks_at_registration():
    """In immediate mode, a registration's car never changes while waiting."""
    seed_rng(0)
    building = Building(num_floors=10)
    c1, c2 = Car("C1", 0, capacity=4), Car("C2", 9, capacity=4)
    sim = Simulation(building, c1, DestinationGroupDispatcher("immediate"),
                     MetricsCollector(), verbose=False, extra_cars=[c2])
    p = Passenger("P1", 5, 7, 1)
    sim.schedule_passenger(1, p)

    sim.step()
    locked = p.assigned_car_id
    assert locked is not None
    for _ in range(25):
        sim.step()
        if p.board_time is not None:
            break
        assert p.assigned_car_id == locked


# ---------------------------------------------------------------------------
# Traffic: super-saturation (arrival_rate > 1)
# ---------------------------------------------------------------------------

def test_multispawn_above_unit_rate():
    """rate 2.5 spawns 2 or 3 per tick averaging ~2.5; legacy path untouched."""
    rng = random.Random(3)
    tg = TrafficGenerator(num_floors=10, arrival_rate=2.5, profile="UP_PEAK")
    counts = [len(tg.generate(t, rng)) for t in range(1, 401)]
    assert set(counts) <= {2, 3}
    assert sum(counts) / len(counts) == pytest.approx(2.5, abs=0.12)

    legacy = TrafficGenerator(num_floors=10, arrival_rate=0.4, profile="UNIFORM")
    legacy_counts = [len(legacy.generate(t, rng)) for t in range(1, 200)]
    assert set(legacy_counts) <= {0, 1}


# ---------------------------------------------------------------------------
# Gate S3 — the §3.3 capacity asymmetry, causally decomposed via the shuttle
# ablation (identical holding/turnstile/routing, no destination information)
# ---------------------------------------------------------------------------

def test_s3_uppeak_destination_info_doubles_capacity():
    """Up-peak: the §6-scale jump, and the information channel specifically.

    Measured on this cell: look_park 11.8% pop, shuttle 12.9% (routing alone
    is worth ~1.09x), dd_delayed 26.0% — 2.2x conventional overall, with the
    destination-information channel alone contributing ~2.0x (vs the published
    §6 doubling, 12.0% -> 24.4%).
    """
    look = _mean_pct("look_park", "up_peak")
    shuttle = _mean_pct("shuttle", "up_peak")
    dd = _mean_pct("dd_delayed", "up_peak")
    assert dd / look >= 1.8, (dd, look)
    assert dd / shuttle >= 1.6, (dd, shuttle)


def test_s3_downpeak_info_channel_is_inert():
    """Down-peak: destination information contributes exactly nothing.

    Every destination is the lobby, so the destination-compact window is a
    no-op and dd_delayed must equal the shuttle ablation run-for-run — any
    divergence means destination info leaked value into a regime where the
    literature says it has none [Report §3.3].
    """
    for seed in SEEDS:
        dd = arena.run_one("dd_delayed", "down_peak", seed, **CELL)
        shuttle = arena.run_one("shuttle", "down_peak", seed, **CELL)
        for key in ("delivered", "hc5", "awt", "p95_wait", "completion", "energy"):
            assert dd[key] == shuttle[key], (seed, key, dd[key], shuttle[key])


# ---------------------------------------------------------------------------
# Gate S5 — assignment timing held explicit; Sorsa (2019) direction
# ---------------------------------------------------------------------------

def test_s5_delayed_beats_immediate_in_mixed_traffic():
    """Lunch (bidirectional): delayed assignment outperforms immediate.

    Locking a call's car at registration degrades mixed traffic [Report §8,
    Sorsa 2019]. Measured: completion 0.61 vs 0.47, pct_pop 19.1 vs 14.9.
    """
    delayed = [arena.run_one("dd_delayed", "lunch", s, **CELL) for s in SEEDS]
    immediate = [arena.run_one("dd_immediate", "lunch", s, **CELL) for s in SEEDS]
    assert sum(r["completion"] for r in delayed) > sum(r["completion"] for r in immediate)
    assert sum(r["hc5"] for r in delayed) > sum(r["hc5"] for r in immediate)


def test_s5_assignment_mode_logged_on_every_run():
    """The immediate/delayed flag is on every DD run; None for conventional."""
    dd = arena.run_one("dd_immediate", "uniform", 1, ticks=50)
    assert dd["dd_assignment"] == "immediate"
    conventional = arena.run_one("look", "uniform", 1, ticks=50)
    assert conventional["dd_assignment"] is None