# src/elevatorsim/core/metrics.py
"""Metrics collector class that aggregates performance statistics from simulation events."""

from typing import Dict, List, Any
from elevatorsim.core.events import (
    Event, PassengerSpawned, PassengerBoarded, PassengerDeboarded, CarMoved
)

class MetricsCollector:
    """Listens to simulation events and computes overall system metrics."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        """Reset all metric counters."""
        self.total_ticks = 0
        self.total_car_moves = 0
        self.total_energy = 0.0
        self.car_was_moving: Dict[str, bool] = {}
        
        # Track passenger objects by ID
        # Maps passenger_id -> Passenger object
        self.all_passengers: Dict[str, Any] = {}
        self.completed_passengers: List[Any] = []

    def register_passenger(self, passenger: Any) -> None:
        """Store the passenger reference to track dynamic state changes."""
        self.all_passengers[passenger.passenger_id] = passenger

    def on_event(self, event: Event) -> None:
        """
        Update metrics based on received event.

        Args:
            event: The domain event that occurred
        """
        from elevatorsim.core.events import DoorOpened

        self.total_ticks = max(self.total_ticks, event.time)

        if isinstance(event, PassengerSpawned):
            # The passenger is registered when added to the building
            pass
            
        elif isinstance(event, PassengerBoarded):
            passenger = self.all_passengers.get(event.passenger_id)
            if passenger:
                passenger.board(event.time)

        elif isinstance(event, PassengerDeboarded):
            passenger = self.all_passengers.get(event.passenger_id)
            if passenger:
                passenger.arrive(event.time)
                self.completed_passengers.append(passenger)

        elif isinstance(event, CarMoved):
            self.total_car_moves += 1
            # Calculate energy usage:
            # 1. Floor travel energy: 1.0 unit per floor traveled
            distance = abs(event.to_floor - event.from_floor)
            self.total_energy += distance * 1.0
            
            # 2. Motor start energy: 5.0 units when transitioning from rest
            if not self.car_was_moving.get(event.car_id, False):
                self.total_energy += 5.0
            
            self.car_was_moving[event.car_id] = True

        elif isinstance(event, DoorOpened):
            # 3. Door cycle energy: 0.5 units when doors open
            self.total_energy += 0.5
            self.car_was_moving[event.car_id] = False

    def get_summary(self) -> Dict[str, Any]:
        """
        Compute and return summary metrics.

        Returns:
            Dictionary containing aggregated metrics
        """
        spawned_count = len(self.all_passengers)
        completed_count = len(self.completed_passengers)

        wait_times = [p.wait_time for p in self.completed_passengers if p.wait_time is not None]
        transit_times = [p.transit_time for p in self.completed_passengers if p.transit_time is not None]
        total_times = [p.total_time for p in self.completed_passengers if p.total_time is not None]

        avg_wait = sum(wait_times) / len(wait_times) if wait_times else 0.0
        avg_transit = sum(transit_times) / len(transit_times) if transit_times else 0.0
        avg_total = sum(total_times) / len(total_times) if total_times else 0.0

        return {
            "total_ticks": self.total_ticks,
            "total_car_moves": self.total_car_moves,
            "passengers_spawned": spawned_count,
            "passengers_completed": completed_count,
            "avg_wait_time": round(avg_wait, 2),
            "avg_transit_time": round(avg_transit, 2),
            "avg_total_time": round(avg_total, 2),
            "total_energy": round(self.total_energy, 2),
        }

    def print_summary(self, title: str = "Simulation Metrics Summary") -> None:
        """Print formatted metrics summary to stdout."""
        summary = self.get_summary()
        print("\n=======================================")
        print(f" {title}")
        print("=======================================")
        print(f" Total Ticks Run:       {summary['total_ticks']}")
        print(f" Total Car Moves:       {summary['total_car_moves']}")
        print(f" Passengers Spawned:    {summary['passengers_spawned']}")
        print(f" Passengers Completed:  {summary['passengers_completed']}")
        print(f" Total Energy Consumed: {summary['total_energy']}")
        print("---------------------------------------")
        print(f" Avg Wait Time (ticks):  {summary['avg_wait_time']}")
        print(f" Avg Transit (ticks):   {summary['avg_transit_time']}")
        print(f" Avg Total Time (ticks): {summary['avg_total_time']}")
        print("=======================================\n")
