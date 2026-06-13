# src/elevatorsim/policy/destination.py
"""Destination dispatch (hall call allocation) group control [Report §3].

Passengers enter their destination at a kiosk *before* boarding; the controller
assigns each to a specific car and the engine enforces assigned boarding via
``Passenger.assigned_car_id``. Knowing origin–destination pairs pre-boarding
lets the controller batch passengers by destination band, cutting stops per
round trip — the lever behind the verified §6 capacity result (RTT 202.3 s →
100.8 s on the same hardware).

The information asymmetry is real in this codebase: conventional dispatchers
(`heuristic.py`, `baselines.py`) see only hall-call floors and onboard targets;
this module is the only policy family that reads a *waiting* passenger's
``target_floor`` — exactly the kiosk's contribution [Report §3.1].

Two assignment policies, held explicit per gate S5 [Report §8; Sorsa 2019]:

- ``delayed`` (default): a passenger is committed to a car only when a car is
  actually allocated to their pickup — assignment stays re-optimisable until
  the last moment. Sorsa (2019) shows this materially beats immediate
  assignment in mixed traffic.
- ``immediate``: a passenger is locked to a car at registration — the
  destination-dispatch UX constraint ("go to car B" on the kiosk screen).

Idle cars with no obligations park at the main terminal, matching the
conventional rung (``look_park``) so HC5 comparisons measure *batching*, not
staging.
"""

from typing import Any, Dict, List, Set

from elevatorsim.policy.base import GroupDispatcher
from elevatorsim.policy.heuristic import GroupHeuristicDispatcher


class DestinationGroupDispatcher(GroupDispatcher):
    """Destination-batching group dispatcher with explicit assignment timing.

    Departure control: a car with only pickups (nothing onboard) is *held*
    until its batch reaches ``batch_threshold`` of its free seats or the oldest
    waiting passenger in the batch has waited ``patience_ticks`` — without
    this, idle cars grab the first trickle of arrivals and depart near-empty,
    destroying the stop-batching that is destination dispatch's entire
    advantage (measured: 3.4% pop vs conventional's 11.8% on the §6 cell).
    Patience bounds the wait tail in light traffic. Departure policy applies
    identically to both assignment modes — it is orthogonal to *when*
    passengers are locked to cars (the S5 variable).
    """

    def __init__(
        self,
        assignment: str = "delayed",
        batch_threshold: float = 0.75,
        patience_ticks: int = 30,
        batch_style: str = "window",
    ) -> None:
        """``batch_style``:

        - ``"window"`` (default): destination-compact batches — the kiosk's
          information channel, the §6 stop-collapse lever.
        - ``"fifo"``: spawn-order batches, destination info unused. The
          ablation rung (arena name ``shuttle``): identical holding, turnstile
          and routing, so dd-vs-shuttle isolates exactly what destination
          information contributes per regime (gate S3) — up-peak it collapses
          stops; down-peak every destination is the lobby and the window is a
          no-op, so dd ≈ shuttle there by construction.
        """
        if assignment not in ("delayed", "immediate"):
            raise ValueError(f"assignment must be 'delayed' or 'immediate', got {assignment!r}")
        if batch_style not in ("window", "fifo"):
            raise ValueError(f"batch_style must be 'window' or 'fifo', got {batch_style!r}")
        self.assignment_mode = assignment
        self.batch_threshold = batch_threshold
        self.patience_ticks = patience_ticks
        self.batch_style = batch_style

    # ------------------------------------------------------------------
    # GroupDispatcher protocol
    # ------------------------------------------------------------------

    def dispatch_group(self, simulation: Any) -> Dict[str, int | None]:
        building = simulation.building
        cars = simulation.cars

        # Kiosk turnstile: destination-controlled cars admit assigned
        # passengers only. Idempotent; set here because the dispatcher, not
        # the arena, owns the boarding discipline.
        for car in cars:
            car.assigned_only = True

        waiting: List[Any] = []
        for floor in range(building.num_floors):
            waiting.extend(building.get_waiting_at(floor))

        # Current commitments: waiting passengers already assigned to a car.
        committed: Dict[str, List[Any]] = {}
        for p in waiting:
            cid = getattr(p, "assigned_car_id", None)
            if cid is not None:
                committed.setdefault(cid, []).append(p)

        if self.assignment_mode == "immediate":
            # Lock every new registration to a car right now.
            for p in waiting:
                if getattr(p, "assigned_car_id", None) is None:
                    self._assign_immediate(p, cars, committed)

        now = simulation.current_time
        assignments: Dict[str, int | None] = {}
        idle = [c for c in cars if c.door_state == "CLOSED" and c.target_floor is None]
        for car in sorted(idle, key=lambda c: c.car_id):
            mine = committed.get(car.car_id, [])

            # Departure control: pickups only, batch thin, nobody waiting too
            # long -> hold the car where it is and re-evaluate next tick.
            if car.passenger_count == 0 and mine and self._should_hold(car, mine, now):
                continue

            # Obligations: deliver everyone onboard; pick up committed
            # passengers only while seats remain — a full car must never
            # target a pickup (it deadlocks on its own floor otherwise).
            obligations: Set[int] = {p.target_floor for p in car.passengers}
            if car.passenger_count < car.capacity:
                obligations |= {p.source_floor for p in mine}

            if not obligations and self.assignment_mode == "delayed":
                batch = self._take_batch(car, waiting, now)
                if batch:
                    committed.setdefault(car.car_id, []).extend(batch)
                    obligations = {batch[0].source_floor}

            if obligations:
                assignments[car.car_id] = GroupHeuristicDispatcher._look_target(
                    car, obligations, set()
                )
            elif car.current_floor != 0:
                # Main-terminal parking — staging parity with look_park.
                assignments[car.car_id] = 0
        return assignments

    def _should_hold(self, car: Any, batch: List[Any], now: int) -> bool:
        """True while a pickup-only batch is below threshold and within patience."""
        needed = max(1, int(self.batch_threshold * (car.capacity - car.passenger_count)))
        if len(batch) >= needed:
            return False
        oldest = min(p.spawn_time for p in batch)
        return (now - oldest) < self.patience_ticks

    # ------------------------------------------------------------------
    # Assignment policies
    # ------------------------------------------------------------------

    @staticmethod
    def _assign_immediate(p: Any, cars: List[Any], committed: Dict[str, List[Any]]) -> None:
        """Lock ``p`` to a car at registration: cheapest marginal batch cost.

        Cost 0 joins a car already stopping at p's destination; an empty car
        costs 1 (a fresh stop set); otherwise the distance from p's destination
        to the car's nearest committed destination (zone-span growth proxy).
        Ties break on projected load, then car id — fully deterministic.
        """
        best_key = None
        best_car = None
        for car in sorted(cars, key=lambda c: c.car_id):
            load = car.passenger_count + len(committed.get(car.car_id, []))
            if load >= car.capacity:
                continue
            dests = {q.target_floor for q in car.passengers}
            dests |= {q.target_floor for q in committed.get(car.car_id, [])}
            if not dests:
                cost = 1.0
            elif p.target_floor in dests:
                cost = 0.0
            else:
                cost = float(min(abs(p.target_floor - d) for d in dests))
            key = (cost, load, car.car_id)
            if best_key is None or key < best_key:
                best_key, best_car = key, car
        if best_car is None:
            # Whole bank at projected capacity: queue on the least-loaded car.
            best_car = min(
                cars,
                key=lambda c: (c.passenger_count + len(committed.get(c.car_id, [])), c.car_id),
            )
        p.assigned_car_id = best_car.car_id
        committed.setdefault(best_car.car_id, []).append(p)

    def _take_batch(self, car: Any, waiting: List[Any], now: int) -> List[Any]:
        """Delayed assignment: commit a destination-compact batch to ``car``.

        The oldest unassigned passenger picks the pickup floor (starvation
        guard — Denning's tail discipline), then the batch is the
        destination-sorted window of up to ``capacity`` floor-mates with the
        smallest destination span *containing that oldest passenger*, so the
        guard cannot be optimised away by compactness. Departure control: no
        batch is taken at all while it would be below threshold and within
        patience — taking it would commit the car prematurely.
        """
        unassigned = [p for p in waiting if getattr(p, "assigned_car_id", None) is None]
        if not unassigned:
            return []
        oldest = min(unassigned, key=lambda p: (p.spawn_time, p.passenger_id))
        seats = car.capacity - car.passenger_count
        mates = [p for p in unassigned if p.source_floor == oldest.source_floor]
        k = min(seats, len(mates))
        if k <= 0:
            return []
        needed = max(1, int(self.batch_threshold * seats))
        if k < needed and (now - oldest.spawn_time) < self.patience_ticks:
            return []

        if self.batch_style == "fifo":
            # Ablation: spawn order, oldest first — destination info unused.
            mates.sort(key=lambda p: (p.spawn_time, p.passenger_id))
            batch = mates[:k]
        else:
            floor_mates = sorted(
                mates, key=lambda p: (p.target_floor, p.spawn_time, p.passenger_id)
            )
            anchor = floor_mates.index(oldest)
            lo = max(0, anchor - k + 1)
            hi = min(anchor, len(floor_mates) - k)
            best_start, best_span = lo, None
            for start in range(lo, hi + 1):
                span = (
                    floor_mates[start + k - 1].target_floor
                    - floor_mates[start].target_floor
                )
                if best_span is None or span < best_span:
                    best_span, best_start = span, start
            batch = floor_mates[best_start:best_start + k]

        for p in batch:
            p.assigned_car_id = car.car_id
        return batch
