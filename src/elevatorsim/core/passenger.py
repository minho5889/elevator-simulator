# src/elevatorsim/core/passenger.py
"""Passenger entity for tracking source, target, weight, and timing metrics."""

# Character weight table. Index = int(digits of passenger_id) % len(table),
# mirroring the frontend's emoji character mapping (ElevatorShaft.jsx PEOPLE)
# so the kid you see on screen weighs like a kid.
CHARACTER_WEIGHTS_KG = [30, 32, 38, 60, 75, 52, 68, 62, 80, 58, 65, 90]


def default_weight_kg(passenger_id: str) -> int:
    """Deterministic weight derived from the passenger id."""
    digits = "".join(ch for ch in str(passenger_id) if ch.isdigit())
    index = int(digits) if digits else 0
    return CHARACTER_WEIGHTS_KG[index % len(CHARACTER_WEIGHTS_KG)]


class Passenger:
    """Represents a passenger in the elevator simulation."""

    def __init__(
        self,
        passenger_id: str,
        source_floor: int,
        target_floor: int,
        spawn_time: int,
        weight_kg: int | None = None,
    ) -> None:
        """
        Initialize passenger.

        Args:
            passenger_id: Unique identifier for the passenger
            source_floor: Floor where the passenger requests the elevator
            target_floor: Destination floor
            spawn_time: Simulation tick when passenger request was spawned
            weight_kg: Body weight; defaults deterministically from the id
        """
        self.passenger_id = passenger_id
        self.source_floor = source_floor
        self.target_floor = target_floor
        self.spawn_time = spawn_time
        self.weight_kg = weight_kg if weight_kg is not None else default_weight_kg(passenger_id)
        # Destination dispatch: when set, this passenger boards only the named
        # car (kiosk assignment — Report §3). None = conventional hall call.
        self.assigned_car_id: str | None = None

        # Timing metrics to be filled during simulation
        self.board_time: int | None = None
        self.arrival_time: int | None = None

    @property
    def direction(self) -> int:
        """Return travel direction: 1 for UP, -1 for DOWN."""
        return 1 if self.target_floor > self.source_floor else -1

    def board(self, time: int) -> None:
        """Mark passenger as boarded."""
        self.board_time = time

    def arrive(self, time: int) -> None:
        """Mark passenger as arrived at destination."""
        self.arrival_time = time

    @property
    def wait_time(self) -> int | None:
        """Time spent waiting for the elevator to arrive (spawn to board)."""
        if self.board_time is None:
            return None
        return self.board_time - self.spawn_time

    @property
    def transit_time(self) -> int | None:
        """Time spent inside the elevator (board to arrive)."""
        if self.board_time is None or self.arrival_time is None:
            return None
        return self.arrival_time - self.board_time

    @property
    def total_time(self) -> int | None:
        """Total time from request spawn to arrival."""
        if self.arrival_time is None:
            return None
        return self.arrival_time - self.spawn_time

    def __repr__(self) -> str:
        return (
            f"Passenger(id={self.passenger_id}, {self.source_floor}->{self.target_floor}, "
            f"spawn={self.spawn_time}, wait={self.wait_time}, total={self.total_time})"
        )
