# tests/test_agents_local.py
"""Unit tests verifying local-LLM (Ollama / Gemma 4) provider integration."""

import pytest
import httpx
from elevatorsim.core.building import Building
from elevatorsim.core.car import Car
from elevatorsim.core.passenger import Passenger
from elevatorsim.core.metrics import MetricsCollector
from elevatorsim.core.simulation import Simulation
from elevatorsim.policy.agentic import DispatcherAgent
from elevatorsim.config import OLLAMA_HOST, LLM_PROVIDER


def is_ollama_ready() -> bool:
    """Helper to check if the Ollama server is reachable and responsive."""
    try:
        # Check standard Ollama API health endpoint
        response = httpx.get(f"{OLLAMA_HOST}/api/tags", timeout=1.0)
        return response.status_code == 200
    except Exception:
        return False


# Skip all tests in this file if LLM_PROVIDER is not gemma or Ollama server is not running
pytestmark = pytest.mark.skipif(
    LLM_PROVIDER != "gemma" or not is_ollama_ready(),
    reason="Ollama server not running or LLM_PROVIDER is not 'gemma'"
)


def test_local_agentic_dispatcher_single_car():
    """Verify local agentic dispatcher can complete a single-car scenario."""
    building = Building(num_floors=5)
    car = Car(car_id="C1", initial_floor=0)
    dispatcher = DispatcherAgent()
    metrics = MetricsCollector()
    
    sim = Simulation(building, car, dispatcher, metrics, verbose=True)

    # Spawn passenger
    p1 = Passenger("P1", source_floor=0, target_floor=3, spawn_time=1)
    sim.schedule_passenger(1, p1)

    # Run for a few ticks to test the connection/inference loop
    sim.run_until_complete(max_ticks=10)

    # Ensure simulation progresses
    summary = metrics.get_summary()
    assert summary["total_ticks"] > 0


def test_local_agentic_dispatcher_direct():
    """Verify local agentic dispatcher can perform a single direct dispatch call."""
    building = Building(num_floors=5)
    car = Car(car_id="C1", initial_floor=0)
    dispatcher = DispatcherAgent()
    metrics = MetricsCollector()
    
    sim = Simulation(building, car, dispatcher, metrics, verbose=False)
    p1 = Passenger("P1", source_floor=0, target_floor=3, spawn_time=0)
    building.add_passenger(p1)

    target = dispatcher.dispatch(sim)
    assert target is not None
    assert 0 <= target < building.num_floors
