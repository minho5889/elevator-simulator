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


def test_api_simulate_mock_provider():
    """Verify simulate endpoint runs successfully using the agentic mock provider without requiring GEMINI_API_KEY."""
    payload = {
        "seed": 42,
        "num_floors": 5,
        "arrival_rate": 0.2,
        "profile": "UNIFORM",
        "max_ticks": 10,
        "run_agentic": True,
        "llm_provider": "mock"
    }
    
    # Enable mock Gemini environment variable to bypass key validation
    import os
    old_mock = os.environ.get("MOCK_GEMINI")
    os.environ["MOCK_GEMINI"] = "true"
    
    try:
        response = client.post("/api/simulate", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        assert "heuristic" in data
        assert "agentic" in data
        assert data["agentic"] is not None
        assert data["agentic_error"] is None
        assert "events" in data["agentic"]
    finally:
        if old_mock is not None:
            os.environ["MOCK_GEMINI"] = old_mock
        else:
            os.environ.pop("MOCK_GEMINI", None)


def test_api_simulate_gemma_provider_offline(monkeypatch):
    """Verify simulate endpoint successfully bypasses API key checks and executes simulation using gemma provider (mocked structured output)."""
    from strands import Agent
    from elevatorsim.policy.schemas import DispatchDecision, GroupDispatchDecision, CarAssignment

    # Mock structured output to return whichever schema the dispatcher actually
    # requests. The web path routes even single-car sims through dispatch_group
    # (DispatcherAgent exposes dispatch_group), so it asks for GroupDispatchDecision,
    # not the single-car DispatchDecision.
    def _fake_structured_output(self, output_model, *args, **kwargs):
        if output_model is GroupDispatchDecision:
            return GroupDispatchDecision(
                assignments=[CarAssignment(car_id="C1", target_floor=0)],
                reasoning="Simulated local model decision",
            )
        return DispatchDecision(target_floor=0, reasoning="Simulated local model decision")

    monkeypatch.setattr(Agent, "structured_output", _fake_structured_output)
    # Monkeypatch Agent __call__ to do nothing (since it calls the model)
    monkeypatch.setattr(Agent, "__call__", lambda *args, **kwargs: None)
    
    # Save environment state
    import os
    old_key = os.environ.get("GEMINI_API_KEY")
    os.environ.pop("GEMINI_API_KEY", None)  # Ensure no key exists
    
    payload = {
        "seed": 42,
        "num_floors": 5,
        "arrival_rate": 0.2,
        "profile": "UNIFORM",
        "max_ticks": 5,
        "run_agentic": True,
        "llm_provider": "gemma",
        "ollama_host": "http://dummy-host:11434",
        "ollama_model_id": "dummy-model"
    }
    
    try:
        response = client.post("/api/simulate", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        assert data["agentic"] is not None
        assert data["agentic_error"] is None
        assert len(data["agentic"]["events"]) > 0
    finally:
        if old_key is not None:
            os.environ["GEMINI_API_KEY"] = old_key


def test_dispatcher_agent_concurrency_isolation():
    """Verify that DispatcherAgent instances are fully isolated and do not mutate environment variables."""
    import os
    from elevatorsim.policy.agentic import DispatcherAgent
    from elevatorsim.config import get_llm_provider

    # Clear environment variables to verify fallbacks work and don't collide
    old_provider = os.environ.get("LLM_PROVIDER")
    os.environ.pop("LLM_PROVIDER", None)

    try:
        agent_a = DispatcherAgent(
            provider="gemma",
            ollama_host="http://host-a:11434",
            ollama_model_id="model-a"
        )
        agent_b = DispatcherAgent(
            provider="mock"
        )

        assert agent_a.provider == "gemma"
        assert agent_a.ollama_host == "http://host-a:11434"
        assert agent_a.ollama_model_id == "model-a"
        assert agent_b.provider == "mock"

        # Check mock mode checks don't interfere
        assert agent_a._is_mock_mode() is False
        assert agent_b._is_mock_mode() is True

        # Environment remains unmutated
        assert "LLM_PROVIDER" not in os.environ
    finally:
        if old_provider is not None:
            os.environ["LLM_PROVIDER"] = old_provider



