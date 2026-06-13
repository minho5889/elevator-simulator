# src/elevatorsim/arena/run.py
"""Single-episode runner + the report-§8 metrics panel.

Lifted verbatim from ``scripts/arena.py`` so both the CLI ladder and the web
``/api/arena`` endpoint score against one instrument. ``scripts/arena.py``
re-exports ``run_one`` / ``percentile`` / the analytic helpers for back-compat.
"""

import math
from typing import Any, Dict, List, Optional

from elevatorsim.core.building import Building
from elevatorsim.core.car import Car
from elevatorsim.core.events import BoardingRefused, DoorOpened, PassengerBoarded
from elevatorsim.core.metrics import MetricsCollector
from elevatorsim.core.simulation import Simulation
from elevatorsim.core.traffic import TrafficGenerator
from elevatorsim.config import seed_rng
from elevatorsim.arena import registry
from elevatorsim.arena.registry import REGIMES


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
    # Resolved via the registry MODULE (not a bound import) so tests can patch the
    # factory to inject a custom dispatcher.
    dispatcher = registry._make_dispatcher(dispatcher_name)
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
