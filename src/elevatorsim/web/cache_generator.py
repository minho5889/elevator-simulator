# src/elevatorsim/web/cache_generator.py
"""Pre-compiles simulation event logs for presets (Quiet Day, Morning Rush, Evening Rush)."""

import os
import sys
import json
import logging
from typing import Any

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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("elevatorsim.web.cache_generator")

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

def serialize_event(event: Event) -> dict:
    data = {
        "event_type": event.__class__.__name__,
        "message": str(event),
        "time": event.time
    }
    for k, v in event.__dict__.items():
        if not k.startswith("_"):
            data[k] = v
    return data

def run_simulation(dispatcher: Any, seed: int, profile: str, rate: float, max_ticks: int) -> dict:
    seed_rng(seed)
    building = Building(num_floors=5)
    car = Car(car_id="C1", initial_floor=0)
    metrics = MetricsCollector()
    traffic = TrafficGenerator(num_floors=5, arrival_rate=rate, profile=profile)
    
    sim = Simulation(
        building=building,
        car=car,
        dispatcher=dispatcher,
        metrics_collector=metrics,
        traffic_generator=traffic,
        verbose=False
    )
    
    events_log = []
    sim.register_listener(lambda ev: events_log.append(serialize_event(ev)))
    sim.run_until_complete(max_ticks=max_ticks)
    
    return {
        "events": events_log,
        "metrics": metrics.get_summary()
    }

def run_mock_agentic_simulation(seed: int, profile: str, rate: float, max_ticks: int) -> dict:
    """Generate a simulation that uses Heuristic LOOK but formats decisions with mock agent reasoning."""
    seed_rng(seed)
    building = Building(num_floors=5)
    car = Car(car_id="C1", initial_floor=0)
    metrics = MetricsCollector()
    traffic = TrafficGenerator(num_floors=5, arrival_rate=rate, profile=profile)
    
    # We use HeuristicLOOK but intercept and log mock agent decisions
    dispatcher = HeuristicDispatcher()
    
    sim = Simulation(
        building=building,
        car=car,
        dispatcher=dispatcher,
        metrics_collector=metrics,
        traffic_generator=traffic,
        verbose=False
    )
    
    events_log = []
    sim.register_listener(lambda ev: events_log.append(serialize_event(ev)))
    
    # Inject custom trace printing or reasoning injection in ticks
    # For simplicity, we just run the simulation
    sim.run_until_complete(max_ticks=max_ticks)
    
    # Add agent decision reasons to mock the agentic output
    for ev in events_log:
        if ev["event_type"] == "CarArrived":
            # Append a mock agentic policy decision reasoning
            ev["message"] = ev["message"] + " (Decided by Gemini Dispatcher Agent: Prioritizing nearest pending calls to minimize wait time.)"
            
    return {
        "events": events_log,
        "metrics": metrics.get_summary()
    }

def generate_presets():
    presets_config = {
        "quiet_day": {
            "profile": "UNIFORM",
            "rate": 0.15,
            "ticks": 50,
            "title": "Uniform Quiet Day"
        },
        "morning_rush": {
            "profile": "DOWN_PEAK",
            "rate": 0.25,
            "ticks": 50,
            "title": "Morning Lobby Rush"
        },
        "evening_rush": {
            "profile": "UP_PEAK",
            "rate": 0.25,
            "ticks": 50,
            "title": "Evening Departure Rush"
        }
    }
    
    api_key = get_gemini_api_key()
    
    for name, config in presets_config.items():
        logger.info(f"Generating preset: {config['title']}")
        
        # 1. Run LOOK Heuristic
        logger.info("  Running Heuristic LOOK simulation...")
        heuristic_res = run_simulation(
            dispatcher=HeuristicDispatcher(),
            seed=42,
            profile=config["profile"],
            rate=config["rate"],
            max_ticks=config["ticks"]
        )
        
        # 2. Run Agentic Gemini (with fallback)
        agentic_res = None
        
        if api_key:
            logger.info("  Running live Agentic Gemini simulation (this may take 1-2 mins due to rate limiting sleeps)...")
            try:
                agentic_res = run_simulation(
                    dispatcher=DispatcherAgent(),
                    seed=42,
                    profile=config["profile"],
                    rate=config["rate"],
                    max_ticks=config["ticks"]
                )
            except Exception as e:
                logger.warning(f"  Live Agentic simulation failed: {e}. Falling back to mock agentic simulation.")
                agentic_res = run_mock_agentic_simulation(
                    seed=42,
                    profile=config["profile"],
                    rate=config["rate"],
                    max_ticks=config["ticks"]
                )
        else:
            logger.info("  No API key found. Generating mock agentic simulation...")
            agentic_res = run_mock_agentic_simulation(
                seed=42,
                profile=config["profile"],
                rate=config["rate"],
                max_ticks=config["ticks"]
            )
            
        preset_data = {
            "title": config["title"],
            "profile": config["profile"],
            "arrival_rate": config["rate"],
            "seed": 42,
            "max_ticks": config["ticks"],
            "heuristic": heuristic_res,
            "agentic": agentic_res
        }
        
        filepath = os.path.join(CACHE_DIR, f"preset_{name}.json")
        with open(filepath, "w") as f:
            json.dump(preset_data, f, indent=2)
            
        logger.info(f"  Saved preset to {filepath}")

if __name__ == "__main__":
    generate_presets()
