# src/elevatorsim/core/traffic.py
"""Stochastic passenger traffic generator with customizable floor distribution profiles."""

import random
from typing import List
from elevatorsim.core.passenger import Passenger

class TrafficGenerator:
    """Generates passenger arrivals based on arrival probability and profiles."""

    def __init__(
        self,
        num_floors: int = 5,
        arrival_rate: float = 0.2,
        profile: str = "UNIFORM"
    ) -> None:
        """
        Initialize the traffic generator.

        Args:
            num_floors: Total number of floors in the building
            arrival_rate: Probability of passenger spawn per tick (0.0 to 1.0)
            profile: Traffic shape name: "UNIFORM", "DOWN_PEAK", or "UP_PEAK"
        """
        self.num_floors = num_floors
        self.arrival_rate = arrival_rate
        
        profile_upper = profile.upper()
        if profile_upper not in ("UNIFORM", "DOWN_PEAK", "UP_PEAK"):
            raise ValueError(f"Unknown traffic profile: {profile}")
        self.profile = profile_upper
        
        self.passenger_counter = 0

    def generate(self, tick: int, rng: random.Random) -> List[Passenger]:
        """
        Determine if any passengers spawn at this tick based on profile.

        Args:
            tick: The current simulation time step
            rng: Seeded random number generator instance to ensure reproducibility

        Returns:
            List of generated Passenger entities for this tick (empty list if no spawn)
        """
        if rng.random() >= self.arrival_rate:
            return []

        self.passenger_counter += 1
        passenger_id = f"P{self.passenger_counter}"
        
        source = 0
        target = 0

        if self.profile == "UNIFORM":
            # Pick any floor uniformly
            source = rng.randint(0, self.num_floors - 1)
            # Pick a different target floor
            target = rng.choice([f for f in range(self.num_floors) if f != source])

        elif self.profile == "DOWN_PEAK":
            # Morning peak: passengers spawn on upper floors heading to the lobby (floor 0)
            source = rng.randint(1, self.num_floors - 1)
            target = 0

        elif self.profile == "UP_PEAK":
            # Evening peak: passengers spawn at the lobby (floor 0) heading to upper floors
            source = 0
            target = rng.randint(1, self.num_floors - 1)

        passenger = Passenger(
            passenger_id=passenger_id,
            source_floor=source,
            target_floor=target,
            spawn_time=tick
        )
        return [passenger]
