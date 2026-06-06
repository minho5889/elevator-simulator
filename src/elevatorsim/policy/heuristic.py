# src/elevatorsim/policy/heuristic.py
"""LOOK-style heuristic elevator dispatcher baseline."""

from typing import Any
from elevatorsim.policy.base import Dispatcher

class HeuristicDispatcher(Dispatcher):
    """
    LOOK elevator scheduling algorithm.
    
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
