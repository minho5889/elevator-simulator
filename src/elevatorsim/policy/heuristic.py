# src/elevatorsim/policy/heuristic.py
"""LOOK-style heuristic elevator dispatchers for single-car and multi-car modes."""

from typing import Any, Dict, Set
from elevatorsim.policy.base import Dispatcher, GroupDispatcher


class HeuristicDispatcher(Dispatcher):
    """
    LOOK elevator scheduling algorithm (single-car legacy).
    
    Services requests in the current direction of travel. If no requests remain in 
    the current direction, it reverses and services requests in the other direction.
    If no requests exist anywhere, the elevator becomes idle.
    """

    def dispatch(self, simulation: Any) -> int | None:
        """
        Determine the next target floor using LOOK algorithm.

        Args:
            simulation: Active simulation instance

        Returns:
            Target floor index (0-indexed) or None if idle
        """
        car = simulation.car
        building = simulation.building

        # Gather all requested floors (onboard dropoffs + floor waiting pickups)
        onboard_destinations = {p.target_floor for p in car.passengers}
        hall_calls = set(building.get_active_calls())
        all_requests = onboard_destinations | hall_calls

        if not all_requests:
            return None

        current_floor = car.current_floor
        current_direction = car.direction

        # If car already has a target, we can keep it unless we arrived. 
        # (Since dispatch is called when idle/target is None, this is standard)
        
        # 1. If currently moving or committed to a direction
        if current_direction == 1:  # UP
            # Find closest request above or equal to current floor
            upper_requests = [r for r in all_requests if r >= current_floor]
            if upper_requests:
                return min(upper_requests)
            # No upper requests: reverse direction
            lower_requests = [r for r in all_requests if r < current_floor]
            if lower_requests:
                return max(lower_requests)

        elif current_direction == -1:  # DOWN
            # Find closest request below or equal to current floor
            lower_requests = [r for r in all_requests if r <= current_floor]
            if lower_requests:
                return max(lower_requests)
            # No lower requests: reverse direction
            upper_requests = [r for r in all_requests if r > current_floor]
            if upper_requests:
                return min(upper_requests)

        # 2. Car is IDLE (0 direction) - find nearest request
        # Tie-breaker: prefer higher floor (arbitrary choice)
        closest_request = None
        min_distance = float('inf')

        for req in sorted(all_requests):
            dist = abs(req - current_floor)
            if dist < min_distance:
                min_distance = dist
                closest_request = req
            elif dist == min_distance:
                # If equal distance, choose the one in the direction we prefer or just tie-break
                if req > current_floor:
                    closest_request = req

        return closest_request


class GroupHeuristicDispatcher(GroupDispatcher, Dispatcher):
    """
    Nearest-idle-car LOOK group dispatcher for multi-car elevator banks.

    When multiple cars are idle, assigns each car to the nearest unserviced hall
    call or onboard destination. Also satisfies the legacy single-car
    ``Dispatcher`` protocol so it can be used transparently in both modes.
    """

    def __init__(self) -> None:
        self._legacy = HeuristicDispatcher()

    def dispatch(self, simulation: Any) -> int | None:
        """Legacy single-car dispatch (delegates to HeuristicDispatcher)."""
        return self._legacy.dispatch(simulation)

    def dispatch_group(self, simulation: Any) -> Dict[str, int | None]:
        """
        Assign targets to all idle cars using nearest-car-first LOOK.

        Algorithm:
        1. Collect all outstanding requests (hall calls + each car's onboard destinations).
        2. For each idle car, identify its personal onboard destinations first
           (these MUST be served by that car).
        3. Assign remaining hall calls to the nearest idle car that has no
           assignment yet, using LOOK scan direction to break ties.
        """
        building = simulation.building
        cars = simulation.cars
        assignments: Dict[str, int | None] = {}

        # Identify idle cars
        idle_cars = [c for c in cars if c.door_state == "CLOSED" and c.target_floor is None]
        if not idle_cars:
            return assignments

        # Collect all active hall calls (floors with waiting passengers)
        hall_calls: Set[int] = set(building.get_active_calls())

        # Track which hall calls are already being served by non-idle cars
        for c in cars:
            if c.target_floor is not None:
                hall_calls.discard(c.target_floor)

        # Phase 1: Assign cars that have onboard passengers first
        assigned_calls: Set[int] = set()
        for car in idle_cars:
            if car.passenger_count > 0:
                # Car has passengers, must deliver them – use LOOK on onboard targets
                target = self._look_target(car, {p.target_floor for p in car.passengers}, set())
                assignments[car.car_id] = target
                if target is not None:
                    assigned_calls.add(target)

        # Phase 2: Assign remaining idle cars to nearest hall call
        remaining_calls = hall_calls - assigned_calls
        remaining_idle = [c for c in idle_cars if c.car_id not in assignments]

        if remaining_calls and remaining_idle:
            # Greedy nearest-first assignment
            available_calls = set(remaining_calls)
            for car in sorted(remaining_idle, key=lambda c: c.car_id):
                if not available_calls:
                    break

                # Find nearest call using LOOK direction preference
                target = self._nearest_call(car, available_calls)
                if target is not None:
                    assignments[car.car_id] = target
                    available_calls.discard(target)

        return assignments

    @staticmethod
    def _look_target(car: Any, targets: Set[int], exclude: Set[int]) -> int | None:
        """Pick the next LOOK-style target from a set of floors."""
        candidates = targets - exclude
        if not candidates:
            return None

        current = car.current_floor
        direction = car.direction

        if direction == 1:  # UP
            upper = [f for f in candidates if f >= current]
            if upper:
                return min(upper)
            lower = [f for f in candidates if f < current]
            if lower:
                return max(lower)
        elif direction == -1:  # DOWN
            lower = [f for f in candidates if f <= current]
            if lower:
                return max(lower)
            upper = [f for f in candidates if f > current]
            if upper:
                return min(upper)

        # IDLE: nearest
        return min(candidates, key=lambda f: abs(f - current))

    @staticmethod
    def _nearest_call(car: Any, calls: Set[int]) -> int | None:
        """Assign the nearest hall call to a car, with LOOK tie-breaking."""
        if not calls:
            return None

        current = car.current_floor
        direction = car.direction

        # Sort by distance, then direction preference
        sorted_calls = sorted(calls, key=lambda f: (abs(f - current), -f if direction >= 0 else f))
        return sorted_calls[0] if sorted_calls else None
