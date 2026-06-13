# tests/test_timing.py
"""Tier-3 time-cost model (t_v, t_s, t_p) and legacy-contract regression.

Validates that the engine charges the round-trip-time terms with the correct
per-unit cost [docs/skyscraper-plan.md P1, gate S1; Report §6, §8] and that the
legacy Tier 0-2 fixed-tick contract is byte-identical when the Tier-3 knobs are
left at their defaults (stop_ticks=2, transfer_ticks=0, speed=1.0).
"""

from elevatorsim.core.building import Building
from elevatorsim.core.car import Car
from elevatorsim.core.events import DoorOpened, PassengerDeboarded
from elevatorsim.core.metrics import MetricsCollector
from elevatorsim.core.passenger import Passenger
from elevatorsim.core.simulation import Simulation
from elevatorsim.policy.heuristic import HeuristicDispatcher
from elevatorsim.config import seed_rng


def _scripted_uppeak_trip(
    passengers: int, stop_ticks: int = 2, transfer_ticks: int = 0, speed: float = 1.0
) -> int:
    """One deterministic up-peak trip; return the tick of the last delivery.

    ``passengers`` people board together at the lobby (floor 0) and ride to
    distinct floors 1..P, so the LOOK car makes exactly P+1 stops (lobby + one
    per drop) with 2P transfers (P boards + P alights). No down calls, so the
    car ends at the top — this measures the up-leg, which is what the RTT terms
    decompose. The number of stops/transfers that *precede* the final delivery
    event is P stops and 2P-1 transfers (the last drop's own door/transfer time
    lands after the event we measure), which is why the closed form below uses
    P and 2P-1 as the term multiplicities.
    """
    seed_rng(0)  # no traffic generator is used, but keep global state pinned
    floors = passengers + 1
    building = Building(num_floors=floors)
    car = Car("C1", initial_floor=0, capacity=passengers + 5, speed=speed)
    metrics = MetricsCollector()
    sim = Simulation(
        building, car, HeuristicDispatcher(), metrics, traffic_generator=None,
        verbose=False, stop_ticks=stop_ticks, transfer_ticks=transfer_ticks,
    )
    for i in range(1, passengers + 1):
        sim.schedule_passenger(1, Passenger(f"P{i}", 0, i, 1))

    last = {"t": 0}
    sim.register_listener(
        lambda e: last.__setitem__("t", e.time)
        if isinstance(e, PassengerDeboarded)
        else None
    )
    sim.run_until_complete(max_ticks=100_000)
    assert len(metrics.completed_passengers) == passengers
    return last["t"]


def test_legacy_contract_pinned():
    """Defaults reproduce the Tier 0-2 contract — pinned scenario value.

    A 5-passenger up-peak trip under the legacy contract (t_s=2, t_p=0, speed=1)
    completes its last delivery at tick 16. This pin guards against accidental
    timing drift in the core engine.
    """
    assert _scripted_uppeak_trip(5) == 16


def test_default_params_equal_explicit_legacy():
    """Omitting the Tier-3 knobs equals passing their legacy defaults."""
    seed_rng(0)
    b = Building(num_floors=4)
    car = Car("C1", initial_floor=0)
    m = MetricsCollector()
    # Construct without the new kwargs at all; must match the explicit defaults.
    sim = Simulation(b, car, HeuristicDispatcher(), m, verbose=False)
    assert sim.stop_ticks == 2
    assert sim.transfer_ticks == 0


def test_rtt_stop_and_transfer_terms_closed_form():
    """Gate S1: total time matches base + P·(t_s−2) + (2P−1)·t_p exactly.

    Each stop costs t_s and each transfer costs t_p [Report §6], so perturbing
    either knob moves the trip time by exactly its multiplicity. Holds across a
    grid of (t_s, t_p), proving the terms are independent and linear.
    """
    P = 5
    base = _scripted_uppeak_trip(P, stop_ticks=2, transfer_ticks=0)
    for t_s in (2, 3, 4, 6):
        for t_p in (0, 1, 2, 3):
            observed = _scripted_uppeak_trip(P, stop_ticks=t_s, transfer_ticks=t_p)
            expected = base + P * (t_s - 2) + (2 * P - 1) * t_p
            assert observed == expected, (t_s, t_p, observed, expected)


def test_transfer_term_scales_with_passenger_count():
    """The t_p term grows with passengers (2P−1 per transfer-tick)."""
    for P in (3, 5, 8):
        base = _scripted_uppeak_trip(P, transfer_ticks=0)
        with_tp = _scripted_uppeak_trip(P, transfer_ticks=1)
        assert with_tp - base == 2 * P - 1


def test_travel_term_scales_with_floor_time():
    """The t_v term: halving speed (t_v 1→2) adds H ticks on the up-leg."""
    P = 5
    base = _scripted_uppeak_trip(P, speed=1.0)
    slow = _scripted_uppeak_trip(P, speed=0.5)
    # Highest reversal floor H = P for this scenario; up-leg travel = H·(t_v−1).
    assert slow - base == P


# ---------------------------------------------------------------------------
# P2 — express / rated speed (skyscraper-plan.md, gate: RTT terms hold at v > 1)
# ---------------------------------------------------------------------------

def _express_trip(speed: float):
    """One passenger, lobby -> top of a 19-floor tower (floor 18) at rated speed.

    Returns (delivery_tick, door_open_count, total_energy). The 18-floor run at
    speed v takes ceil(18/v) move ticks — express cars cover multiple floors per
    tick and clamp exactly onto the target (no overshoot, no mid-flight stops).
    """
    seed_rng(0)
    building = Building(num_floors=19)
    car = Car("C1", initial_floor=0, capacity=4, speed=speed)
    metrics = MetricsCollector()
    sim = Simulation(
        building, car, HeuristicDispatcher(), metrics, traffic_generator=None,
        verbose=False,
    )
    sim.schedule_passenger(1, Passenger("P1", 0, 18, 1))

    seen = {"deboard": 0, "doors": 0}

    def listen(e):
        if isinstance(e, PassengerDeboarded):
            seen["deboard"] = e.time
        elif isinstance(e, DoorOpened):
            seen["doors"] += 1

    sim.register_listener(listen)
    sim.run_until_complete(max_ticks=100_000)
    assert len(metrics.completed_passengers) == 1
    return seen["deboard"], seen["doors"], metrics.total_energy


def test_express_speed_cuts_travel_by_the_t_v_term():
    """Rated speeds > 1 floor/tick shorten travel by exactly ceil(d/v) per leg."""
    base, doors1, energy1 = _express_trip(1.0)
    assert doors1 == 2  # lobby pickup + top drop, nothing in between
    for speed, ticks_saved in ((2.0, 9), (3.0, 12), (4.0, 13)):
        t, doors, energy = _express_trip(speed)
        assert base - t == ticks_saved, (speed, base, t)
        # Doors never open mid-flight at any speed.
        assert doors == 2
        # Express saves time, not distance: energy is speed-invariant.
        assert energy == energy1


def test_express_fractional_speed_clamps_exactly():
    """Non-integer rated speeds land exactly on target: ceil(18/2.5) = 8 ticks."""
    base, _, _ = _express_trip(1.0)
    t, doors, _ = _express_trip(2.5)
    assert base - t == 10
    assert doors == 2


_DEST_FLOORS = (3, 6, 9, 12, 15, 18)


def _round_trip_return_tick(speed: float, stop_ticks: int, transfer_ticks: int) -> int:
    """Full up-peak round trip on the 19-floor reference cell [Report §6 geometry].

    Six passengers board together at the lobby and alight at six evenly spaced
    floors (segments of 3, so speeds 1 and 3 divide every leg exactly); a lobby
    up-call scheduled after departure forces the express return. Returns the
    tick the doors reopen at the lobby — the measured round-trip time.
    """
    seed_rng(0)
    building = Building(num_floors=19)
    car = Car("C1", initial_floor=0, capacity=10, speed=speed)
    metrics = MetricsCollector()
    sim = Simulation(
        building, car, HeuristicDispatcher(), metrics, traffic_generator=None,
        verbose=False, stop_ticks=stop_ticks, transfer_ticks=transfer_ticks,
    )
    for i, floor in enumerate(_DEST_FLOORS, start=1):
        sim.schedule_passenger(1, Passenger(f"P{i}", 0, floor, 1))
    # Registered after the slowest config has left the lobby (tick 12), and long
    # before any config reverses at the top — so every run shares one route.
    sim.schedule_passenger(14, Passenger("P7", 0, 1, 14))

    ret = {"t": None}

    def listen(e):
        if isinstance(e, DoorOpened) and e.floor == 0 and e.time > 14 and ret["t"] is None:
            ret["t"] = e.time

    sim.register_listener(listen)
    sim.run_until_complete(max_ticks=100_000)
    assert ret["t"] is not None, "car never returned to the lobby"
    return ret["t"]


def test_round_trip_rtt_terms_hold_at_rated_speed():
    """P2 gate: the RTT decomposition holds at express speed on the 19-floor cell.

    Travel: up sweep (six 3-floor segments) + 18-floor express return — going
    from t_v=1 to t_v=1/3 saves (18+18)·(1−1/3) = 24 ticks. Stops before the
    return door: lobby + 6 destinations = 7, each charged t_s; transfers before
    it: 6 boards + 6 alights = 12, each charged t_p. UPPINT for an L-car bank is
    this RTT divided by L — instrumented arena-wide in P3.
    """
    base = _round_trip_return_tick(1.0, 2, 0)
    express_base = _round_trip_return_tick(3.0, 2, 0)
    assert base - express_base == 24

    for speed, speed_base in ((1.0, base), (3.0, express_base)):
        for t_s in (2, 4):
            for t_p in (0, 1):
                observed = _round_trip_return_tick(speed, t_s, t_p)
                expected = speed_base + 7 * (t_s - 2) + 12 * t_p
                assert observed == expected, (speed, t_s, t_p, observed, expected)
