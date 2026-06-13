# src/elevatorsim/web/serialize.py
"""JSON serializers for the web layer.

``serialize_event`` (moved from ``server.py``) flattens a domain event for the
legacy 2-team event stream. ``serialize_sim_state`` is the per-tick STATE
SNAPSHOT the Arena UI consumes directly — it carries the skyscraper state that
is NOT reconstructable from events (zones, structural mode/hold, per-passenger
car assignment, weight), read straight off the live ``Car``/``Passenger``/
dispatcher objects (a pure read — no mutation).
"""

from typing import Any, Dict, List, Optional

from elevatorsim.core.events import Event
from elevatorsim.arena.run import percentile


def serialize_event(event: Event) -> Dict[str, Any]:
    """Serialize a simulation event object into a JSON-compatible dictionary."""
    data = {
        "event_type": event.__class__.__name__,
        "message": str(event),
        "time": event.time,
    }
    for k, v in event.__dict__.items():
        if not k.startswith("_"):
            data[k] = v
    return data


def _passenger_brief(p: Any) -> Dict[str, Any]:
    return {
        "id": p.passenger_id,
        "target": p.target_floor,
        "final_target": getattr(p, "final_target", p.target_floor),
        "weight": getattr(p, "weight_kg", None),
        "assigned_car_id": getattr(p, "assigned_car_id", None),
        "spawn_time": getattr(p, "spawn_time", None),
    }


def _car_state(car: Any) -> Dict[str, Any]:
    svc = getattr(car, "service_range", None)
    return {
        "car_id": car.car_id,
        "position": round(car.current_position, 3),
        "floor": car.current_floor,
        "target_floor": car.target_floor,
        "direction": car.direction,
        "door_state": car.door_state,
        "door_timer": car.door_timer,
        "onboard": [_passenger_brief(p) for p in car.passengers],
        "passenger_count": car.passenger_count,
        "capacity": car.capacity,
        "weight_kg": round(car.current_weight_kg, 1),
        "max_weight_kg": car.max_weight_kg,
        "service_range": list(svc) if svc is not None else None,
        "assigned_only": getattr(car, "assigned_only", False),
    }


def _zone_map(sim: Any) -> Optional[Dict[str, List[int]]]:
    """car_id -> [lo, hi] zone band, when the dispatcher defines one.

    Static zoning exposes a ``_zone_car`` floor->car map; sky-lobby / express
    banks express it as per-car ``service_range``. Returns None for conventional
    dispatchers (no bands to draw)."""
    zone_car = getattr(sim.dispatcher, "_zone_car", None)
    if zone_car:
        bands: Dict[str, List[int]] = {}
        for floor, cid in zone_car.items():
            lo, hi = bands.get(cid, [floor, floor])
            bands[cid] = [min(lo, floor), max(hi, floor)]
        return bands
    svc_bands = {
        c.car_id: list(c.service_range)
        for c in sim.cars
        if getattr(c, "service_range", None) is not None
    }
    return svc_bands or None


def _structural_state(sim: Any) -> Optional[Dict[str, Any]]:
    """The learned policy's current mode+hold, if this is a StructuralDispatcher."""
    plan = getattr(sim.dispatcher, "current_plan", None)
    if plan is None and not hasattr(sim.dispatcher, "plan_provider"):
        return None
    provider = getattr(sim.dispatcher, "plan_provider", None)
    out: Dict[str, Any] = {
        "mode": getattr(plan, "mode", None),
        "hold": getattr(plan, "hold", None),
    }
    if provider is not None:
        out["valid_rate"] = getattr(provider, "valid_rate", None)
        out["model_id"] = getattr(provider, "model_id", None)
        epoch = getattr(sim.dispatcher, "min_epoch_ticks", None)
        if epoch is not None:
            out["epoch_ticks"] = epoch
    return out


def snapshot_metrics(
    sim: Any, refusals: int = 0, transfers: int = 0
) -> Dict[str, Any]:
    """Running metrics for one contestant at the current tick (the arena scorer's
    live subset). Wait-quality is None until someone completes (survivorship)."""
    metrics = sim.metrics
    completed = metrics.completed_passengers
    waits = [p.wait_time for p in completed if p.wait_time is not None]
    totals = [p.total_time for p in completed if p.total_time is not None]
    ticks = max(sim.current_time, 1)
    spawned = len(metrics.all_passengers)
    delivered = len(completed)
    return {
        "awt": round(sum(waits) / len(waits), 2) if waits else None,
        "p95_wait": round(percentile(waits, 95), 2) if waits else None,
        "attd": round(sum(totals) / len(totals), 2) if totals else None,
        "hc5": round(delivered / ticks * 300, 2),
        "energy": round(metrics.total_energy, 2),
        "delivered": delivered,
        "spawned": spawned,
        "completion": round(delivered / spawned, 3) if spawned else 0.0,
        "refusals": refusals,
        "transfers": transfers,
    }


def serialize_sim_state(
    sim: Any,
    contestant_id: str,
    *,
    refusals: int = 0,
    transfers: int = 0,
) -> Dict[str, Any]:
    """Full per-tick snapshot for one contestant (everything the Arena renders)."""
    snap: Dict[str, Any] = {
        "contestant_id": contestant_id,
        "tick": sim.current_time,
        "cars": [_car_state(c) for c in sim.cars],
        "floor_queues": {
            str(f): [_passenger_brief(p) for p in sim.building.get_waiting_at(f)]
            for f in sim.building.get_active_calls()
        },
        "metrics": snapshot_metrics(sim, refusals=refusals, transfers=transfers),
    }
    zones = _zone_map(sim)
    if zones:
        snap["zones"] = zones
    structural = _structural_state(sim)
    if structural is not None:
        snap["structural"] = structural
    return snap
