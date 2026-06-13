# src/elevatorsim/tools/sim_tools.py
"""Strands tool definitions allowing the DispatcherAgent to query simulation state."""

from typing import Dict, Any, List
from strands import tool

# Module-level pointer to the active simulation being dispatched.
# Set by DispatcherAgent before executing the model calls.
_active_simulation: Any = None

def set_active_simulation(sim: Any) -> None:
    """Set the active simulation context for tool execution."""
    global _active_simulation
    _active_simulation = sim

def clear_active_simulation() -> None:
    """Clear the active simulation context."""
    global _active_simulation
    _active_simulation = None


@tool
def get_elevator_state() -> Dict[str, Any]:
    """
    Get the current physical state of the elevator car.
    
    Returns:
        A dictionary containing car_id, current_floor, target_floor, 
        direction (1: UP, -1: DOWN, 0: IDLE), door_state, and a list of onboard passengers.
    """
    if _active_simulation is None:
        return {"error": "No active simulation context."}
    
    car = _active_simulation.car
    passengers_info = [
        {
            "passenger_id": p.passenger_id,
            "source_floor": p.source_floor,
            "target_floor": p.target_floor,
            "spawn_time": p.spawn_time,
            "weight_kg": getattr(p, "weight_kg", None)
        }
        for p in car.passengers
    ]

    return {
        "car_id": car.car_id,
        "current_floor": car.current_floor,
        "target_floor": car.target_floor,
        "direction": car.direction,
        "door_state": car.door_state,
        "passengers": passengers_info,
        "passenger_count": len(passengers_info),
        "capacity": car.capacity,
        "current_weight_kg": car.current_weight_kg,
        "max_weight_kg": car.max_weight_kg
    }


@tool
def get_all_cars_state() -> Dict[str, Any]:
    """
    Get the physical state of every elevator car in the bank.

    Returns:
        A dictionary with ``num_floors`` (top floor index is ``num_floors - 1``)
        and ``cars``: a list of per-car states, each containing car_id,
        current_floor, target_floor, direction (1: UP, -1: DOWN, 0: IDLE),
        door_state, is_idle (closed doors and no target), and onboard passengers.
    """
    if _active_simulation is None:
        return {"error": "No active simulation context."}

    cars_info = []
    for car in _active_simulation.cars:
        cars_info.append({
            "car_id": car.car_id,
            "current_floor": car.current_floor,
            "target_floor": car.target_floor,
            "direction": car.direction,
            "door_state": car.door_state,
            "is_idle": car.door_state == "CLOSED" and car.target_floor is None,
            "passenger_count": car.passenger_count,
            "capacity": car.capacity,
            "current_weight_kg": car.current_weight_kg,
            "max_weight_kg": car.max_weight_kg,
            "remaining_weight_kg": (car.max_weight_kg - car.current_weight_kg) if car.max_weight_kg is not None else None,
            "onboard_destinations": sorted({p.target_floor for p in car.passengers}),
        })

    return {
        "num_floors": _active_simulation.building.num_floors,
        "cars": cars_info,
    }


@tool
def get_traffic_summary() -> Dict[str, Any]:
    """
    Get an aggregate traffic/regime summary for structural (skyscraper) dispatch.

    The structural policy chooses a control MODE per epoch, and that choice hinges
    on the traffic regime and building height — so this exposes the minimal
    sufficient statistics to classify up-peak vs down-peak vs lunch vs uniform and
    gauge load, rather than making a small model infer them from raw queues.

    Returns:
        A dictionary with num_floors, num_cars, total_waiting, total_onboard,
        and the directional mix of waiting passengers: frac_origin_lobby (share
        with source = floor 0, the up-peak signal), frac_dest_lobby (share bound
        for floor 0, the down-peak signal), frac_interfloor (neither end at the
        lobby), plus mean_wait_age (ticks) and max_floor_queue.
    """
    if _active_simulation is None:
        return {"error": "No active simulation context."}

    sim = _active_simulation
    building = sim.building
    now = sim.current_time

    waiting = [
        p for f in range(building.num_floors) for p in building.get_waiting_at(f)
    ]
    total = len(waiting)
    origin_lobby = sum(1 for p in waiting if p.source_floor == 0)
    dest_lobby = sum(1 for p in waiting if p.target_floor == 0)
    interfloor = sum(1 for p in waiting if p.source_floor != 0 and p.target_floor != 0)
    max_queue = max(
        (len(building.get_waiting_at(f)) for f in range(building.num_floors)),
        default=0,
    )

    return {
        "num_floors": building.num_floors,
        "num_cars": len(sim.cars),
        "total_waiting": total,
        "total_onboard": sum(c.passenger_count for c in sim.cars),
        "frac_origin_lobby": round(origin_lobby / total, 3) if total else 0.0,
        "frac_dest_lobby": round(dest_lobby / total, 3) if total else 0.0,
        "frac_interfloor": round(interfloor / total, 3) if total else 0.0,
        "mean_wait_age": round(sum(now - p.spawn_time for p in waiting) / total, 2) if total else 0.0,
        "max_floor_queue": max_queue,
    }


@tool
def get_floor_calls() -> Dict[str, List[Dict[str, Any]]]:
    """
    Get lists of passengers waiting on each floor (hall calls).
    
    Returns:
        A dictionary mapping floor numbers to lists of passenger requests 
        with source, target, and spawn_time.
    """
    if _active_simulation is None:
        return {"error": "No active simulation context."}
    
    building = _active_simulation.building
    floor_queues = {}
    
    for f in range(building.num_floors):
        waiting_list = building.get_waiting_at(f)
        floor_queues[str(f)] = [
            {
                "passenger_id": p.passenger_id,
                "source_floor": p.source_floor,
                "target_floor": p.target_floor,
                "spawn_time": p.spawn_time,
                "direction": "UP" if p.direction == 1 else "DOWN",
                "weight_kg": getattr(p, "weight_kg", None)
            }
            for p in waiting_list
        ]
        
    return floor_queues
