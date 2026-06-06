# src/elevatorsim/core/car.py
"""Elevator car representation covering physics, doors, and onboard passengers."""

from typing import List
from elevatorsim.core.passenger import Passenger

class Car:
    """Represents an elevator car in the simulation."""

    def __init__(
        self,
        car_id: str,
        initial_floor: int = 0,
        capacity: int = 8
    ) -> None:
        """
        Initialize the elevator car.

        Args:
            car_id: Unique identifier for the car
            initial_floor: Starting floor
            capacity: Maximum passenger capacity
        """
        self.car_id = car_id
        self.current_floor = initial_floor
        self.target_floor: int | None = None
        self.direction = 0  # 1: UP, -1: DOWN, 0: STANDBY/IDLE
        self.door_state = "CLOSED"  # "CLOSED", "OPEN"
        self.door_timer = 0  # Ticks remaining for door open state
        self.passengers: List[Passenger] = []
        self.capacity = capacity

    @property
    def passenger_count(self) -> int:
        """Number of passengers currently in the car."""
        return len(self.passengers)

    @property
    def is_full(self) -> bool:
        """Check if the elevator is at capacity."""
        return len(self.passengers) >= self.capacity

    def set_target(self, floor: int) -> None:
        """
        Set a new target floor.

        Args:
            floor: Target destination floor
        """
        self.target_floor = floor
        if floor > self.current_floor:
            self.direction = 1
        elif floor < self.current_floor:
            self.direction = -1
        else:
            self.direction = 0

    def open_doors(self, open_ticks: int = 2) -> None:
        """
        Open the elevator doors and set the timer.

        Args:
            open_ticks: Number of ticks the doors stay open
        """
        self.door_state = "OPEN"
        self.door_timer = open_ticks
        self.direction = 0  # Cannot move while doors are open

    def close_doors(self) -> None:
        """Close the doors and clear target if reached."""
        self.door_state = "CLOSED"
        self.door_timer = 0
        if self.target_floor == self.current_floor:
            self.target_floor = None
            self.direction = 0

    def step_doors(self) -> bool:
        """
        Tick the door timer.

        Returns:
            True if doors transitioned from OPEN to CLOSED in this step.
        """
        if self.door_state == "OPEN":
            if self.door_timer > 0:
                self.door_timer -= 1
                if self.door_timer == 0:
                    self.close_doors()
                    return True
        return False

    def move_tick(self) -> bool:
        """
        Move the car one floor towards the target floor if doors are closed.

        Returns:
            True if the car moved, False otherwise.
        """
        if self.door_state == "OPEN" or self.target_floor is None:
            return False

        if self.current_floor < self.target_floor:
            self.current_floor += 1
            self.direction = 1
            return True
        elif self.current_floor > self.target_floor:
            self.current_floor -= 1
            self.direction = -1
            return True
        
        return False

    def board(self, passenger: Passenger) -> bool:
        """
        Board a passenger if capacity allows.

        Args:
            passenger: Passenger to board
        """
        if len(self.passengers) < self.capacity:
            self.passengers.append(passenger)
            return True
        return False

    def deboard(self) -> List[Passenger]:
        """
        Deboard passengers arriving at their destination floor.

        Returns:
            List of passengers who got off at the current floor
        """
        arrived = [p for p in self.passengers if p.target_floor == self.current_floor]
        self.passengers = [p for p in self.passengers if p.target_floor != self.current_floor]
        return arrived

    def __repr__(self) -> str:
        return (
            f"Car(id={self.car_id}, floor={self.current_floor}, target={self.target_floor}, "
            f"dir={self.direction}, door={self.door_state}, passengers={len(self.passengers)})"
        )
