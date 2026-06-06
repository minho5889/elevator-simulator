# src/elevatorsim/core/building.py
"""Building model managing floor queues and outstanding passenger waitlists."""

from typing import Dict, List
from elevatorsim.core.passenger import Passenger

class Building:
    """Manages floor queues and requests in the building."""

    def __init__(self, num_floors: int = 5) -> None:
        """
        Initialize the building.

        Args:
            num_floors: Total number of floors in the building
        """
        self.num_floors = num_floors
        # Maps floor number to list of waiting passengers
        self.waiting_passengers: Dict[int, List[Passenger]] = {
            f: [] for f in range(num_floors)
        }

    def add_passenger(self, passenger: Passenger) -> None:
        """
        Add a passenger to the waiting list on their source floor.

        Args:
            passenger: Passenger requesting service
        """
        if 0 <= passenger.source_floor < self.num_floors:
            self.waiting_passengers[passenger.source_floor].append(passenger)
        else:
            raise ValueError(f"Invalid source floor: {passenger.source_floor}")

    def get_waiting_at(self, floor: int) -> List[Passenger]:
        """Get the list of passengers waiting at a specific floor."""
        return self.waiting_passengers.get(floor, [])

    def remove_boarded(self, floor: int, boarded: List[Passenger]) -> None:
        """
        Remove passengers from the floor queue after they successfully board.

        Args:
            floor: Floor number
            boarded: List of passengers who boarded
        """
        boarded_ids = {p.passenger_id for p in boarded}
        self.waiting_passengers[floor] = [
            p for p in self.waiting_passengers[floor] if p.passenger_id not in boarded_ids
        ]

    def has_pending_calls(self) -> bool:
        """Check if any passengers are waiting at any floor."""
        return any(len(queue) > 0 for queue in self.waiting_passengers.values())

    def get_active_calls(self) -> List[int]:
        """
        Get a list of floor numbers that have waiting passengers (hall calls).

        Returns:
            List of floors with active waiting lists
        """
        return [f for f, queue in self.waiting_passengers.items() if len(queue) > 0]

    def __repr__(self) -> str:
        queues = {f: len(queue) for f, queue in self.waiting_passengers.items() if len(queue) > 0}
        return f"Building(floors={self.num_floors}, active_queues={queues})"
