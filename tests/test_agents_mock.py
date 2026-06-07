# tests/test_agents_mock.py
"""Unit tests verifying DispatcherAgent offline mock mode integrations."""

import os
import pytest
from elevatorsim.core.building import Building
from elevatorsim.core.car import Car
from elevatorsim.core.passenger import Passenger
from elevatorsim.core.metrics import MetricsCollector
from elevatorsim.core.simulation import Simulation
from elevatorsim.policy.agentic import DispatcherAgent


@pytest.fixture(autouse=True)
def enable_mock_gemini():
    """Ensure mock Gemini environment is enabled for all tests in this file."""
    old_val = os.environ.get("MOCK_GEMINI")
    os.environ["MOCK_GEMINI"] = "true"
    yield
    if old_val is not None:
        os.environ["MOCK_GEMINI"] = old_val
    else:
        os.environ.pop("MOCK_GEMINI", None)


def test_mock_agentic_dispatcher_single_car():
    """Verify mock agentic dispatch functions correctly for a single car simulation."""
    building = Building(num_floors=5)
    car = Car(car_id="C1", initial_floor=0)
    dispatcher = DispatcherAgent()
    metrics = MetricsCollector()
    
    sim = Simulation(building, car, dispatcher, metrics, verbose=True)

    # Spawn passenger at floor 0 heading to floor 3
    p1 = Passenger("P1", source_floor=0, target_floor=3, spawn_time=1)
    sim.schedule_passenger(1, p1)

    # Run for 20 ticks
    sim.run_until_complete(max_ticks=20)

    # Ensure mock mode was triggered and simulation ran to completion
    summary = metrics.get_summary()
    assert summary["passengers_completed"] == 1
    assert summary["total_ticks"] > 0


def test_mock_agentic_dispatcher_multi_car():
    """Verify mock agentic dispatch functions correctly for a multi-car bank."""
    building = Building(num_floors=5)
    cars = [Car("C1", 0), Car("C2", 0)]
    dispatcher = DispatcherAgent()
    metrics = MetricsCollector()

    sim = Simulation(
        building=building,
        car=cars[0],
        dispatcher=dispatcher,
        metrics_collector=metrics,
        verbose=True,
        extra_cars=cars[1:]
    )

    # Spawn passengers
    p1 = Passenger("P1", source_floor=0, target_floor=4, spawn_time=1)
    p2 = Passenger("P2", source_floor=3, target_floor=1, spawn_time=2)
    sim.schedule_passenger(1, p1)
    sim.schedule_passenger(2, p2)

    # Run for 30 ticks
    sim.run_until_complete(max_ticks=30)

    # Ensure both passengers completed
    summary = metrics.get_summary()
    assert summary["passengers_completed"] == 2
    assert summary["total_ticks"] > 0
