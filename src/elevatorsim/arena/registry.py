# src/elevatorsim/arena/registry.py
"""The contestant ladder + regime catalog — one source of truth for the arena.

Lifted verbatim from ``scripts/arena.py`` (the ``REGIMES`` / ``DISPATCHERS`` /
``_make_dispatcher`` it had), plus the public ``make_dispatcher`` (keyword args
for the web layer), a ``CONTESTANT_LADDER`` + display metadata shared by the API
and the UI, and a cheap ``structural_available`` reachability probe.
"""

from typing import Any, Callable, Dict, List, Optional, Tuple

from elevatorsim.policy.baselines import (
    ETACostDispatcher,
    FCFSDispatcher,
    MainTerminalParkingLook,
    NearestCallDispatcher,
)
from elevatorsim.policy.destination import DestinationGroupDispatcher
from elevatorsim.policy.heuristic import GroupHeuristicDispatcher
from elevatorsim.policy.zoning import ZonedStaticDispatcher
from elevatorsim.config import OLLAMA_HOST, OLLAMA_MODEL_ID


# Regime name -> TrafficGenerator profile. Lunch is the bidirectional regime
# added for this plan (traffic.py); the others are the engine's originals.
REGIMES: Dict[str, str] = {
    "uniform": "UNIFORM",
    "down_peak": "DOWN_PEAK",
    "up_peak": "UP_PEAK",
    "lunch": "LUNCH",
}

# Dispatcher name -> zero-arg factory (fresh instance per run, no cross-seed state).
# Ordered weakest -> strongest so the ladder reads top to bottom.
DISPATCHERS: Dict[str, Callable[[], Any]] = {
    "fcfs": FCFSDispatcher,
    "nearest": NearestCallDispatcher,
    "eta": ETACostDispatcher,
    "look": GroupHeuristicDispatcher,
    # LOOK + main-terminal parking: the conventional-control reference (gate S2)
    "look_park": MainTerminalParkingLook,
    # Destination dispatch — assignment timing held explicit (gates S3/S5)
    "dd_delayed": lambda: DestinationGroupDispatcher("delayed"),
    "dd_immediate": lambda: DestinationGroupDispatcher("immediate"),
    # Ablation: same holding/turnstile/routing, FIFO batches, no destination
    # info — dd-vs-shuttle isolates the kiosk's information channel (gate S3)
    "shuttle": lambda: DestinationGroupDispatcher("delayed", batch_style="fifo"),
    # Static zoning: one contiguous zone per car, signage via assigned boarding
    # — the classical conventional up-peak strategy (P5 gate)
    "zoned": ZonedStaticDispatcher,
}


def make_dispatcher(
    name: str,
    *,
    ollama_model_id: Optional[str] = None,
    ollama_host: Optional[str] = None,
    min_epoch_ticks: int = 120,
) -> Any:
    """Build a dispatcher by ladder name (web-friendly, keyword args).

    Ladder baselines take no args. The learned ``structural`` policy and the
    legacy ``agentic`` Gemini policy are imported lazily so the baseline ladder
    runs with no LLM client present.
        - ``structural`` / ``structural:<model_id>`` -> the per-epoch learned
          policy (``min_epoch_ticks`` threads through; default 120 is ~1 RTT at
          skyscraper scale, not the 300 the headless default uses).
        - ``agentic`` / ``agent`` / ``gemini`` -> the per-dispatch Gemini agent.
    """
    if name in DISPATCHERS:
        return DISPATCHERS[name]()
    if name.startswith("structural"):
        from elevatorsim.policy.structural_agent import make_structural_dispatcher

        model_id = name.split(":", 1)[1] if ":" in name else ollama_model_id
        return make_structural_dispatcher(
            model_id=model_id, host=ollama_host, min_epoch_ticks=min_epoch_ticks
        )
    if name in ("agent", "agentic", "gemini", "gemma", "elevator-gemma"):
        from elevatorsim.policy.agentic import DispatcherAgent

        return DispatcherAgent(ollama_host=ollama_host, ollama_model_id=ollama_model_id)
    raise ValueError(
        f"Unknown dispatcher: {name!r} "
        f"(known: {', '.join(DISPATCHERS)} | structural[:model] | agentic)"
    )


def _make_dispatcher(name: str) -> Any:
    """Back-compat positional shim used by ``scripts/arena.py`` and its tests."""
    return make_dispatcher(name)


# The ordered ladder the Arena UI picks contestants from, with display metadata.
# Weakest -> strongest; the first two are the friendly default duo (Rule-Bot vs
# AI Brain) when exactly two contestants race.
CONTESTANT_LADDER: List[str] = [
    "look", "look_park", "fcfs", "nearest", "eta",
    "dd_delayed", "dd_immediate", "shuttle", "zoned", "structural", "agentic",
]

CONTESTANT_META: Dict[str, Dict[str, str]] = {
    "look": {"label": "Rule-Bot (LOOK)", "blurb": "Classic collective LOOK sweep."},
    "look_park": {"label": "LOOK + Park", "blurb": "LOOK with main-terminal parking."},
    "fcfs": {"label": "First-Come", "blurb": "Serves calls in arrival order."},
    "nearest": {"label": "Nearest-Car", "blurb": "Always sends the closest car."},
    "eta": {"label": "ETA-Cost", "blurb": "Nearest car + directional continuity."},
    "dd_delayed": {"label": "Destination (delayed)", "blurb": "Kiosk dispatch, late car assignment."},
    "dd_immediate": {"label": "Destination (instant)", "blurb": "Kiosk dispatch, locked at check-in."},
    "shuttle": {"label": "Shuttle (FIFO)", "blurb": "Batched FIFO, no destination info."},
    "zoned": {"label": "Zoned", "blurb": "One contiguous floor band per car."},
    "structural": {"label": "AI Brain (learned)", "blurb": "Gemma picks a structural plan per epoch."},
    "agentic": {"label": "AI Brain (Gemini)", "blurb": "Per-decision LLM dispatch (slow / quota-bound)."},
}


def structural_available(
    model_id: Optional[str] = None, host: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """Cheap reachability probe for the learned/agentic Ollama contestant.

    Returns ``(available, reason_if_not)``. Used at arena init so an absent
    Ollama model greys the contestant out instead of hanging the race; the
    per-epoch provider also forfeits to its last plan on any live error.
    """
    try:
        import ollama
    except Exception as exc:  # pragma: no cover - import guard
        return False, f"ollama python package unavailable: {exc}"
    want = model_id or OLLAMA_MODEL_ID
    try:
        client = ollama.Client(host=host or OLLAMA_HOST)
        listed = client.list().get("models", [])
        names = {m.get("model") or m.get("name") for m in listed}
    except Exception as exc:
        return False, f"Ollama server unreachable at {host or OLLAMA_HOST}: {exc}"
    if want not in names and not any((n or "").startswith(want) for n in names):
        return False, f"model {want!r} not pulled (have: {sorted(n for n in names if n)})"
    return True, None
