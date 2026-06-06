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
