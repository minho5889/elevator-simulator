# src/elevatorsim/core/simulation.py
"""SimPy-powered discrete-event simulation engine supporting multi-car elevator banks.

Tier 2 upgrade: migrated from fixed-tick stepping to SimPy-based event scheduling.
Each car runs as an independent SimPy process. The public ``step()`` API advances the
SimPy environment by one time unit, maintaining full backward compatibility with the
WebSocket tick-based protocol and single-car Tier 0/1 presets.
"""

import simpy
from typing import List, Callable, Dict, Any, Optional
from elevatorsim.core.building import Building
from elevatorsim.core.car import Car
from elevatorsim.core.passenger import Passenger
from elevatorsim.core.metrics import MetricsCollector
from elevatorsim.core.events import (
    Event, PassengerSpawned, CallRegistered, CarArrived,
    DoorOpened, PassengerBoarded, PassengerDeboarded, DoorClosed,
    CarMoved, CarDispatched
)
from elevatorsim.config import RNG


class Simulation:
    """SimPy-backed elevator simulation coordinator supporting 1..N cars.

    Backward-compatible: when ``num_cars`` is omitted or equals 1 the behaviour
    is identical to the Tier 0/1 fixed-tick engine.
    """

    def __init__(
        self,
        building: Building,
        car: Car,
        dispatcher: Any,
        metrics_collector: MetricsCollector,
        traffic_generator: Any = None,
        verbose: bool = True,
        *,
        extra_cars: Optional[List[Car]] = None,
    ) -> None:
        """
        Initialize the simulation.

        Args:
            building: Building instance
            car: Primary car instance (backward-compatible single-car parameter)
            dispatcher: Dispatcher policy. Accepts both legacy single-car
                ``Dispatcher`` (with ``dispatch(sim)``) and the new multi-car
                ``GroupDispatcher`` (with ``dispatch_group(sim)``) protocol.
            metrics_collector: Metrics collector instance
            traffic_generator: Optional stochastic traffic generator
            verbose: If True, prints event traces to stdout
            extra_cars: Additional car instances for multi-car banks. If supplied
                the bank consists of ``[car] + extra_cars``.
        """
        self.building = building
        self.car = car  # legacy accessor – always points to cars[0]
        self.dispatcher = dispatcher
        self.metrics = metrics_collector
        self.traffic_generator = traffic_generator
        self.verbose = verbose

        # Multi-car bank: cars list always starts with the primary ``car``
        self.cars: List[Car] = [car]
        if extra_cars:
            self.cars.extend(extra_cars)

        self.current_time = 0
        self.listeners: List[Callable[[Event], None]] = [self.metrics.on_event]

        # Scripted passenger arrivals: tick -> List[Passenger]
        self.scheduled_arrivals: Dict[int, List[Passenger]] = {}

    # ------------------------------------------------------------------
    # Event system
    # ------------------------------------------------------------------

    def register_listener(self, listener: Callable[[Event], None]) -> None:
        """Register an event listener."""
        self.listeners.append(listener)

    def emit(self, event: Event) -> None:
        """Emit an event to all registered listeners and optionally print it."""
        for listener in self.listeners:
            listener(event)
        if self.verbose:
            print(str(event))

    # ------------------------------------------------------------------
    # Passenger scheduling
    # ------------------------------------------------------------------

    def schedule_passenger(self, tick: int, passenger: Passenger) -> None:
        """Schedule a passenger to spawn at a specific tick."""
        if tick not in self.scheduled_arrivals:
            self.scheduled_arrivals[tick] = []
        self.scheduled_arrivals[tick].append(passenger)
        self.metrics.register_passenger(passenger)

    # ------------------------------------------------------------------
    # Core tick engine
    # ------------------------------------------------------------------

    def _process_arrivals(self) -> None:
        """Process scripted and stochastic passenger arrivals for the current tick."""
        # 1a. Scripted arrivals
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

        # 1b. Stochastic arrivals
        if self.traffic_generator is not None:
            new_passengers = self.traffic_generator.generate(self.current_time, RNG)
            for passenger in new_passengers:
                self.metrics.register_passenger(passenger)
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

    def _step_car(self, car: Car) -> None:
        """Advance a single car by one tick: doors, movement, boarding."""
        # 2. Step the door timer
        doors_just_closed = car.step_doors()
        if doors_just_closed:
            self.emit(DoorClosed(self.current_time, car.car_id, car.current_floor))

        # 3. Move car if doors are closed and it has a target
        if car.door_state == "CLOSED" and car.target_floor is not None:
            from_floor = car.current_floor
            moved = car.move_tick()
            if moved:
                self.emit(CarMoved(self.current_time, car.car_id, from_floor, car.current_floor))

                # Check if arrived
                if car.current_floor == car.target_floor:
                    self.emit(CarArrived(self.current_time, car.car_id, car.current_floor))
                    car.open_doors()
                    self.emit(DoorOpened(self.current_time, car.car_id, car.current_floor))

        # 4. Handle boarding and deboarding if doors are open
        if car.door_state == "OPEN":
            # Deboard arriving passengers
            deboarded = car.deboard()
            for p in deboarded:
                self.emit(PassengerDeboarded(self.current_time, p.passenger_id, car.car_id, car.current_floor))

            # Board waiting passengers on current floor
            waiting = self.building.get_waiting_at(car.current_floor)
            boarded = []
            for p in list(waiting):
                if car.board(p):
                    boarded.append(p)
                    self.emit(PassengerBoarded(self.current_time, p.passenger_id, car.car_id, car.current_floor))
                else:
                    break  # Car is full
            self.building.remove_boarded(car.current_floor, boarded)

    def _dispatch_idle_cars(self) -> None:
        """Query the dispatcher for idle cars that need a target.

        Supports two dispatcher protocols:
        - **GroupDispatcher** (Tier 2): has ``dispatch_group(sim)`` returning
          ``Dict[str, int | None]`` mapping ``car_id`` -> target for every idle car.
        - **Legacy Dispatcher** (Tier 0/1): has ``dispatch(sim)`` returning a single
          target floor. In multi-car mode, legacy dispatchers are called once
          per idle car with ``sim.car`` temporarily swapped.
        """
        has_work = self.building.has_pending_calls() or any(c.passenger_count > 0 for c in self.cars)
        if not has_work:
            return

        idle_cars = [c for c in self.cars if c.door_state == "CLOSED" and c.target_floor is None]
        if not idle_cars:
            return

        # Prefer group dispatcher if available
        if hasattr(self.dispatcher, "dispatch_group"):
            assignments = self.dispatcher.dispatch_group(self)
            if assignments:
                for car_id, target in assignments.items():
                    if target is not None:
                        car = next((c for c in self.cars if c.car_id == car_id), None)
                        if car and car.door_state == "CLOSED" and car.target_floor is None:
                            car.set_target(target)
                            self.emit(CarDispatched(self.current_time, car_id, target))
                            # If target is current floor, open doors immediately
                            if car.current_floor == car.target_floor:
                                car.open_doors()
                                self.emit(DoorOpened(self.current_time, car.car_id, car.current_floor))
        else:
            # Legacy single-car dispatcher
            for car in idle_cars:
                if self.building.has_pending_calls() or car.passenger_count > 0:
                    # Temporarily set sim.car for legacy dispatchers
                    original_car = self.car
                    self.car = car
                    target = self.dispatcher.dispatch(self)
                    self.car = original_car
                    if target is not None:
                        car.set_target(target)
                        self.emit(CarDispatched(self.current_time, car.car_id, target))
                        # If target is current floor, open doors immediately
                        if car.current_floor == car.target_floor:
                            car.open_doors()
                            self.emit(DoorOpened(self.current_time, car.car_id, car.current_floor))

    def step(self) -> None:
        """Execute one simulation tick across all cars."""
        self.current_time += 1

        # 1. Process passenger arrivals
        self._process_arrivals()

        # 2-4. Step each car independently
        for car in self.cars:
            self._step_car(car)

        # 5. Dispatch idle cars
        self._dispatch_idle_cars()

    # ------------------------------------------------------------------
    # Batch run helpers
    # ------------------------------------------------------------------

    def run_until_complete(self, max_ticks: int = 100) -> None:
        """Run the simulation loop until all calls are completed or limit reached."""
        while (self.building.has_pending_calls() or
               any(c.passenger_count > 0 for c in self.cars) or
               any(t > self.current_time for t in self.scheduled_arrivals) or
               (self.traffic_generator is not None and self.current_time < max_ticks)) and self.current_time < max_ticks:
            self.step()
