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


def test_agentic_dispatcher_fallback_on_failure(monkeypatch):
    """Verify that if agent.structured_output raises an error, the dispatcher falls back to LOOK heuristic."""
    from strands import Agent
    def mock_structured_output(*args, **kwargs):
        raise ValueError("Simulated structured output failure")
    
    monkeypatch.setattr(Agent, "structured_output", mock_structured_output)

    # Setup simulation
    building = Building(num_floors=5)
    car = Car(car_id="C1", initial_floor=0)
    dispatcher = DispatcherAgent()
    metrics = MetricsCollector()
    
    # Bypass ensure_model by manually setting dispatcher.model to a dummy value
    dispatcher.model = "dummy"
    
    # Disable mock mode for this test, and set provider to gemma to bypass key checks
    os.environ["MOCK_GEMINI"] = "false"
    old_provider = os.environ.get("LLM_PROVIDER")
    os.environ["LLM_PROVIDER"] = "gemma"
    
    # We also need to monkeypatch the Agent __call__ to do nothing (since it calls the model)
    monkeypatch.setattr(Agent, "__call__", lambda *args, **kwargs: None)

    try:
        sim = Simulation(building, car, dispatcher, metrics, verbose=True)
        # Spawn a passenger so dispatcher is called
        p1 = Passenger("P1", source_floor=0, target_floor=3, spawn_time=0)
        building.add_passenger(p1)
        
        # Call dispatcher
        target = dispatcher.dispatch(sim)
        
        # Verify fallback target was returned (using LOOK, which returns 0 to pick up the passenger at 0)
        assert target is not None
        assert target == 0
    finally:
        os.environ["MOCK_GEMINI"] = "true"
        if old_provider is not None:
            os.environ["LLM_PROVIDER"] = old_provider
        else:
            os.environ.pop("LLM_PROVIDER", None)


def test_agentic_dispatcher_group_fallback_on_failure(monkeypatch):
    """Verify that if group agent.structured_output raises an error, the dispatcher falls back to LOOK heuristic."""
    from strands import Agent
    def mock_structured_output(*args, **kwargs):
        raise ValueError("Simulated group structured output failure")
    
    monkeypatch.setattr(Agent, "structured_output", mock_structured_output)

    # Setup simulation
    building = Building(num_floors=5)
    cars = [Car("C1", 0), Car("C2", 0)]
    dispatcher = DispatcherAgent()
    metrics = MetricsCollector()
    
    # Bypass ensure_model by manually setting dispatcher.model to a dummy value
    dispatcher.model = "dummy"
    
    # Disable mock mode for this test, and set provider to gemma to bypass key checks
    os.environ["MOCK_GEMINI"] = "false"
    old_provider = os.environ.get("LLM_PROVIDER")
    os.environ["LLM_PROVIDER"] = "gemma"
    
    # We also need to monkeypatch the Agent __call__ to do nothing (since it calls the model)
    monkeypatch.setattr(Agent, "__call__", lambda *args, **kwargs: None)

    try:
        sim = Simulation(
            building=building,
            car=cars[0],
            dispatcher=dispatcher,
            metrics_collector=metrics,
            verbose=True,
            extra_cars=cars[1:]
        )
        # Spawn a passenger so dispatcher is called
        p1 = Passenger("P1", source_floor=0, target_floor=3, spawn_time=0)
        building.add_passenger(p1)
        
        # Call dispatch_group
        assignments = dispatcher.dispatch_group(sim)
        
        # Verify fallback assignments were returned using Group LOOK heuristic
        assert assignments is not None
        assert "C1" in assignments or "C2" in assignments
    finally:
        os.environ["MOCK_GEMINI"] = "true"
        if old_provider is not None:
            os.environ["LLM_PROVIDER"] = old_provider
        else:
            os.environ.pop("LLM_PROVIDER", None)


def test_agentic_dispatcher_group_stall_guard(monkeypatch):
    """Verify that if group structured_output returns a valid but empty assignments list while work is pending, the stall-guard fills it using Heuristic."""
    from strands import Agent
    from elevatorsim.policy.schemas import GroupDispatchDecision
    
    # Force structured_output to return a valid but empty assignment
    def mock_structured_output(*args, **kwargs):
        return GroupDispatchDecision(assignments=[], reasoning="Simulated empty but valid assignments")
    
    monkeypatch.setattr(Agent, "structured_output", mock_structured_output)

    # Setup simulation
    building = Building(num_floors=5)
    cars = [Car("C1", 0), Car("C2", 0)]
    dispatcher = DispatcherAgent()
    metrics = MetricsCollector()
    
    # Bypass ensure_model by manually setting dispatcher.model to a dummy value
    dispatcher.model = "dummy"
    
    # Disable mock mode for this test, and set provider to gemma to bypass key checks
    os.environ["MOCK_GEMINI"] = "false"
    old_provider = os.environ.get("LLM_PROVIDER")
    os.environ["LLM_PROVIDER"] = "gemma"
    
    # We also need to monkeypatch the Agent __call__ to do nothing (since it calls the model)
    monkeypatch.setattr(Agent, "__call__", lambda *args, **kwargs: None)

    try:
        sim = Simulation(
            building=building,
            car=cars[0],
            dispatcher=dispatcher,
            metrics_collector=metrics,
            verbose=True,
            extra_cars=cars[1:]
        )
        
        # 1. Test case 1: Idle car has onboard passengers
        p_onboard = Passenger("P1", source_floor=0, target_floor=3, spawn_time=0)
        cars[0].board(p_onboard)
        assert cars[0].passenger_count == 1
        
        # Call dispatch_group
        assignments = dispatcher.dispatch_group(sim)
        
        # Verify the stall-guard filled C1's target floor because C1 has onboard passengers
        assert assignments is not None
        assert "C1" in assignments
        assert assignments["C1"] == 3  # LOOK target is passenger target floor 3
        
        # Clear onboard passenger
        cars[0].passengers.clear()
        
        # 2. Test case 2: Outstanding hall calls exist
        p_hall = Passenger("P2", source_floor=2, target_floor=4, spawn_time=0)
        building.add_passenger(p_hall)
        
        # Call dispatch_group again
        assignments = dispatcher.dispatch_group(sim)
        
        # Verify the stall-guard filled C1 or C2's target to pick up the hall call
        assert assignments is not None
        assert len(assignments) > 0
        
    finally:
        os.environ["MOCK_GEMINI"] = "true"
        if old_provider is not None:
            os.environ["LLM_PROVIDER"] = old_provider
        else:
            os.environ.pop("LLM_PROVIDER", None)



