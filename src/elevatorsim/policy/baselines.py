# src/elevatorsim/policy/baselines.py
"""Baseline single-car dispatchers forming the report's evaluation ladder.

These exist so the arena (``scripts/arena.py``) can score a learned policy against
the canonical lineage of dispatching heuristics rather than a single strawman
[Report §8: "build the baseline ladder, not one comparison"]:

    FCFS  ->  nearest-call (SSTF)  ->  ETA-cost  ->  LOOK  ->  learned policy
    weakest                                          strongest (heuristic.py)

All three implement the legacy single-car ``Dispatcher`` protocol
(``dispatch(simulation) -> int | None``), so the engine drives them in both
single-car and multi-car banks (it calls ``dispatch`` once per idle car with
``simulation.car`` swapped in — see ``Simulation._dispatch_idle_cars``). None of
them consume from the global ``config.RNG``, so per-seed traffic stays identical
across policies for apples-to-apples comparison.

Rung semantics, and why each is a rung:
- **FCFS** serves calls in arrival order, ignoring the car's route — the
  textbook worst case that direction-sorted sweeps were invented to beat
  [Report §1.2].
- **nearest-call** is SSTF in a shaft: always go to the closest request. It
  minimises the next hop but starves edge floors under load [Report §1.2,
  Denning 1967]. The honest weak-but-tempting baseline.
- **ETA-cost** adds an energy-aware directional-continuity term so it resists
  reversing mid-sweep — a simplified single-car proxy for the bi-objective
  wait+energy ETA dispatching of classical group control [Report §2.2,
  Tyni & Ylinen 2006]. The full multi-car bi-objective assignment is future
  work; this captures the directional-continuity intuition in ~1 cost term.
"""

from typing import Any, Dict, List, Optional, Set

from elevatorsim.policy.base import Dispatcher


def _active_request_floors(car: Any, building: Any) -> Set[int]:
    """All floors the car must eventually visit: onboard dropoffs + hall calls."""
    onboard = {p.target_floor for p in car.passengers}
    hall = set(building.get_active_calls())
    return onboard | hall


class FCFSDispatcher(Dispatcher):
    """First-come-first-served: drive to the earliest-registered outstanding request.

    The request set is every onboard passenger (keyed by spawn time) and every
    waiting passenger at a hall call (the floor's earliest spawn time represents
    that call). The next target is the floor of the globally earliest request,
    which makes the car shuttle in arrival order with no route optimisation —
    exactly the behaviour SCAN/LOOK improve on [Report §1.2].
    """

    def dispatch(self, simulation: Any) -> Optional[int]:
        car = simulation.car
        building = simulation.building

        # (spawn_time, floor) candidates. Lower spawn_time = served first.
        candidates: List[tuple] = [(p.spawn_time, p.target_floor) for p in car.passengers]
        for floor in building.get_active_calls():
            waiting = building.get_waiting_at(floor)
            if waiting:
                earliest = min(p.spawn_time for p in waiting)
                candidates.append((earliest, floor))

        if not candidates:
            return None

        # Earliest request wins; tie-break on lower floor for determinism.
        candidates.sort(key=lambda c: (c[0], c[1]))
        return candidates[0][1]


class NearestCallDispatcher(Dispatcher):
    """Nearest-call / SSTF: always serve the closest outstanding request.

    Greedy minimisation of the next hop. Attractive for a first simulation and
    decisively flawed: under load the car dwells where requests are dense and
    edge floors can be deferred unboundedly [Report §1.2, Denning 1967 on SSTF
    starvation]. Deterministic lower-floor tie-break.
    """

    def dispatch(self, simulation: Any) -> Optional[int]:
        car = simulation.car
        requests = _active_request_floors(car, simulation.building)
        if not requests:
            return None

        current = car.current_floor
        return min(requests, key=lambda f: (abs(f - current), f))


class ETACostDispatcher(Dispatcher):
    """ETA-cost: nearest-call with an energy-aware directional-continuity penalty.

    Scores each candidate stop by estimated travel time plus a reversal penalty,
    then takes the argmin::

        cost(t) = |t - position| + reverse_penalty * (t reverses the sweep?)

    The reversal penalty (default 2.5 ≈ half a motor-start's 5.0 energy units in
    the metrics model) makes the car prefer continuing its current sweep when
    distances are comparable — directional continuity bought with a cost term
    rather than LOOK's hard sweep rule. This is a deliberately simplified
    single-car proxy for the bi-objective wait+energy ETA dispatching used in
    production group control [Report §2.2, Tyni & Ylinen 2006]; the full
    multi-car assignment formulation is out of scope for the baseline ladder.

    Stateful: the committed sweep direction is tracked per ``car_id`` because the
    car resets ``direction`` to 0 each time its doors open, so the engine-level
    direction is unavailable at dispatch time. A fresh dispatcher is created per
    arena run, so no state leaks across seeds.
    """

    def __init__(self, reverse_penalty: float = 2.5) -> None:
        self.reverse_penalty = reverse_penalty
        # car_id -> last committed travel direction (1 up, -1 down)
        self._committed_dir: Dict[str, int] = {}

    def dispatch(self, simulation: Any) -> Optional[int]:
        car = simulation.car
        requests = _active_request_floors(car, simulation.building)
        if not requests:
            return None

        current = car.current_floor
        committed = self._committed_dir.get(car.car_id, 0)

        def cost(target: int) -> float:
            distance = abs(target - current)
            move_dir = 1 if target > current else (-1 if target < current else 0)
            reverses = committed != 0 and move_dir != 0 and move_dir != committed
            return distance + (self.reverse_penalty if reverses else 0.0)

        # argmin cost; deterministic lower-floor tie-break.
        target = min(requests, key=lambda f: (cost(f), f))

        new_dir = 1 if target > current else (-1 if target < current else committed)
        self._committed_dir[car.car_id] = new_dir
        return target
