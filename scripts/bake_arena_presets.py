#!/usr/bin/env python3
# scripts/bake_arena_presets.py
"""Bake skyscraper Arena presets — full per-tick snapshot tracks the UI replays
instantly (no live WS, no model needed).

Each preset is a fixed (contestants × regime × scale) race recorded tick-by-tick
via the same CRN injection + ``serialize_sim_state`` the live arena uses, so a
baked preset is byte-identical to running it live. Conventional contestants only
(no Ollama dependency), so baking is deterministic and offline.

    uv run python scripts/bake_arena_presets.py
"""

import json
import os
import random
import sys
from typing import Any, Dict, List, Optional

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from elevatorsim.core.building import Building  # noqa: E402
from elevatorsim.core.car import Car  # noqa: E402
from elevatorsim.core.events import BoardingRefused, PassengerTransferred  # noqa: E402
from elevatorsim.core.metrics import MetricsCollector  # noqa: E402
from elevatorsim.core.passenger import Passenger  # noqa: E402
from elevatorsim.core.simulation import Simulation  # noqa: E402
from elevatorsim.core.traffic import TrafficGenerator  # noqa: E402
from elevatorsim.arena.registry import REGIMES, make_dispatcher, structural_available  # noqa: E402
from elevatorsim.web.serialize import serialize_sim_state  # noqa: E402

CACHE_DIR = os.path.join(ROOT, "src", "elevatorsim", "web", "cache")

_MODEL_BASES = ("structural", "agentic", "agent", "gemini", "gemma")


def _refusal_observer(ref: List[int], xfer: List[int]):
    def obs(e: Any) -> None:
        if isinstance(e, BoardingRefused):
            ref[0] += 1
        elif isinstance(e, PassengerTransferred):
            xfer[0] += 1
    return obs


def bake_one(contestants: List[Dict[str, Any]], *, seed: int, num_floors: int,
             num_cars: int, capacity: int, max_weight_kg: Optional[float],
             arrival_rate: float, regime: str, max_ticks: int,
             stop_ticks: int = 9, transfer_ticks: int = 1,
             min_epoch_ticks: int = 120) -> Dict[str, Any]:
    """Run one CRN race and record per-tick snapshot tracks for every contestant."""
    profile = REGIMES[regime]
    rng = random.Random(seed)
    traffic = TrafficGenerator(num_floors=num_floors, arrival_rate=arrival_rate, profile=profile)

    lanes: List[Dict[str, Any]] = []
    for spec in contestants:
        cid = spec["id"]
        dk = spec["dispatcher"]
        base = dk.split(":", 1)[0]
        if base in _MODEL_BASES:
            ok, reason = structural_available(spec.get("ollama_model_id"))
            if not ok:
                lanes.append({"id": cid, "dispatcher": dk, "available": False,
                              "unavailable_reason": reason, "track": [], "sim": None})
                continue
        cars = [Car(car_id=f"C{i+1}", initial_floor=0, capacity=capacity,
                    max_weight_kg=max_weight_kg) for i in range(num_cars)]
        sim = Simulation(
            building=Building(num_floors=num_floors), car=cars[0],
            dispatcher=make_dispatcher(dk, ollama_model_id=spec.get("ollama_model_id"),
                                       min_epoch_ticks=min_epoch_ticks),
            metrics_collector=MetricsCollector(), traffic_generator=None, verbose=False,
            extra_cars=cars[1:] if len(cars) > 1 else None,
            stop_ticks=stop_ticks, transfer_ticks=transfer_ticks)
        ref, xfer = [0], [0]
        sim.register_listener(_refusal_observer(ref, xfer))
        lanes.append({"id": cid, "dispatcher": dk, "available": True, "unavailable_reason": None,
                      "track": [serialize_sim_state(sim, cid)], "sim": sim, "_ref": ref, "_xfer": xfer})

    active = [le for le in lanes if le["sim"] is not None]
    for tick in range(1, max_ticks + 1):
        for p in traffic.generate(tick, rng):
            for le in active:
                le["sim"].schedule_passenger(tick, Passenger(
                    passenger_id=p.passenger_id, source_floor=p.source_floor,
                    target_floor=p.target_floor, spawn_time=p.spawn_time,
                    weight_kg=p.weight_kg, final_target=p.final_target))
        for le in active:
            le["sim"].step()
            le["track"].append(serialize_sim_state(
                le["sim"], le["id"], refusals=le["_ref"][0], transfers=le["_xfer"][0]))

    for le in lanes:
        le["metrics"] = le["track"][-1]["metrics"] if le["track"] else None
        for k in ("sim", "_ref", "_xfer"):
            le.pop(k, None)

    return {
        "config": {"seed": seed, "num_floors": num_floors, "num_cars": num_cars,
                   "capacity": capacity, "max_weight_kg": max_weight_kg,
                   "arrival_rate": arrival_rate, "regime": regime, "max_ticks": max_ticks},
        "contestants": lanes,
    }


# The baked "day" catalog for the kid view: two friendly racers per day —
# Robot (a simple LOOK rule) vs Brainy (a plan-ahead policy). Conventional
# dispatchers only, so a day replays instantly with no model needed. The ids
# robot/brainy are what the kid UI shows as character names.
PRESETS = {
    # Busy morning everyone-rides-up: heavy up-peak is exactly where planning
    # ahead (destination dispatch) beats a simple sweep — Brainy wins clearly.
    "morning_rush": {
        "title": "Morning Rush", "emoji": "🌅",
        "regime": "up_peak", "num_floors": 30, "num_cars": 8, "capacity": 18,
        "arrival_rate": 1.3, "max_ticks": 200, "seed": 1000,
        "contestants": [{"id": "robot", "dispatcher": "look"},
                        {"id": "brainy", "dispatcher": "dd_delayed"}],
    },
    # Calmer lunch, crowds both ways: the zippy simple sweep keeps up — Robot
    # wins. (Different days suit different styles!)
    "lunchtime": {
        "title": "Lunchtime", "emoji": "🍱",
        "regime": "lunch", "num_floors": 22, "num_cars": 6, "capacity": 20,
        "arrival_rate": 1.0, "max_ticks": 200, "seed": 2000,
        "contestants": [{"id": "robot", "dispatcher": "look"},
                        {"id": "brainy", "dispatcher": "zoned"}],
    },
    # Calm, scattered traffic: the simple speedy sweep keeps up just fine —
    # Robot wins. (Different days need different ideas!)
    "quiet_day": {
        "title": "Quiet Day", "emoji": "☁️",
        "regime": "uniform", "num_floors": 16, "num_cars": 4, "capacity": 24,
        "arrival_rate": 0.5, "max_ticks": 160, "seed": 3000,
        "contestants": [{"id": "robot", "dispatcher": "look"},
                        {"id": "brainy", "dispatcher": "dd_delayed"}],
    },
}


def main() -> int:
    os.makedirs(CACHE_DIR, exist_ok=True)
    index: List[Dict[str, Any]] = []
    for key, p in PRESETS.items():
        print(f"baking {key} ({p['title']}) — {p['regime']} {p['num_floors']}fl/{p['num_cars']}cars ...")
        baked = bake_one(
            p["contestants"], seed=p["seed"], num_floors=p["num_floors"],
            num_cars=p["num_cars"], capacity=p["capacity"], max_weight_kg=1600.0,
            arrival_rate=p["arrival_rate"], regime=p["regime"], max_ticks=p["max_ticks"])
        baked["title"] = p["title"]
        baked["emoji"] = p["emoji"]
        baked["key"] = key
        out = os.path.join(CACHE_DIR, f"arena_preset_{key}.json")
        with open(out, "w") as fh:
            json.dump(baked, fh)
        ticks = len(baked["contestants"][0]["track"]) if baked["contestants"] else 0
        size_kb = os.path.getsize(out) / 1024
        print(f"  -> {out}  ({ticks} ticks, {size_kb:.0f} KB)")
        index.append({"key": key, "title": p["title"], "emoji": p["emoji"],
                      "regime": p["regime"], "num_floors": p["num_floors"],
                      "num_cars": p["num_cars"],
                      "contestants": [c["dispatcher"] for c in p["contestants"]]})
    with open(os.path.join(CACHE_DIR, "arena_presets_index.json"), "w") as fh:
        json.dump(index, fh, indent=2)
    print(f"wrote index ({len(index)} presets)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
