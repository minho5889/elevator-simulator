# src/elevatorsim/core/events.py
"""Domain events emitted by the simulator for logging, metrics, and trace tracking."""

class Event:
    """Base event class."""
    
    def __init__(self, time: int) -> None:
        self.time = time


class PassengerSpawned(Event):
    """Event indicating a passenger arrived at a floor and registered a call."""

    def __init__(self, time: int, passenger_id: str, source: int, target: int) -> None:
        super().__init__(time)
        self.passenger_id = passenger_id
        self.source = source
        self.target = target

    def __str__(self) -> str:
        return f"[{self.time:03d} T] PASSENGER_SPAWNED: {self.passenger_id} requests {self.source}->{self.target}"


class CallRegistered(Event):
    """Event indicating a hall call request is registered on a floor."""

    def __init__(self, time: int, floor: int, direction: int) -> None:
        super().__init__(time)
        self.floor = floor
        self.direction = direction

    def __str__(self) -> str:
        dir_str = "UP" if self.direction == 1 else "DOWN"
        return f"[{self.time:03d} T] CALL_REGISTERED: Floor {self.floor} requests {dir_str}"


class CarArrived(Event):
    """Event indicating the elevator car arrived at a floor."""

    def __init__(self, time: int, car_id: str, floor: int) -> None:
        super().__init__(time)
        self.car_id = car_id
        self.floor = floor

    def __str__(self) -> str:
        return f"[{self.time:03d} T] CAR_ARRIVED: Car {self.car_id} arrived at floor {self.floor}"


class DoorOpened(Event):
    """Event indicating the elevator doors opened at a floor."""

    def __init__(self, time: int, car_id: str, floor: int) -> None:
        super().__init__(time)
        self.car_id = car_id
        self.floor = floor

    def __str__(self) -> str:
        return f"[{self.time:03d} T] DOOR_OPENED: Car {self.car_id} opened doors at floor {self.floor}"


class PassengerBoarded(Event):
    """Event indicating a passenger successfully boarded the car."""

    def __init__(self, time: int, passenger_id: str, car_id: str, floor: int) -> None:
        super().__init__(time)
        self.passenger_id = passenger_id
        self.car_id = car_id
        self.floor = floor

    def __str__(self) -> str:
        return f"[{self.time:03d} T] PASSENGER_BOARDED: {self.passenger_id} boarded car {self.car_id} at floor {self.floor}"


class PassengerDeboarded(Event):
    """Event indicating a passenger exited the car at their destination."""

    def __init__(self, time: int, passenger_id: str, car_id: str, floor: int) -> None:
        super().__init__(time)
        self.passenger_id = passenger_id
        self.car_id = car_id
        self.floor = floor

    def __str__(self) -> str:
        return f"[{self.time:03d} T] PASSENGER_DEBOARDED: {self.passenger_id} exited car {self.car_id} at floor {self.floor}"


class DoorClosed(Event):
    """Event indicating the elevator doors closed."""

    def __init__(self, time: int, car_id: str, floor: int) -> None:
        super().__init__(time)
        self.car_id = car_id
        self.floor = floor

    def __str__(self) -> str:
        return f"[{self.time:03d} T] DOOR_CLOSED: Car {self.car_id} closed doors at floor {self.floor}"


class CarDispatched(Event):
    """Event indicating a car has been dispatched to a target floor by the group dispatcher."""

    def __init__(self, time: int, car_id: str, target_floor: int) -> None:
        super().__init__(time)
        self.car_id = car_id
        self.target_floor = target_floor

    def __str__(self) -> str:
        return f"[{self.time:03d} T] CAR_DISPATCHED: Car {self.car_id} dispatched to floor {self.target_floor}"


class CarMoved(Event):
    """Event indicating the car traveled from one floor to another."""

    def __init__(self, time: int, car_id: str, from_floor: float, to_floor: float) -> None:
        super().__init__(time)
        self.car_id = car_id
        self.from_floor = float(from_floor)
        self.to_floor = float(to_floor)

    def __str__(self) -> str:
        return f"[{self.time:03d} T] CAR_MOVED: Car {self.car_id} traveled {self.from_floor:.2f} -> {self.to_floor:.2f}"
