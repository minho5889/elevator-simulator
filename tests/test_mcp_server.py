# tests/test_mcp_server.py
"""Unit tests for the FastMCP ElevatorSim server tools."""

import json
import os
import pytest
from elevatorsim.mcp.server import (
    init_simulation,
    step_simulation,
    get_status,
    get_metrics,
    spawn_passenger
)


@pytest.fixture(autouse=True)
def force_mock_gemini():
    """Ensure mock Gemini is enabled to avoid actual LLM calls during MCP tests."""
    old_val = os.environ.get("MOCK_GEMINI")
    os.environ["MOCK_GEMINI"] = "true"
    yield
    if old_val is not None:
        os.environ["MOCK_GEMINI"] = old_val
    else:
        os.environ.pop("MOCK_GEMINI", None)


def test_mcp_simulation_lifecycle():
    """Test standard simulation setup, stepping, spawning, and metrics query via MCP tools."""
    # 1. Initialize simulation
    init_res = init_simulation(
        seed=42,
        num_floors=5,
        num_cars=2,
        arrival_rate=0.0,  # Turn off stochastic arrivals for deterministic test
        profile="UNIFORM",
        max_ticks=20
    )
    init_data = json.loads(init_res)
    assert init_data["status"] == "Initialized"
    assert init_data["config"]["num_cars"] == 2
    
    # 2. Get status (should be tick 0, all idle)
    status_res = get_status()
    status_data = json.loads(status_res)
    assert status_data["heuristic_state"]["current_time"] == 0
    assert "C1" in status_data["heuristic_state"]["cars"]
    assert "C2" in status_data["heuristic_state"]["cars"]
    
    # 3. Spawn a passenger manually at Floor 1 heading to Floor 4
    spawn_res = spawn_passenger(source_floor=1, target_floor=4)
    spawn_data = json.loads(spawn_res)
    assert spawn_data["source"] == 1
    assert spawn_data["target"] == 4
    passenger_id = spawn_data["passenger_id"]
    
    # 4. Step simulation by 1 tick (passenger will spawn at tick 1)
    step_res = step_simulation(ticks=1)
    step_data = json.loads(step_res)
    assert step_data["current_tick"] == 1
    
    # Check that passenger is now in queue in both simulators
    status_res2 = get_status()
    status_data2 = json.loads(status_res2)
    h_queue_1 = status_data2["heuristic_state"]["floor_queues"]["1"]
    a_queue_1 = status_data2["agentic_state"]["floor_queues"]["1"]
    
    assert any(p["id"] == passenger_id for p in h_queue_1)
    assert any(p["id"] == passenger_id for p in a_queue_1)
    
    # 5. Get metrics
    metrics_res = get_metrics()
    metrics_data = json.loads(metrics_res)
    assert "heuristic_metrics" in metrics_data
    assert "agentic_metrics" in metrics_data
