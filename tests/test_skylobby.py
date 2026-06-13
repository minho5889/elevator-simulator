# tests/test_skylobby.py
"""Sky-lobby / shuttle topology (P6): transfer mechanic + the equal-core gate."""

from elevatorsim.core.building import Building
from elevatorsim.core.car import Car
from elevatorsim.core.events import PassengerDeboarded, PassengerTransferred
from elevatorsim.core.metrics import MetricsCollector
from elevatorsim.core.passenger import Passenger
from elevatorsim.core.simulation import Simulation
from elevatorsim.policy.skylobby import SkyLobbyDispatcher, run_flat, run_skylobby


class _NullDispatcher:
    def dispatch_group(self, simulation):
        return {}


def test_final_target_defaults_to_target():
    """Single-leg passengers have final_target == target_floor (byte-identical)."""
    p = Passenger("P", 2, 7, 0)
    assert p.final_target == 7
    q = Passenger("Q", 0, 10, 0, final_target=18)
    assert q.target_floor == 10 and q.final_target == 18


def test_transfer_delivers_to_final_via_two_legs():
    """A ground->high passenger rides a shuttle to the sky lobby, transfers, and
    is delivered to the final floor by a local car — counted once."""
    building = Building(num_floors=20)
    cars = [Car("S1", 0, capacity=8), Car("L1", 10, capacity=8)]
    disp = SkyLobbyDispatcher(sky_lobby=10, shuttle_ids=["S1"], local_ids=["L1"])
    metrics = MetricsCollector()
    sim = Simulation(building, cars[0], disp, metrics, verbose=False,
                     extra_cars=cars[1:], stop_ticks=2, transfer_ticks=0)
    p = Passenger("P1", 0, 10, 1, final_target=15)
    sim.schedule_passenger(1, p)

    events = []
    sim.register_listener(events.append)
    sim.run_until_complete(max_ticks=300)

    transfers = [e for e in events if isinstance(e, PassengerTransferred)]
    assert len(transfers) == 1 and transfers[0].floor == 10 and transfers[0].final_target == 15
    assert p in metrics.completed_passengers
    assert metrics.completed_passengers.count(p) == 1  # counted once, not at the transfer
    assert p.arrival_time is not None and p.target_floor == 15


def test_service_range_blocks_out_of_zone_boarding():
    """A shuttle (zone 0..10) refuses a high-bound rider but takes an in-zone one."""
    building = Building(num_floors=20)
    car = Car("S1", 0, capacity=8)
    car.service_range = (0, 10)
    sim = Simulation(building, car, _NullDispatcher(), MetricsCollector(), verbose=False)

    high = Passenger("HIGH", 0, 15, 1)   # target outside shuttle zone
    low = Passenger("LOW", 0, 8, 1)      # target inside shuttle zone
    sim.schedule_passenger(1, high)
    sim.schedule_passenger(1, low)

    car.open_doors(3)
    sim.step()  # doors open at floor 0; boarding obeys service_range
    boarded = {p.passenger_id for p in car.passengers}
    assert "LOW" in boarded
    assert "HIGH" not in boarded


def test_p6_gate_sky_lobby_beats_flat_under_equal_core():
    """P6 gate: at supertall height, under an equal core-area (shaft-floor)
    budget, the sky-lobby tower beats the flat bank — the §5.1 economic argument.

    A flat shaft spans the whole height; sky-lobby shafts are half-length, so the
    same core fields ~2x the cars, and that fleet advantage outweighs the
    transfer overhead. (A naive equal-CARS comparison goes the other way — the
    transfer is pure dispatching overhead — which is exactly why the benefit is
    architectural, not throughput, and must be measured per core area.)
    """
    for floors, sky in ((60, 30), (80, 40)):
        core = 8 * floors           # flat: 8 shafts x full height
        span = floors - sky
        n_sh = (core // 2) // sky
        n_lo = (core // 2) // span
        flat = sum(run_flat(s, floors=floors, cars=8, sky_lobby=sky,
                            arrival_rate=3.0, ticks=500)["hc5"] for s in (7, 8)) / 2
        sky_hc5 = sum(run_skylobby(s, floors=floors, shuttle_cars=n_sh, local_cars=n_lo,
                                   sky_lobby=sky, arrival_rate=3.0, ticks=500)["hc5"]
                      for s in (7, 8)) / 2
        assert sky_hc5 / flat >= 1.15, (floors, flat, sky_hc5)


def test_skylobby_pipeline_delivers():
    """Smoke check: the two-leg pipeline delivers a meaningful share at a light
    load (the transfer mechanic's correctness is pinned by the test above; this
    guards against a regression that strands everyone at the sky lobby)."""
    res = run_skylobby(7, floors=40, shuttle_cars=4, local_cars=4, sky_lobby=20,
                       arrival_rate=0.5, ticks=400)
    assert res["delivered"] > 0
    assert res["completion"] > 0.5
