# tests/test_core.py
"""Unit tests for the deterministic simulator core.

Ensures passenger tracking, car dynamics, building queues, and LOOK policy
work correctly without calling any LLMs or requiring API keys.
"""

from elevatorsim.core.passenger import Passenger
from elevatorsim.core.car import Car
from elevatorsim.core.building import Building
from elevatorsim.core.metrics import MetricsCollector
from elevatorsim.core.simulation import Simulation
from elevatorsim.policy.heuristic import HeuristicDispatcher

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
