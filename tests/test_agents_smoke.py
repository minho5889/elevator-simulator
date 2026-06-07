# tests/test_agents_smoke.py
"""Smoke test for the agentic policy dispatcher.

Skips dynamically if no GEMINI_API_KEY is found in the environment.
"""

import traceback

import pytest
from elevatorsim.core.building import Building
from elevatorsim.core.car import Car
from elevatorsim.core.passenger import Passenger
from elevatorsim.core.metrics import MetricsCollector
from elevatorsim.core.simulation import Simulation
from elevatorsim.policy.agentic import DispatcherAgent
from elevatorsim.config import get_gemini_api_key

@pytest.mark.skipif(
    get_gemini_api_key() is None,
    reason="GEMINI_API_KEY is not configured in the environment. Skipping live model tests."
)
def test_agentic_dispatcher_smoke():
    """Verify DispatcherAgent successfully performs a live dispatch call."""
    building = Building(num_floors=5)
    car = Car(car_id="C1", initial_floor=0)
    dispatcher = DispatcherAgent()
    metrics = MetricsCollector()
    
    sim = Simulation(building, car, dispatcher, metrics, verbose=False)

    # Place a waiting passenger directly on its source floor. We intentionally do
    # NOT call sim.step(): step() invokes the dispatcher internally, which would
    # make an extra (unguarded) live agent call. We want exactly one agent call,
    # made inside the quota guard below.
    p1 = Passenger("P1", source_floor=0, target_floor=3, spawn_time=0)
    building.add_passenger(p1)

    # The car is at floor 0, passenger waiting at floor 0.
    # Dispatcher should be called to select a target.
    try:
        target = dispatcher.dispatch(sim)
    except Exception as exc:  # noqa: BLE001
        # Free-tier keys routinely hit 429 quota / throttling limits. That is an
        # API-availability condition, not a code defect, so skip rather than fail.
        # Strands retries and re-wraps throttle errors, so the exception type that
        # surfaces here is unreliable; the chained Google quota payload is, however,
        # always present in the formatted traceback.
        if _is_quota_error(exc):
            pytest.skip(f"Gemini quota/throttle limit hit, skipping live smoke test: {exc}")
        raise

    assert target is not None
    assert 0 <= target < building.num_floors
    print(f"\n[SMOKE TEST SUCCESS] Agent chose target floor: {target}")


_QUOTA_MARKERS = (
    "429", "quota", "resource_exhausted", "rate limit", "ratelimit", "throttl",
)


def _is_quota_error(exc: BaseException) -> bool:
    """Detect Gemini rate-limit / quota-exhaustion errors.

    Strands retries and re-wraps Google's HTTP 429, so neither the surfaced
    exception type nor its ``str()`` reliably carries the word "quota". The
    chained Google quota payload (status 429, ``RESOURCE_EXHAUSTED``) is, however,
    always rendered in the formatted traceback, so we scan that as the source of
    truth, with an explicit 429 status-code check as a fast path.
    """
    seen: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and current not in seen and len(seen) < 6:
        seen.append(current)
        if (getattr(current, "status_code", None) or getattr(current, "code", None)) == 429:
            return True
        current = current.__cause__ or current.__context__

    rendered = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).lower()
    return any(marker in rendered for marker in _QUOTA_MARKERS)
