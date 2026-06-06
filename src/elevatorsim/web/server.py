# src/elevatorsim/web/server.py
"""FastAPI web server exposing simulation endpoints and serving preset caches."""

import os
import sys
import json
import logging
import random
import asyncio
from typing import Dict, Any, List, Optional
from contextlib import contextmanager
from pydantic import BaseModel, Field

from fastapi import FastAPI, HTTPException, status, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Ensure project root is in python path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from elevatorsim.core.building import Building  # noqa: E402
from elevatorsim.core.car import Car  # noqa: E402
from elevatorsim.core.metrics import MetricsCollector  # noqa: E402
from elevatorsim.core.passenger import Passenger  # noqa: E402
from elevatorsim.core.simulation import Simulation  # noqa: E402
from elevatorsim.core.traffic import TrafficGenerator  # noqa: E402
from elevatorsim.policy.heuristic import HeuristicDispatcher, GroupHeuristicDispatcher  # noqa: E402
from elevatorsim.policy.agentic import DispatcherAgent  # noqa: E402
from elevatorsim.config import seed_rng, get_gemini_api_key  # noqa: E402
from elevatorsim.core.events import Event  # noqa: E402

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("elevatorsim.web")

app = FastAPI(
    title="Elevator Simulator API",
    description="Backend API for the A/B Elevator Simulator Dashboard",
    version="0.2.0"
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
    num_cars: int = Field(default=1, description="Number of elevator cars (1-6)")
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


def _build_car_bank(num_cars: int) -> List[Car]:
    """Create a bank of elevator cars starting at floor 0."""
    return [Car(car_id=f"C{i+1}", initial_floor=0) for i in range(num_cars)]


def _make_simulation(
    dispatcher: Any,
    num_floors: int,
    num_cars: int,
    arrival_rate: float,
    profile: str,
    traffic_generator: Optional[Any] = None,
    verbose: bool = False,
) -> Simulation:
    """Factory to construct a Simulation with the right car bank."""
    building = Building(num_floors=num_floors)
    cars = _build_car_bank(num_cars)
    metrics = MetricsCollector()

    if traffic_generator is None:
        traffic_generator = TrafficGenerator(num_floors=num_floors, arrival_rate=arrival_rate, profile=profile)

    sim = Simulation(
        building=building,
        car=cars[0],
        dispatcher=dispatcher,
        metrics_collector=metrics,
        traffic_generator=traffic_generator,
        verbose=verbose,
        extra_cars=cars[1:] if len(cars) > 1 else None,
    )
    return sim


def run_single_simulation(
    dispatcher: Any,
    seed: int,
    num_floors: int,
    arrival_rate: float,
    profile: str,
    max_ticks: int,
    num_cars: int = 1,
) -> Dict[str, Any]:
    """Execute a simulation run and return serialized events and final metrics."""
    seed_rng(seed)

    sim = _make_simulation(
        dispatcher=dispatcher,
        num_floors=num_floors,
        num_cars=num_cars,
        arrival_rate=arrival_rate,
        profile=profile,
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
        "metrics": sim.metrics.get_summary()
    }

@app.post("/api/simulate")
def run_simulation(req: SimulationRequest):
    """Run Heuristic and Agentic simulations for the given parameters."""
    logger.info(f"Received simulation request: profile={req.profile}, seed={req.seed}, ticks={req.max_ticks}, cars={req.num_cars}")
    
    if req.num_floors < 2 or req.num_floors > 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Number of floors must be between 2 and 10."
        )

    if req.num_cars < 1 or req.num_cars > 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Number of cars must be between 1 and 6."
        )
        
    # 1. Run LOOK Heuristic (always runs instantly)
    try:
        # Use group dispatcher for multi-car, legacy for single-car
        if req.num_cars > 1:
            heuristic_dispatcher = GroupHeuristicDispatcher()
        else:
            heuristic_dispatcher = HeuristicDispatcher()

        heuristic_result = run_single_simulation(
            dispatcher=heuristic_dispatcher,
            seed=req.seed,
            num_floors=req.num_floors,
            arrival_rate=req.arrival_rate,
            profile=req.profile,
            max_ticks=req.max_ticks,
            num_cars=req.num_cars,
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
                        max_ticks=req.max_ticks,
                        num_cars=req.num_cars,
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


@app.websocket("/api/ws/simulate")
async def websocket_simulate(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket connection established.")
    
    # State variables for the WebSocket session
    look_sim: Optional[Simulation] = None
    gemini_sim: Optional[Simulation] = None
    traffic_generator: Optional[TrafficGenerator] = None
    ws_rng: Optional[random.Random] = None
    
    seed = 42
    num_floors = 5
    num_cars = 1
    arrival_rate = 0.2
    profile = "UNIFORM"
    max_ticks = 50
    api_key: Optional[str] = None
    run_agentic = True
    passenger_counter = 0
    
    # Lists to collect events for the current tick
    look_tick_events = []
    gemini_tick_events = []
    
    def look_listener(ev):
        look_tick_events.append(serialize_event(ev))
        
    def gemini_listener(ev):
        gemini_tick_events.append(serialize_event(ev))
        
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            msg_type = message.get("type")
            
            if msg_type == "init":
                config = message.get("config", {})
                seed = config.get("seed", 42)
                num_floors = config.get("num_floors", 5)
                num_cars = config.get("num_cars", 1)
                arrival_rate = config.get("arrival_rate", 0.2)
                profile = config.get("profile", "UNIFORM")
                run_agentic = config.get("run_agentic", True)
                api_key = config.get("api_key")
                max_ticks = config.get("max_ticks", 50)
                
                ws_rng = random.Random(seed)
                traffic_generator = TrafficGenerator(num_floors=num_floors, arrival_rate=arrival_rate, profile=profile)
                passenger_counter = 0
                
                # Select dispatcher based on car count
                if num_cars > 1:
                    look_dispatcher = GroupHeuristicDispatcher()
                else:
                    look_dispatcher = HeuristicDispatcher()
                
                # Initialize LOOK simulation
                look_cars = _build_car_bank(num_cars)
                look_building = Building(num_floors=num_floors)
                look_metrics = MetricsCollector()
                look_sim = Simulation(
                    building=look_building,
                    car=look_cars[0],
                    dispatcher=look_dispatcher,
                    metrics_collector=look_metrics,
                    traffic_generator=None,
                    verbose=False,
                    extra_cars=look_cars[1:] if len(look_cars) > 1 else None,
                )
                look_tick_events = []
                look_sim.register_listener(look_listener)
                
                # Initialize Gemini if enabled
                gemini_sim = None
                gemini_tick_events = []
                if run_agentic:
                    gemini_cars = _build_car_bank(num_cars)
                    gemini_building = Building(num_floors=num_floors)
                    gemini_metrics = MetricsCollector()
                    gemini_dispatcher = DispatcherAgent()
                    gemini_sim = Simulation(
                        building=gemini_building,
                        car=gemini_cars[0],
                        dispatcher=gemini_dispatcher,
                        metrics_collector=gemini_metrics,
                        traffic_generator=None,
                        verbose=False,
                        extra_cars=gemini_cars[1:] if len(gemini_cars) > 1 else None,
                    )
                    gemini_sim.register_listener(gemini_listener)
                    
                # Broadcast the initial state (tick 0)
                await websocket.send_json({
                    "type": "state",
                    "current_tick": 0,
                    "num_cars": num_cars,
                    "heuristic_events": [],
                    "agentic_events": [],
                    "agentic_error": None
                })
                
            elif msg_type == "step":
                if look_sim is None:
                    await websocket.send_json({"type": "error", "message": "Simulation not initialized."})
                    continue
                
                current_tick = look_sim.current_time
                next_tick = current_tick + 1
                
                if next_tick > max_ticks:
                    await websocket.send_json({"type": "error", "message": "Maximum tick limit reached."})
                    continue
                
                look_tick_events.clear()
                gemini_tick_events.clear()
                agentic_error = None
                
                # Generate stochastic arrivals for next_tick
                if traffic_generator is not None and ws_rng is not None:
                    new_passengers = traffic_generator.generate(next_tick, ws_rng)
                    for passenger in new_passengers:
                        # Schedule in both sims
                        p_look = Passenger(
                            passenger_id=passenger.passenger_id,
                            source_floor=passenger.source_floor,
                            target_floor=passenger.target_floor,
                            spawn_time=passenger.spawn_time
                        )
                        look_sim.schedule_passenger(next_tick, p_look)
                        
                        if gemini_sim is not None:
                            p_gemini = Passenger(
                                passenger_id=passenger.passenger_id,
                                source_floor=passenger.source_floor,
                                target_floor=passenger.target_floor,
                                spawn_time=passenger.spawn_time
                            )
                            gemini_sim.schedule_passenger(next_tick, p_gemini)
                
                # Step LOOK Heuristic in threadpool
                await asyncio.to_thread(look_sim.step)
                
                # Step Gemini Agent in threadpool if enabled
                if gemini_sim is not None:
                    # Check if any car in the agent sim is about to need a dispatch decision
                    is_thinking = any(
                        c.door_state == "CLOSED" and c.target_floor is None
                        for c in gemini_sim.cars
                    ) and (gemini_sim.building.has_pending_calls() or any(c.passenger_count > 0 for c in gemini_sim.cars))
                    
                    if is_thinking:
                        await websocket.send_json({"type": "thinking"})
                        
                    effective_key = api_key or get_gemini_api_key()
                    if not effective_key:
                        agentic_error = "GEMINI_API_KEY is not configured on the server, and no key was provided in the UI settings."
                        logger.warning("Skipping agentic step: no API key.")
                    else:
                        with override_env_key(effective_key):
                            try:
                                await asyncio.to_thread(gemini_sim.step)
                            except Exception as e:
                                logger.error(f"Agentic step failed: {e}")
                                agentic_error = str(e)
                
                # Send the state update with events accumulated in this tick
                await websocket.send_json({
                    "type": "state",
                    "current_tick": next_tick,
                    "num_cars": num_cars,
                    "heuristic_events": look_tick_events,
                    "agentic_events": gemini_tick_events,
                    "agentic_error": agentic_error
                })
                
            elif msg_type == "spawn":
                if look_sim is None:
                    await websocket.send_json({"type": "error", "message": "Simulation not initialized."})
                    continue
                
                source = message.get("source")
                target = message.get("target")
                
                if source is None or target is None:
                    await websocket.send_json({"type": "error", "message": "Missing source or target floor."})
                    continue
                
                passenger_counter += 1
                manual_id = f"P_man_{passenger_counter}"
                
                # Schedule to spawn at the NEXT tick immediately
                current_tick = look_sim.current_time
                spawn_tick = current_tick + 1
                
                p_look = Passenger(
                    passenger_id=manual_id,
                    source_floor=source,
                    target_floor=target,
                    spawn_time=spawn_tick
                )
                look_sim.schedule_passenger(spawn_tick, p_look)
                
                p_gemini = Passenger(
                    passenger_id=manual_id,
                    source_floor=source,
                    target_floor=target,
                    spawn_time=spawn_tick
                )
                if gemini_sim is not None:
                    gemini_sim.schedule_passenger(spawn_tick, p_gemini)
                
                # Send a notification back confirming spawn schedule
                # The actual spawn events will fire and be streamed during the next 'step'
                await websocket.send_json({
                    "type": "spawn_confirm",
                    "passenger_id": manual_id,
                    "source": source,
                    "target": target
                })
                
            elif msg_type == "config":
                # Handle config updates mid-simulation (e.g. toggling agentic mode)
                run_agentic = message.get("run_agentic", run_agentic)
                api_key = message.get("api_key", api_key)
                
                if not run_agentic:
                    gemini_sim = None
                elif gemini_sim is None and look_sim is not None:
                    # Dynamically instantiate Gemini if it was disabled but is now enabled
                    gemini_cars = _build_car_bank(num_cars)
                    gemini_building = Building(num_floors=num_floors)
                    gemini_metrics = MetricsCollector()
                    gemini_dispatcher = DispatcherAgent()
                    gemini_sim = Simulation(
                        building=gemini_building,
                        car=gemini_cars[0],
                        dispatcher=gemini_dispatcher,
                        metrics_collector=gemini_metrics,
                        traffic_generator=None,
                        verbose=False,
                        extra_cars=gemini_cars[1:] if len(gemini_cars) > 1 else None,
                    )
                    gemini_sim.register_listener(gemini_listener)
                    # Sync current tick of gemini with look_sim
                    gemini_sim.current_time = look_sim.current_time
                    
    except WebSocketDisconnect:
        logger.info("WebSocket connection disconnected.")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": f"Server error: {e}"})
        except Exception:
            pass


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
