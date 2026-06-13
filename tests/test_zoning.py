# tests/test_zoning.py
"""Static zoning (P5): zone map, signage assignment rule, and the height gate."""

import importlib.util
import sys
from pathlib import Path

from elevatorsim.core.car import Car
from elevatorsim.core.passenger import Passenger
from elevatorsim.policy.zoning import ZonedStaticDispatcher

_ARENA_PATH = Path(__file__).resolve().parents[1] / "scripts" / "arena.py"
_spec = importlib.util.spec_from_file_location("arena_zone", _ARENA_PATH)
arena = importlib.util.module_from_spec(_spec)
sys.modules["arena_zone"] = arena
_spec.loader.exec_module(arena)


def test_zone_map_is_contiguous_balanced_and_covers_all_upper_floors():
    """Floors 1..N-1 are partitioned into one contiguous zone per car."""
    disp = ZonedStaticDispatcher()
    cars = [Car(f"C{i + 1}", 0) for i in range(8)]
    disp._build_zone_map(32, cars)

    assert set(disp._zone_car) == set(range(1, 32))  # lobby unzoned, full cover
    # Contiguity: each car's floors form an unbroken band.
    by_car = {}
    for floor, cid in disp._zone_car.items():
        by_car.setdefault(cid, []).append(floor)
    sizes = []
    for floors in by_car.values():
        floors.sort()
        assert floors == list(range(floors[0], floors[-1] + 1))
        sizes.append(len(floors))
    # Balance: zone sizes differ by at most one floor.
    assert max(sizes) - min(sizes) <= 1
    assert len(by_car) == 8


def test_signage_assignment_rule():
    """Lobby boardings assign by destination zone; others by source zone."""
    disp = ZonedStaticDispatcher()
    cars = [Car("C1", 0), Car("C2", 0)]
    disp._build_zone_map(11, cars)  # floors 1-5 -> C1, 6-10 -> C2

    up = Passenger("U", 0, 7, 1)          # lobby -> 7: destination zone (C2)
    down = Passenger("D", 4, 0, 1)        # 4 -> lobby: source zone (C1)
    inter = Passenger("I", 9, 2, 1)       # 9 -> 2: source zone (C2)
    committed = {}
    for p in (up, down, inter):
        disp._assign_immediate(p, cars, committed)
    assert up.assigned_car_id == "C2"
    assert down.assigned_car_id == "C1"
    assert inter.assigned_car_id == "C2"


def test_p5_zoned_beats_single_group_at_height():
    """P5 gate: at 30+ floors, zoning beats the single-group baselines on HC5.

    Measured on the 32-floor cell (31 above terminal, 8 cars, capacity 24,
    600/5min demand, t_s=9/t_p=1): look 4.2% pop, look_park 6.1%, zoned 13.3%
    — 2.2x conventional staging and 3.2x plain LOOK, with the P95 wait tail
    roughly halved. The single group collapses with height (S~17 stops and
    H~30 per trip); zones shrink both terms per car [Report §2.3, §5.1].
    """
    cell = dict(floors=32, cars=8, capacity=24, arrival_rate=2.0, ticks=900,
                stop_ticks=9, transfer_ticks=1, population=3100)
    seeds = (7, 8)

    def mean_pct(dispatcher):
        runs = [arena.run_one(dispatcher, "up_peak", s, **cell) for s in seeds]
        return sum(r["pct_pop"] for r in runs) / len(runs)

    look = mean_pct("look")
    look_park = mean_pct("look_park")
    zoned = mean_pct("zoned")
    assert zoned / look_park >= 1.6, (zoned, look_park)
    assert zoned / look >= 2.0, (zoned, look)