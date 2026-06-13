# src/elevatorsim/core/simulation.py
"""Fixed-tick simulation engine supporting multi-car elevator banks.

Each ``step()`` call advances the clock by exactly one tick and steps every car in
the bank once (1 floor per tick, doors open 2 ticks). This tick-based contract is what
the WebSocket streaming protocol and the recorded preset caches depend on, so it is
preserved across all tiers. Tier 0/1 single-car runs are an exact special case
(``num_cars == 1``).

Note: a SimPy/discrete-event engine was evaluated and deliberately rejected — see
``docs/decision-log.md`` Decision 2. The event-jumping model conflicts with per-tick
visualization, and variable car speeds (Tier 3) are expressible as fractional
position accumulation within this loop.
"""

from typing import List, Callable, Dict, Any, Optional
from elevatorsim.core.building import Building
from elevatorsim.core.car import Car
from elevatorsim.core.passenger import Passenger
from elevatorsim.core.metrics import MetricsCollector
from elevatorsim.core.events import (
    Event, PassengerSpawned, CallRegistered, CarArrived,
    DoorOpened, PassengerBoarded, PassengerDeboarded, DoorClosed,
    CarMoved, CarDispatched, BoardingRefused
)
from elevatorsim.config import RNG


class Simulation:
    """Fixed-tick elevator simulation coordinator supporting 1..N cars.

    Backward-compatible: when ``num_cars`` is omitted or equals 1 the behaviour
    is identical to the Tier 0/1 single-car engine.
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
        stop_ticks: int = 2,
        transfer_ticks: int = 0,
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
            stop_ticks: Door/stop penalty per stop in ticks (``t_s`` in the RTT
                model [Report §6, §8]). The legacy default of 2 reproduces the
                Tier 0-2 fixed-tick contract exactly.
            transfer_ticks: Per-passenger transfer time in ticks (``t_p``). The
                legacy default of 0 means boarding is instantaneous — Tier 0-2
                behaviour. Set > 0 for the Tier-3 "skyscraper" time-cost model,
                where each boarding/alighting passenger lengthens the stop. This
                is the term destination dispatch exists to reduce; with it at 0
                the simulator understates destination dispatch [Report §8].
        """
        self.building = building
        self.car = car  # legacy accessor – always points to cars[0]
        self.dispatcher = dispatcher
        self.metrics = metrics_collector
        self.traffic_generator = traffic_generator
        self.verbose = verbose
        # Tier-3 time-cost model (t_s, t_p). Defaults preserve the legacy contract.
        self.stop_ticks = stop_ticks
        self.transfer_ticks = transfer_ticks

        # Multi-car bank: cars list always starts with the primary ``car``
        self.cars: List[Car] = [car]
        if extra_cars:
            self.cars.extend(extra_cars)

        self.current_time = 0
        # (car_id, passenger_id) pairs already announced as weight refusals
        self._announced_refusals: set = set()
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
                    passenger.target_floor,
                    getattr(passenger, "weight_kg", None)
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
                    passenger.target_floor,
                    getattr(passenger, "weight_kg", None)
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
            from_pos = car.current_position
            moved = car.move_tick()
            if moved:
                self.emit(CarMoved(self.current_time, car.car_id, from_pos, car.current_position))

                # Check if arrived
                if car.current_position == float(car.target_floor):
                    self.emit(CarArrived(self.current_time, car.car_id, car.current_floor))
                    car.open_doors(self.stop_ticks)
                    self.emit(DoorOpened(self.current_time, car.car_id, car.current_floor))

        # 4. Handle boarding and deboarding if doors are open
        if car.door_state == "OPEN":
            # Deboard arriving passengers
            deboarded = car.deboard()
            for p in deboarded:
                self.emit(PassengerDeboarded(self.current_time, p.passenger_id, car.car_id, car.current_floor))

            # Board waiting passengers on current floor (queue order: first
            # person who doesn't fit stops boarding, like a real elevator line)
            waiting = self.building.get_waiting_at(car.current_floor)
            boarded = []
            for p in list(waiting):
                # Destination dispatch: a passenger assigned to a different car
                # steps aside rather than blocking the line, and a kiosk-
                # controlled car admits assigned passengers only (Report §3) —
                # walk-ins stealing batch seats strands the batch and deadlocks
                # the bank (full car forever re-targeting its pickup floor).
                assigned = getattr(p, "assigned_car_id", None)
                if assigned is not None and assigned != car.car_id:
                    continue
                if assigned is None and getattr(car, "assigned_only", False):
                    continue
                if car.board(p):
                    boarded.append(p)
                    self.emit(PassengerBoarded(self.current_time, p.passenger_id, car.car_id, car.current_floor))
                else:
                    # Announce a weight refusal once per car/passenger pair;
                    # doors stay open ~2 ticks and we don't want duplicates
                    refusal_key = (car.car_id, p.passenger_id)
                    if car.max_weight_kg is not None and refusal_key not in self._announced_refusals:
                        self._announced_refusals.add(refusal_key)
                        self.emit(BoardingRefused(
                            self.current_time, p.passenger_id, car.car_id, car.current_floor,
                            getattr(p, "weight_kg", 0), car.current_weight_kg, car.max_weight_kg
                        ))
                    break  # Car is full
            self.building.remove_boarded(car.current_floor, boarded)

            # Tier-3 time-cost: lengthen the stop by t_p per transferring passenger
            # [Report §6, §8]. Transfers resolve in the first open tick (deboard()
            # empties arrivals and the board loop seats everyone who fits in one
            # pass), so this charge fires once per stop. When transfer_ticks == 0
            # (legacy Tier 0-2) the branch is skipped entirely and timing is
            # byte-identical.
            if self.transfer_ticks > 0:
                n_transfers = len(deboarded) + len(boarded)
                if n_transfers > 0:
                    car.door_timer += self.transfer_ticks * n_transfers

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
                                car.open_doors(self.stop_ticks)
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
                            car.open_doors(self.stop_ticks)
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
