# src/elevatorsim/web/server.py
"""FastAPI web server exposing simulation endpoints and serving preset caches."""

import os
import sys
import json
import logging
from typing import Dict, Any, List, Optional
from contextlib import contextmanager
from pydantic import BaseModel, Field

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Ensure project root is in python path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from elevatorsim.core.building import Building  # noqa: E402
from elevatorsim.core.car import Car  # noqa: E402
from elevatorsim.core.metrics import MetricsCollector  # noqa: E402
from elevatorsim.core.simulation import Simulation  # noqa: E402
from elevatorsim.core.traffic import TrafficGenerator  # noqa: E402
from elevatorsim.policy.heuristic import HeuristicDispatcher  # noqa: E402
from elevatorsim.policy.agentic import DispatcherAgent  # noqa: E402
from elevatorsim.config import seed_rng, get_gemini_api_key  # noqa: E402
from elevatorsim.core.events import Event  # noqa: E402

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("elevatorsim.web")

app = FastAPI(
    title="Elevator Simulator API",
    description="Backend API for the A/B Elevator Simulator Dashboard",
    version="0.1.0"
)

# Enable CORS for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cache Directory Setup
CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

class SimulationRequest(BaseModel):
    seed: int = Field(default=42, description="RNG Seed for reproducibility")
    num_floors: int = Field(default=5, description="Number of floors (5-10)")
    arrival_rate: float = Field(default=0.2, description="Arrival rate probability (0.0 to 1.0)")
    profile: str = Field(default="UNIFORM", description="UNIFORM, DOWN_PEAK, or UP_PEAK")
    max_ticks: int = Field(default=50, description="Maximum simulation duration")
    api_key: Optional[str] = Field(default=None, description="Optional Gemini API key")
    run_agentic: bool = Field(default=True, description="Whether to run the Agentic simulation")

class KeyCheckRequest(BaseModel):
    api_key: str = Field(..., description="API Key to test")

@contextmanager
def override_env_key(key: Optional[str]):
    """Temporarily override GEMINI_API_KEY environment variable."""
    old_key = os.environ.get("GEMINI_API_KEY")
    if key is not None:
        os.environ["GEMINI_API_KEY"] = key.strip()
    try:
        yield
    finally:
        if old_key is not None:
            os.environ["GEMINI_API_KEY"] = old_key
        else:
            os.environ.pop("GEMINI_API_KEY", None)

def serialize_event(event: Event) -> Dict[str, Any]:
    """Serialize a simulation event object into a JSON-compatible dictionary."""
    data = {
        "event_type": event.__class__.__name__,
        "message": str(event),
        "time": event.time
    }
    for k, v in event.__dict__.items():
        if not k.startswith("_"):
            data[k] = v
    return data

def run_single_simulation(
    dispatcher: Any,
    seed: int,
    num_floors: int,
    arrival_rate: float,
    profile: str,
    max_ticks: int
) -> Dict[str, Any]:
    """Execute a simulation run and return serialized events and final metrics."""
    seed_rng(seed)
    
    building = Building(num_floors=num_floors)
    car = Car(car_id="C1", initial_floor=0)
    metrics = MetricsCollector()
    traffic = TrafficGenerator(num_floors=num_floors, arrival_rate=arrival_rate, profile=profile)
    
    # Instantiate simulation in silent mode (verbose=False) to avoid stdout spam
    sim = Simulation(
        building=building,
        car=car,
        dispatcher=dispatcher,
        metrics_collector=metrics,
        traffic_generator=traffic,
        verbose=False
    )
    
    # List to collect events
    events_log: List[Dict[str, Any]] = []
    
    # Custom listener to capture events
    def event_listener(ev: Event):
        events_log.append(serialize_event(ev))
        
    sim.register_listener(event_listener)
    
    # Run the simulation
    sim.run_until_complete(max_ticks=max_ticks)
    
    return {
        "events": events_log,
        "metrics": metrics.get_summary()
    }

@app.post("/api/simulate")
def run_simulation(req: SimulationRequest):
    """Run Heuristic and Agentic simulations for the given parameters."""
    logger.info(f"Received simulation request: profile={req.profile}, seed={req.seed}, ticks={req.max_ticks}")
    
    if req.num_floors < 2 or req.num_floors > 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Number of floors must be between 2 and 10."
        )
        
    # 1. Run LOOK Heuristic (always runs instantly)
    try:
        heuristic_dispatcher = HeuristicDispatcher()
        heuristic_result = run_single_simulation(
            dispatcher=heuristic_dispatcher,
            seed=req.seed,
            num_floors=req.num_floors,
            arrival_rate=req.arrival_rate,
            profile=req.profile,
            max_ticks=req.max_ticks
        )
    except Exception as e:
        logger.error(f"Heuristic simulation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Heuristic simulation failed: {e}"
        )
        
    # 2. Run Agentic (Gemini) simulation
    agentic_result = None
    agentic_error = None
    
    if req.run_agentic:
        # Determine the API key to use
        effective_key = req.api_key or get_gemini_api_key()
        
        if not effective_key:
            agentic_error = "GEMINI_API_KEY is not configured on the server, and no key was provided in the UI settings."
            logger.warning("Skipping agentic run: no API key.")
        else:
            with override_env_key(effective_key):
                try:
                    agentic_dispatcher = DispatcherAgent()
                    agentic_result = run_single_simulation(
                        dispatcher=agentic_dispatcher,
                        seed=req.seed,
                        num_floors=req.num_floors,
                        arrival_rate=req.arrival_rate,
                        profile=req.profile,
                        max_ticks=req.max_ticks
                    )
                except Exception as e:
                    logger.error(f"Agentic simulation failed: {e}")
                    agentic_error = str(e)
                    
    return {
        "heuristic": heuristic_result,
        "agentic": agentic_result,
        "agentic_error": agentic_error
    }

@app.post("/api/test-key")
def test_key(req: KeyCheckRequest):
    """Verify Gemini API key connectivity."""
    logger.info("Testing Gemini API key connectivity...")
    
    from google import genai
    try:
        client = genai.Client(api_key=req.api_key.strip())
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents="Respond with 'OK' if you can read this.",
        )
        if "OK" in response.text or response.text.strip() != "":
            return {"success": True, "message": "API Key is valid!"}
        else:
            return {"success": False, "message": f"Unexpected API response: {response.text}"}
    except Exception as e:
        logger.error(f"API key test failed: {e}")
        return {"success": False, "message": str(e)}

@app.get("/api/presets")
def get_presets():
    """Retrieve pre-compiled scenario runs from cache to avoid API calls."""
    presets = {}
    preset_files = {
        "quiet_day": "preset_quiet_day.json",
        "morning_rush": "preset_morning_rush.json",
        "evening_rush": "preset_evening_rush.json"
    }
    
    for name, filename in preset_files.items():
        filepath = os.path.join(CACHE_DIR, filename)
        if os.path.exists(filepath):
            try:
                with open(filepath, "r") as f:
                    presets[name] = json.load(f)
            except Exception as e:
                logger.error(f"Failed to read preset cache file {filename}: {e}")
        else:
            logger.warning(f"Preset cache file {filename} does not exist. Please run cache_generator.py first.")
            
    return presets

# Mount frontend build folder once available
frontend_build_path = os.path.join(os.path.dirname(__file__), "frontend", "dist")
if os.path.exists(frontend_build_path):
    app.mount("/", StaticFiles(directory=frontend_build_path, html=True), name="static")
else:
    @app.get("/")
    def read_root():
        return {
            "message": "Elevator Simulator API is running. The React frontend is not compiled yet. "
                       "Please run the Vite dev server inside src/elevatorsim/web/frontend/ or build the assets."
        }

if __name__ == "__main__":
    import uvicorn
    # Read port from environment, default to 8000
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
