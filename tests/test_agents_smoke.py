# tests/test_agents_smoke.py
"""Smoke test for the agentic policy dispatcher.

Skips dynamically if no GEMINI_API_KEY is found in the environment.
"""

import pytest
from elevatorsim.core.building import Building
from elevatorsim.core.car import Car
from elevatorsim.core.passenger import Passenger
from elevatorsim.core.metrics import MetricsCollector
from elevatorsim.core.simulation import Simulation
from elevatorsim.policy.agentic import DispatcherAgent
from elevatorsim.config import get_gemini_api_key

@pytest.mark.skipif(
    get_gemini_api_key() is None,
    reason="GEMINI_API_KEY is not configured in the environment. Skipping live model tests."
)
def test_agentic_dispatcher_smoke():
    """Verify DispatcherAgent successfully performs a live dispatch call."""
    building = Building(num_floors=5)
    car = Car(car_id="C1", initial_floor=0)
    dispatcher = DispatcherAgent()
    metrics = MetricsCollector()
    
    sim = Simulation(building, car, dispatcher, metrics, verbose=False)
    
    # Register a single waiting passenger
    p1 = Passenger("P1", source_floor=0, target_floor=3, spawn_time=1)
    sim.schedule_passenger(1, p1)
    
    # Advance simulation to tick 1 to trigger passenger spawn
    sim.step()
    
    # The car is at floor 0, passenger waiting at floor 0.
    # Dispatcher should be called to select a target.
    target = dispatcher.dispatch(sim)
    
    assert target is not None
    assert 0 <= target <= 4
    print(f"\n[SMOKE TEST SUCCESS] Agent chose target floor: {target}")
