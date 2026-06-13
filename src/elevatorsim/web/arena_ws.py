# src/elevatorsim/web/arena_ws.py
"""Arena WebSocket session: race K dispatcher contestants under one regime.

Additive to the legacy 2-team protocol in ``server.py`` — ``websocket_simulate``
delegates here when an ``init`` message carries ``arena: true``. Every contestant
sim is built with ``traffic_generator=None`` and fed arrivals cloned from a SINGLE
seeded RNG each tick, so all contestants see byte-identical traffic (Common Random
Numbers); a live ``traffic_generator`` would pull the global RNG and desync them.
"""

import asyncio
import json
import logging
import random
from typing import Any, Dict, List, Optional

from fastapi import WebSocket, WebSocketDisconnect

from elevatorsim.core.building import Building
from elevatorsim.core.car import Car
from elevatorsim.core.events import BoardingRefused, PassengerTransferred
from elevatorsim.core.metrics import MetricsCollector
from elevatorsim.core.passenger import Passenger
from elevatorsim.core.simulation import Simulation
from elevatorsim.core.traffic import TrafficGenerator
from elevatorsim.arena.registry import (
    CONTESTANT_META,
    REGIMES,
    make_dispatcher,
    structural_available,
)
from elevatorsim.web.serialize import serialize_event, serialize_sim_state

logger = logging.getLogger("elevatorsim.web.arena")

# Contestants whose dispatcher needs a reachable Ollama model before it can race.
_MODEL_CONTESTANTS = ("structural", "agentic", "agent", "gemini", "gemma")


def _build_cars(num_cars: int, capacity: int, car_speeds: Optional[List[float]],
                max_weight_kg: Optional[float]) -> List[Car]:
    speeds = car_speeds if (car_speeds and len(car_speeds) == num_cars) else [1.0] * num_cars
    return [
        Car(car_id=f"C{i + 1}", initial_floor=0, capacity=capacity,
            speed=speeds[i], max_weight_kg=max_weight_kg)
        for i in range(num_cars)
    ]


class _Contestant:
    """One live contestant: its sim, this-tick events, and refusal/transfer tallies."""

    def __init__(self, cid: str, dispatcher_key: str, sim: Simulation) -> None:
        self.id = cid
        self.dispatcher_key = dispatcher_key
        self.sim = sim
        self.events: List[Dict[str, Any]] = []
        self.refusals = 0
        self.transfers = 0
        self.error: Optional[str] = None
        sim.register_listener(self._observe)

    def _observe(self, ev: Any) -> None:
        if isinstance(ev, BoardingRefused):
            self.refusals += 1
        elif isinstance(ev, PassengerTransferred):
            self.transfers += 1
        self.events.append(serialize_event(ev))

    def snapshot(self) -> Dict[str, Any]:
        return serialize_sim_state(
            self.sim, self.id, refusals=self.refusals, transfers=self.transfers
        )


async def handle_arena_session(websocket: WebSocket, init_msg: Dict[str, Any]) -> None:
    """Own the WS receive loop for an arena race until the client disconnects."""
    cfg = init_msg.get("config", {})
    seed = int(cfg.get("seed", 1000))
    num_floors = int(cfg.get("num_floors", 24))
    num_cars = int(cfg.get("num_cars", 6))
    capacity = int(cfg.get("capacity", 24))
    car_speeds = cfg.get("car_speeds")
    max_weight_kg = cfg.get("max_weight_kg", 1600.0)
    arrival_rate = float(cfg.get("arrival_rate", 0.8))
    regime = cfg.get("regime", "up_peak")
    max_ticks = int(cfg.get("max_ticks", 600))
    stop_ticks = int(cfg.get("stop_ticks", 9))
    transfer_ticks = int(cfg.get("transfer_ticks", 1))
    state_every = max(1, int(cfg.get("state_every", 1)))
    min_epoch_ticks = int(cfg.get("min_epoch_ticks", 120))
    requested = cfg.get("contestants", [])

    profile = REGIMES.get(regime)
    if profile is None:
        await websocket.send_json({"type": "error",
                                   "message": f"Unknown regime: {regime!r}"})
        return

    # Build the live contestant set; probe model contestants and report availability.
    contestants: List[_Contestant] = []
    init_report: List[Dict[str, Any]] = []
    arena_rng = random.Random(seed)
    passenger_counter = 0

    for spec in requested:
        cid = spec.get("id") or spec.get("dispatcher")
        dispatcher_key = spec.get("dispatcher", cid)
        meta = CONTESTANT_META.get(dispatcher_key, {})
        label = spec.get("label") or meta.get("label", dispatcher_key)
        entry: Dict[str, Any] = {"id": cid, "dispatcher": dispatcher_key,
                                 "label": label, "available": True,
                                 "unavailable_reason": None}

        base = dispatcher_key.split(":", 1)[0]
        if base in _MODEL_CONTESTANTS:
            ok, reason = structural_available(spec.get("ollama_model_id"),
                                              cfg.get("ollama_host"))
            if not ok:
                entry["available"] = False
                entry["unavailable_reason"] = reason
                init_report.append(entry)
                continue
        try:
            dispatcher = make_dispatcher(
                dispatcher_key,
                ollama_model_id=spec.get("ollama_model_id"),
                ollama_host=cfg.get("ollama_host"),
                min_epoch_ticks=min_epoch_ticks,
            )
            cars = _build_cars(num_cars, capacity, car_speeds, max_weight_kg)
            sim = Simulation(
                building=Building(num_floors=num_floors),
                car=cars[0],
                dispatcher=dispatcher,
                metrics_collector=MetricsCollector(),
                traffic_generator=None,
                verbose=False,
                extra_cars=cars[1:] if len(cars) > 1 else None,
                stop_ticks=stop_ticks,
                transfer_ticks=transfer_ticks,
            )
            contestants.append(_Contestant(cid, dispatcher_key, sim))
        except Exception as exc:  # noqa: BLE001 - report, don't crash the race
            entry["available"] = False
            entry["unavailable_reason"] = f"failed to build: {exc}"
        init_report.append(entry)

    traffic = TrafficGenerator(num_floors=num_floors, arrival_rate=arrival_rate,
                               profile=profile)

    await websocket.send_json({
        "type": "arena_init",
        "contestants": init_report,
        "config": {
            "seed": seed, "num_floors": num_floors, "num_cars": num_cars,
            "capacity": capacity, "max_weight_kg": max_weight_kg,
            "arrival_rate": arrival_rate, "regime": regime, "max_ticks": max_ticks,
            "min_epoch_ticks": min_epoch_ticks,
        },
        "tick": 0,
        "states": [c.snapshot() for c in contestants],
    })

    def _inject(passenger: Passenger, tick: int) -> None:
        for c in contestants:
            clone = Passenger(
                passenger_id=passenger.passenger_id,
                source_floor=passenger.source_floor,
                target_floor=passenger.target_floor,
                spawn_time=passenger.spawn_time,
                weight_kg=passenger.weight_kg,
                final_target=passenger.final_target,
            )
            c.sim.schedule_passenger(tick, clone)

    async def _step_contestant(c: _Contestant) -> None:
        c.events.clear()
        c.error = None
        try:
            await asyncio.to_thread(c.sim.step)
        except Exception as exc:  # noqa: BLE001 - a model hiccup forfeits one tick
            c.error = str(exc)
            logger.warning("Contestant %s step failed: %s", c.id, exc)

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            mtype = message.get("type")

            if mtype == "step":
                if not contestants:
                    await websocket.send_json({"type": "error",
                                               "message": "No available contestants."})
                    continue
                next_tick = contestants[0].sim.current_time + 1
                if next_tick > max_ticks:
                    await websocket.send_json({"type": "error",
                                               "message": "Maximum tick limit reached."})
                    continue
                for p in traffic.generate(next_tick, arena_rng):
                    _inject(p, next_tick)
                await asyncio.gather(*[_step_contestant(c) for c in contestants])
                payload: Dict[str, Any] = {
                    "type": "arena_state",
                    "tick": next_tick,
                    "events": {c.id: c.events for c in contestants},
                    "errors": {c.id: c.error for c in contestants},
                }
                if next_tick % state_every == 0:
                    payload["states"] = [c.snapshot() for c in contestants]
                await websocket.send_json(payload)

            elif mtype == "spawn":
                source, target = message.get("source"), message.get("target")
                if source is None or target is None or not contestants:
                    await websocket.send_json({"type": "error",
                                               "message": "Missing source/target or no contestants."})
                    continue
                passenger_counter += 1
                spawn_tick = contestants[0].sim.current_time + 1
                _inject(Passenger(passenger_id=f"P_man_{passenger_counter}",
                                  source_floor=source, target_floor=target,
                                  spawn_time=spawn_tick), spawn_tick)
                await websocket.send_json({
                    "type": "spawn_confirm",
                    "passenger_id": f"P_man_{passenger_counter}",
                    "source": source, "target": target,
                })

            elif mtype == "init":
                # Re-init within the same socket: restart the session cleanly.
                await handle_arena_session(websocket, message)
                return

    except WebSocketDisconnect:
        logger.info("Arena WebSocket disconnected.")
