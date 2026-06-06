# src/elevatorsim/core/simulation.py
"""Fixed-tick simulation engine orchestrating building, car, events, and policy checks."""

from typing import List, Callable, Dict, Any
from elevatorsim.core.building import Building
from elevatorsim.core.car import Car
from elevatorsim.core.passenger import Passenger
from elevatorsim.core.metrics import MetricsCollector
from elevatorsim.core.events import (
    Event, PassengerSpawned, CallRegistered, CarArrived,
    DoorOpened, PassengerBoarded, PassengerDeboarded, DoorClosed, CarMoved
)

class Simulation:
    """Fixed-tick elevator simulation coordinator."""

    def __init__(
        self,
        building: Building,
        car: Car,
        dispatcher: Any,
        metrics_collector: MetricsCollector,
        verbose: bool = True
    ) -> None:
        """
        Initialize the simulation.

        Args:
            building: Building instance
            car: Car instance
            dispatcher: Dispatcher policy (implements policy.base.Dispatcher)
            metrics_collector: Metrics collector instance
            verbose: If True, prints event traces to stdout
        """
        self.building = building
        self.car = car
        self.dispatcher = dispatcher
        self.metrics = metrics_collector
        self.verbose = verbose
        
        self.current_time = 0
        self.listeners: List[Callable[[Event], None]] = [self.metrics.on_event]
        
        # Scripted passenger arrivals: tick -> List[Passenger]
        self.scheduled_arrivals: Dict[int, List[Passenger]] = {}

    def register_listener(self, listener: Callable[[Event], None]) -> None:
        """Register an event listener."""
        self.listeners.append(listener)

    def emit(self, event: Event) -> None:
        """Emit an event to all registered listeners and optionally print it."""
        for listener in self.listeners:
            listener(event)
        if self.verbose:
            print(str(event))

    def schedule_passenger(self, tick: int, passenger: Passenger) -> None:
        """Schedule a passenger to spawn at a specific tick."""
        if tick not in self.scheduled_arrivals:
            self.scheduled_arrivals[tick] = []
        self.scheduled_arrivals[tick].append(passenger)
        self.metrics.register_passenger(passenger)

    def step(self) -> None:
        """Execute one simulation tick."""
        self.current_time += 1
        
        # 1. Process passenger arrivals
        if self.current_time in self.scheduled_arrivals:
            for passenger in self.scheduled_arrivals[self.current_time]:
                self.building.add_passenger(passenger)
                self.emit(PassengerSpawned(
                    self.current_time,
                    passenger.passenger_id,
                    passenger.source_floor,
                    passenger.target_floor
                ))
                self.emit(CallRegistered(
                    self.current_time,
                    passenger.source_floor,
                    passenger.direction
                ))

        # 2. Step the door timer if open
        doors_just_closed = self.car.step_doors()
        if doors_just_closed:
            self.emit(DoorClosed(self.current_time, self.car.car_id, self.car.current_floor))

        # 3. Move car if doors are closed and it has a target
        if self.car.door_state == "CLOSED" and self.car.target_floor is not None:
            from_floor = self.car.current_floor
            moved = self.car.move_tick()
            if moved:
                self.emit(CarMoved(self.current_time, self.car.car_id, from_floor, self.car.current_floor))
                
                # Check if arrived
                if self.car.current_floor == self.car.target_floor:
                    self.emit(CarArrived(self.current_time, self.car.car_id, self.car.current_floor))
                    self.car.open_doors()
                    self.emit(DoorOpened(self.current_time, self.car.car_id, self.car.current_floor))

        # 4. Handle boarding and deboarding if doors are open
        if self.car.door_state == "OPEN":
            # Deboard arriving passengers
            deboarded = self.car.deboard()
            for p in deboarded:
                self.emit(PassengerDeboarded(self.current_time, p.passenger_id, self.car.car_id, self.car.current_floor))

            # Board waiting passengers on current floor
            waiting = self.building.get_waiting_at(self.car.current_floor)
            boarded = []
            for p in list(waiting):
                if self.car.board(p):
                    boarded.append(p)
                    self.emit(PassengerBoarded(self.current_time, p.passenger_id, self.car.car_id, self.car.current_floor))
                else:
                    break  # Car is full
            self.building.remove_boarded(self.car.current_floor, boarded)

        # 5. Check if car is idle and needs a target
        # Doors must be closed and target_floor is None
        if self.car.door_state == "CLOSED" and self.car.target_floor is None:
            # Query policy dispatcher if building has requests or passengers are on board
            if self.building.has_pending_calls() or self.car.passenger_count > 0:
                target = self.dispatcher.dispatch(self)
                if target is not None:
                    self.car.set_target(target)
                    # If target is current floor, open doors immediately
                    if self.car.current_floor == self.car.target_floor:
                        self.car.open_doors()
                        self.emit(DoorOpened(self.current_time, self.car.car_id, self.car.current_floor))

    def run_until_complete(self, max_ticks: int = 100) -> None:
        """Run the simulation loop until all calls are completed or limit reached."""
        while (self.building.has_pending_calls() or 
               self.car.passenger_count > 0 or 
               any(t > self.current_time for t in self.scheduled_arrivals)) and self.current_time < max_ticks:
            self.step()
