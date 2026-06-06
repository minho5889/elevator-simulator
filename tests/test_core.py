# tests/test_core.py
"""Unit tests for the deterministic simulator core.

Ensures passenger tracking, car dynamics, building queues, and LOOK policy
work correctly without calling any LLMs or requiring API keys.
Covers both single-car (Tier 0/1) and multi-car (Tier 2) modes.
"""

from elevatorsim.core.passenger import Passenger
from elevatorsim.core.car import Car
from elevatorsim.core.building import Building
from elevatorsim.core.metrics import MetricsCollector
from elevatorsim.core.simulation import Simulation
from elevatorsim.policy.heuristic import HeuristicDispatcher, GroupHeuristicDispatcher

def test_passenger_metrics():
    """Verify passenger time tracking and direction properties."""
    p = Passenger(passenger_id="P1", source_floor=1, target_floor=4, spawn_time=5)
    
    assert p.passenger_id == "P1"
    assert p.source_floor == 1
    assert p.target_floor == 4
    assert p.spawn_time == 5
    assert p.direction == 1  # UP
    
    p.board(10)
    assert p.wait_time == 5
    
    p.arrive(12)
    assert p.transit_time == 2
    assert p.total_time == 7


def test_car_physics():
    """Verify car target settings, door status, passenger limits, and movement."""
    car = Car(car_id="C1", initial_floor=0, capacity=2)
    
    # Target and directions
    car.set_target(3)
    assert car.direction == 1
    assert car.target_floor == 3
    
    # Doors prevent movement
    car.open_doors()
    assert car.door_state == "OPEN"
    assert car.direction == 0
    assert not car.move_tick()
    
    # Closing doors
    assert not car.step_doors()  # timer: 2 -> 1, still open
    assert car.door_state == "OPEN"
    assert car.step_doors()  # timer: 1 -> 0, closes doors
    assert car.door_state == "CLOSED"
    
    # Movement ticks
    assert car.move_tick()
    assert car.current_floor == 1
    assert car.move_tick()
    assert car.current_floor == 2
    assert car.move_tick()
    assert car.current_floor == 3
    
    # Arrived target resets target
    car.close_doors()  # trigger target reset since floor == target
    assert car.target_floor is None
    assert car.direction == 0
    
    # Capacity constraints
    p1 = Passenger("P1", 3, 0, 1)
    p2 = Passenger("P2", 3, 1, 1)
    p3 = Passenger("P3", 3, 2, 1)
    
    assert car.board(p1)
    assert car.board(p2)
    assert not car.board(p3)  # Over capacity
    
    deboarded = car.deboard()
    assert len(deboarded) == 0  # Floor is 3, none of the onboard passenger targets match
    
    car.current_floor = 1
    deboarded = car.deboard()
    assert len(deboarded) == 1
    assert deboarded[0].passenger_id == "P2"
    assert len(car.passengers) == 1


def test_building_queues():
    """Verify floor queues and hall calls inside the building."""
    building = Building(num_floors=5)
    
    assert not building.has_pending_calls()
    
    p1 = Passenger("P1", 0, 3, 1)
    p2 = Passenger("P2", 2, 0, 2)
    
    building.add_passenger(p1)
    building.add_passenger(p2)
    
    assert building.has_pending_calls()
    assert set(building.get_active_calls()) == {0, 2}
    
    waiting_at_0 = building.get_waiting_at(0)
    assert len(waiting_at_0) == 1
    assert waiting_at_0[0].passenger_id == "P1"
    
    # Simulate boarding
    building.remove_boarded(0, [p1])
    assert 0 not in building.get_active_calls()
    assert len(building.get_waiting_at(0)) == 0


def test_heuristic_look_simulation():
    """Verify LOOK dispatcher correctly resolves a scripted simulation baseline."""
    building = Building(num_floors=5)
    car = Car(car_id="C1", initial_floor=0)
    dispatcher = HeuristicDispatcher()
    metrics = MetricsCollector()
    
    sim = Simulation(building, car, dispatcher, metrics, verbose=False)
    
    # Scripted scenario
    p1 = Passenger("P1", 0, 4, 1)
    p2 = Passenger("P2", 3, 1, 3)
    p3 = Passenger("P3", 2, 4, 5)
    
    sim.schedule_passenger(1, p1)
    sim.schedule_passenger(3, p2)
    sim.schedule_passenger(5, p3)
    
    sim.run_until_complete(max_ticks=100)
    
    summary = metrics.get_summary()
    assert summary["passengers_completed"] == 3
    assert summary["total_ticks"] > 0
    assert summary["total_car_moves"] > 0


# --------------------------------------------------------------------------
# Tier 2: Multi-Car Tests
# --------------------------------------------------------------------------

def test_simulation_multi_car_creation():
    """Verify multi-car bank initializes correctly with extra_cars."""
    building = Building(num_floors=5)
    cars = [Car(car_id=f"C{i+1}", initial_floor=0) for i in range(3)]
    dispatcher = GroupHeuristicDispatcher()
    metrics = MetricsCollector()

    sim = Simulation(
        building=building,
        car=cars[0],
        dispatcher=dispatcher,
        metrics_collector=metrics,
        verbose=False,
        extra_cars=cars[1:],
    )

    assert len(sim.cars) == 3
    assert sim.cars[0].car_id == "C1"
    assert sim.cars[1].car_id == "C2"
    assert sim.cars[2].car_id == "C3"
    assert sim.car is sim.cars[0]  # legacy accessor


def test_multi_car_group_dispatch():
    """Verify GroupHeuristicDispatcher assigns nearest car to each call."""
    building = Building(num_floors=5)
    c1 = Car(car_id="C1", initial_floor=0)
    c2 = Car(car_id="C2", initial_floor=4)
    dispatcher = GroupHeuristicDispatcher()
    metrics = MetricsCollector()

    sim = Simulation(
        building=building,
        car=c1,
        dispatcher=dispatcher,
        metrics_collector=metrics,
        verbose=False,
        extra_cars=[c2],
    )

    # Put passengers at floor 0 and floor 4
    p1 = Passenger("P1", 0, 3, 1)
    p2 = Passenger("P2", 4, 1, 1)

    sim.schedule_passenger(1, p1)
    sim.schedule_passenger(1, p2)

    # Run one tick to spawn passengers, then group dispatch should assign
    sim.step()  # tick 1: passengers spawn, dispatch assigns

    # After tick 1, both cars should have targets
    # C1 is at floor 0 where P1 spawns, C2 is at floor 4 where P2 spawns
    # The group dispatcher should assign C1 -> floor 0, C2 -> floor 4
    assert c1.target_floor is not None or c1.door_state == "OPEN"
    assert c2.target_floor is not None or c2.door_state == "OPEN"


def test_multi_car_full_simulation():
    """Verify a full multi-car simulation completes all passengers."""
    building = Building(num_floors=5)
    cars = [Car(car_id=f"C{i+1}", initial_floor=0) for i in range(3)]
    dispatcher = GroupHeuristicDispatcher()
    metrics = MetricsCollector()

    sim = Simulation(
        building=building,
        car=cars[0],
        dispatcher=dispatcher,
        metrics_collector=metrics,
        verbose=False,
        extra_cars=cars[1:],
    )

    # Schedule multiple passengers across different floors and times
    sim.schedule_passenger(1, Passenger("P1", 0, 4, 1))
    sim.schedule_passenger(1, Passenger("P2", 0, 3, 1))
    sim.schedule_passenger(2, Passenger("P3", 4, 0, 2))
    sim.schedule_passenger(3, Passenger("P4", 2, 4, 3))
    sim.schedule_passenger(4, Passenger("P5", 1, 3, 4))

    sim.run_until_complete(max_ticks=100)

    summary = metrics.get_summary()
    assert summary["passengers_completed"] == 5
    assert summary["total_ticks"] > 0
    assert summary["total_car_moves"] > 0


def test_multi_car_backward_compat_single():
    """Verify single-car mode (no extra_cars) is identical to Tier 1."""
    building = Building(num_floors=5)
    car = Car(car_id="C1", initial_floor=0)
    dispatcher = HeuristicDispatcher()
    metrics = MetricsCollector()

    sim = Simulation(building, car, dispatcher, metrics, verbose=False)

    assert len(sim.cars) == 1
    assert sim.car is sim.cars[0]

    # Same scripted scenario as Tier 0/1 test
    sim.schedule_passenger(1, Passenger("P1", 0, 4, 1))
    sim.schedule_passenger(3, Passenger("P2", 3, 1, 3))
    sim.schedule_passenger(5, Passenger("P3", 2, 4, 5))

    sim.run_until_complete(max_ticks=100)

    summary = metrics.get_summary()
    assert summary["passengers_completed"] == 3


def test_legacy_dispatcher_with_multi_car():
    """Verify legacy single-car dispatcher works with multi-car simulation."""
    building = Building(num_floors=5)
    c1 = Car(car_id="C1", initial_floor=0)
    c2 = Car(car_id="C2", initial_floor=0)
    # Use legacy HeuristicDispatcher (no dispatch_group method)
    dispatcher = HeuristicDispatcher()
    metrics = MetricsCollector()

    sim = Simulation(
        building=building,
        car=c1,
        dispatcher=dispatcher,
        metrics_collector=metrics,
        verbose=False,
        extra_cars=[c2],
    )

    sim.schedule_passenger(1, Passenger("P1", 0, 4, 1))
    sim.schedule_passenger(1, Passenger("P2", 3, 0, 1))

    sim.run_until_complete(max_ticks=100)

    summary = metrics.get_summary()
    assert summary["passengers_completed"] == 2
