# tests/test_web_server.py
"""Unit tests for the FastAPI backend simulator web server."""

from fastapi.testclient import TestClient
from elevatorsim.web.server import app

client = TestClient(app)

def test_api_presets():
    """Verify presets endpoint returns the pre-compiled scenarios."""
    response = client.get("/api/presets")
    assert response.status_code == 200
    data = response.json()
    
    # We generated quiet_day, morning_rush, evening_rush caches
    assert "quiet_day" in data
    assert "morning_rush" in data
    assert "evening_rush" in data
    
    # Check quiet_day cache structure
    quiet = data["quiet_day"]
    assert quiet["title"] == "Uniform Quiet Day"
    assert quiet["profile"] == "UNIFORM"
    assert "heuristic" in quiet
    assert "events" in quiet["heuristic"]
    assert len(quiet["heuristic"]["events"]) > 0

def test_api_simulate_heuristic():
    """Verify simulate endpoint runs heuristic LOOK instantly."""
    payload = {
        "seed": 42,
        "num_floors": 5,
        "arrival_rate": 0.2,
        "profile": "UNIFORM",
        "max_ticks": 20,
        "run_agentic": False  # Disable agentic to bypass API calls in offline test
    }
    
    response = client.post("/api/simulate", json=payload)
    assert response.status_code == 200
    data = response.json()
    
    # Check heuristic results
    assert "heuristic" in data
    assert data["heuristic"] is not None
    assert "events" in data["heuristic"]
    assert "metrics" in data["heuristic"]
    assert data["heuristic"]["metrics"]["total_ticks"] > 0
    
    # Agentic should be skipped as requested
    assert data["agentic"] is None
    assert data["agentic_error"] is None

def test_api_simulate_validation():
    """Verify simulate endpoint rejects invalid floor numbers."""
    payload = {
        "seed": 42,
        "num_floors": 12,  # Invalid: max is 10
        "arrival_rate": 0.2,
        "profile": "UNIFORM",
        "max_ticks": 20,
        "run_agentic": False
    }
    
    response = client.post("/api/simulate", json=payload)
    assert response.status_code == 400
    assert "floors" in response.json()["detail"].lower()

def test_api_test_key_invalid():
    """Verify test-key endpoint returns failure for a dummy key."""
    payload = {
        "api_key": "invalid_dummy_key_format_123"
    }
    
    response = client.post("/api/test-key", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert "message" in data


def test_websocket_simulate():
    """Verify stateful WebSocket connection, initialization, stepping, and passenger spawning."""
    with client.websocket_connect("/api/ws/simulate") as websocket:
        # 1. Initialize
        websocket.send_json({
            "type": "init",
            "config": {
                "seed": 42,
                "num_floors": 5,
                "arrival_rate": 0.0,  # Turn off stochastic arrivals for deterministic test
                "profile": "UNIFORM",
                "max_ticks": 10,
                "run_agentic": False  # Disable agentic to run purely offline
            }
        })
        
        # Receive initial state
        init_data = websocket.receive_json()
        assert init_data["type"] == "state"
        assert init_data["current_tick"] == 0
        assert init_data["heuristic_events"] == []
        
        # 2. Step 1 (should be empty since arrival rate is 0)
        websocket.send_json({"type": "step"})
        step_data = websocket.receive_json()
        assert step_data["type"] == "state"
        assert step_data["current_tick"] == 1
        assert step_data["heuristic_events"] == []
        
        # 3. Spawn a passenger manually at Floor 3 heading to Floor 0
        websocket.send_json({
            "type": "spawn",
            "source": 3,
            "target": 0
        })
        spawn_data = websocket.receive_json()
        assert spawn_data["type"] == "spawn_confirm"
        assert spawn_data["source"] == 3
        assert spawn_data["target"] == 0
        passenger_id = spawn_data["passenger_id"]
        assert passenger_id.startswith("P_man_")
        
        # 4. Step 2 (passenger should spawn and call registered)
        websocket.send_json({"type": "step"})
        step2_data = websocket.receive_json()
        assert step2_data["type"] == "state"
        assert step2_data["current_tick"] == 2
        
        events = step2_data["heuristic_events"]
        assert len(events) >= 2
        # Verify PassengerSpawned and CallRegistered are in the events
        spawn_ev = next((e for e in events if e["event_type"] == "PassengerSpawned"), None)
        call_ev = next((e for e in events if e["event_type"] == "CallRegistered"), None)
        
        assert spawn_ev is not None
        assert spawn_ev["passenger_id"] == passenger_id
        assert spawn_ev["source"] == 3
        assert spawn_ev["target"] == 0
        
        assert call_ev is not None
        assert call_ev["floor"] == 3

