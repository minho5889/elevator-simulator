# src/elevatorsim/mcp/server.py
"""MCP server exposing tools to control and inspect simulation runs programmatically."""

import json
from typing import Dict, Any, Optional
import uuid
from mcp.server.fastmcp import FastMCP

from elevatorsim.core.building import Building
from elevatorsim.core.car import Car
from elevatorsim.core.metrics import MetricsCollector
from elevatorsim.core.passenger import Passenger
from elevatorsim.core.simulation import Simulation
from elevatorsim.core.traffic import TrafficGenerator
from elevatorsim.policy.heuristic import HeuristicDispatcher, GroupHeuristicDispatcher
from elevatorsim.policy.agentic import DispatcherAgent
from elevatorsim.config import seed_rng

# Global simulation states
sim_heuristic: Optional[Simulation] = None
sim_agentic: Optional[Simulation] = None
mcp_config: Dict[str, Any] = {}

mcp = FastMCP("ElevatorSim")

@mcp.tool()
def init_simulation(
    seed: int = 42,
    num_floors: int = 5,
    num_cars: int = 1,
    arrival_rate: float = 0.2,
    profile: str = "UNIFORM",
    max_ticks: int = 50,
) -> str:
    """
    Initialize an A/B elevator simulation comparison on the server.
    
    Args:
        seed: RNG seed for reproducible passenger arrivals.
        num_floors: Number of floors (2-10).
        num_cars: Number of elevator cars in the bank (1-6).
        arrival_rate: Probability of passenger spawn per tick (0.0 to 1.0).
        profile: Traffic profile ('UNIFORM', 'DOWN_PEAK', or 'UP_PEAK').
        max_ticks: Maximum simulation ticks limit.
    """
    global sim_heuristic, sim_agentic, mcp_config
    
    if num_floors < 2 or num_floors > 10:
        return "Error: Number of floors must be between 2 and 10."
    if num_cars < 1 or num_cars > 6:
        return "Error: Number of cars must be between 1 and 6."
    if arrival_rate < 0.0 or arrival_rate > 1.0:
        return "Error: Arrival rate must be between 0.0 and 1.0."
    if profile not in ("UNIFORM", "DOWN_PEAK", "UP_PEAK"):
        return "Error: Profile must be UNIFORM, DOWN_PEAK, or UP_PEAK."
        
    mcp_config = {
        "seed": seed,
        "num_floors": num_floors,
        "num_cars": num_cars,
        "arrival_rate": arrival_rate,
        "profile": profile,
        "max_ticks": max_ticks
    }
    
    # 1. Initialize Heuristic Simulation
    seed_rng(seed)
    look_building = Building(num_floors=num_floors)
    look_cars = [Car(f"C{i+1}", 0) for i in range(num_cars)]
    look_dispatcher = GroupHeuristicDispatcher() if num_cars > 1 else HeuristicDispatcher()
    look_metrics = MetricsCollector()
    look_tg = TrafficGenerator(num_floors, arrival_rate, profile)
    
    sim_heuristic = Simulation(
        building=look_building,
        car=look_cars[0],
        dispatcher=look_dispatcher,
        metrics_collector=look_metrics,
        traffic_generator=look_tg,
        verbose=False,
        extra_cars=look_cars[1:] if len(look_cars) > 1 else None
    )
    
    # 2. Initialize Agentic Simulation
    seed_rng(seed)
    agentic_building = Building(num_floors=num_floors)
    agentic_cars = [Car(f"C{i+1}", 0) for i in range(num_cars)]
    agentic_dispatcher = DispatcherAgent()
    agentic_metrics = MetricsCollector()
    agentic_tg = TrafficGenerator(num_floors, arrival_rate, profile)
    
    sim_agentic = Simulation(
        building=agentic_building,
        car=agentic_cars[0],
        dispatcher=agentic_dispatcher,
        metrics_collector=agentic_metrics,
        traffic_generator=agentic_tg,
        verbose=False,
        extra_cars=agentic_cars[1:] if len(agentic_cars) > 1 else None
    )
    
    return json.dumps({
        "status": "Initialized",
        "config": mcp_config
    }, indent=2)

@mcp.tool()
def step_simulation(ticks: int = 1) -> str:
    """
    Advance both Heuristic and Agentic simulations by a given number of ticks.
    
    Args:
        ticks: Number of ticks to step (default is 1).
    """
    global sim_heuristic, sim_agentic
    
    if sim_heuristic is None or sim_agentic is None:
        return "Error: Simulation not initialized. Call init_simulation first."
        
    h_start_tick = sim_heuristic.current_time
    max_ticks = mcp_config.get("max_ticks", 50)
    
    if h_start_tick >= max_ticks:
        return f"Error: Simulation has already reached max ticks limit ({max_ticks})."
        
    actual_ticks = min(ticks, max_ticks - h_start_tick)
    
    h_events = []
    a_events = []
    
    def h_listener(ev):
        h_events.append(ev)
    def a_listener(ev):
        a_events.append(ev)
        
    sim_heuristic.register_listener(h_listener)
    sim_agentic.register_listener(a_listener)
    
    try:
        for _ in range(actual_ticks):
            sim_heuristic.step()
            sim_agentic.step()
    finally:
        if h_listener in sim_heuristic.listeners:
            sim_heuristic.listeners.remove(h_listener)
        if a_listener in sim_agentic.listeners:
            sim_agentic.listeners.remove(a_listener)
        
    return json.dumps({
        "stepped_ticks": actual_ticks,
        "current_tick": sim_heuristic.current_time,
        "heuristic_new_events": [str(e) for e in h_events],
        "agentic_new_events": [str(e) for e in a_events]
    }, indent=2)

@mcp.tool()
def get_status() -> str:
    """
    Retrieve current status, car telemetry, and outstanding logs of both simulators.
    """
    global sim_heuristic, sim_agentic
    
    if sim_heuristic is None or sim_agentic is None:
        return "Error: Simulation not initialized. Call init_simulation first."
        
    def serialize_sim_state(sim):
        cars_data = {}
        for car in sim.cars:
            cars_data[car.car_id] = {
                "floor": car.current_floor,
                "target_floor": car.target_floor,
                "door_state": car.door_state,
                "passenger_count": car.passenger_count,
                "onboard_passengers": [
                    {"id": p.passenger_id, "target": p.target_floor}
                    for p in car.passengers
                ]
            }
            
        floor_queues = {}
        for floor_idx in range(sim.building.num_floors):
            queue = sim.building.get_waiting_at(floor_idx)
            floor_queues[floor_idx] = [
                {"id": p.passenger_id, "target": p.target_floor}
                for p in queue
            ]
            
        return {
            "current_time": sim.current_time,
            "cars": cars_data,
            "floor_queues": floor_queues
        }
        
    return json.dumps({
        "heuristic_state": serialize_sim_state(sim_heuristic),
        "agentic_state": serialize_sim_state(sim_agentic)
    }, indent=2)

@mcp.tool()
def get_metrics() -> str:
    """
    Retrieve performance metrics comparison between the LOOK Heuristic and the Agentic dispatcher.
    """
    global sim_heuristic, sim_agentic
    
    if sim_heuristic is None or sim_agentic is None:
        return "Error: Simulation not initialized. Call init_simulation first."
        
    return json.dumps({
        "heuristic_metrics": sim_heuristic.metrics.get_summary(),
        "agentic_metrics": sim_agentic.metrics.get_summary()
    }, indent=2)

@mcp.tool()
def spawn_passenger(source_floor: int, target_floor: int) -> str:
    """
    Manually spawn a passenger at the next simulation tick in both simulators.
    
    Args:
        source_floor: Starting floor index.
        target_floor: Destination floor index.
    """
    global sim_heuristic, sim_agentic
    
    if sim_heuristic is None or sim_agentic is None:
        return "Error: Simulation not initialized. Call init_simulation first."
        
    num_floors = mcp_config.get("num_floors", 5)
    if not (0 <= source_floor < num_floors) or not (0 <= target_floor < num_floors):
        return f"Error: Floors must be between 0 and {num_floors - 1}."
    if source_floor == target_floor:
        return "Error: Source and target floors must be different."
        
    spawn_time = sim_heuristic.current_time + 1
    passenger_id = f"P_mcp_{uuid.uuid4().hex[:6]}"
    
    p_h = Passenger(passenger_id, source_floor, target_floor, spawn_time)
    p_a = Passenger(passenger_id, source_floor, target_floor, spawn_time)
    
    sim_heuristic.schedule_passenger(spawn_time, p_h)
    sim_agentic.schedule_passenger(spawn_time, p_a)
    
    return json.dumps({
        "passenger_id": passenger_id,
        "spawn_tick": spawn_time,
        "source": source_floor,
        "target": target_floor
    }, indent=2)

if __name__ == "__main__":
    mcp.run()
