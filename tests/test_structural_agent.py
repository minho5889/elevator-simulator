# tests/test_structural_agent.py
"""P7 inference surface: the learned structural policy provider + dispatcher.

Offline tests (fallback, wiring, frozen prompt) run everywhere; the real-model
smoke test is skipped unless a local Ollama with a gemma model is reachable.
"""

import importlib.util
import json
import sys
import time
from pathlib import Path

import pytest

from elevatorsim.policy.schemas import StructuralPlan
from elevatorsim.policy.structural import STRUCTURAL_SYSTEM_PROMPT, StructuralDispatcher
from elevatorsim.policy.structural_agent import (
    LLMStructuralProvider,
    make_structural_dispatcher,
    render_traffic_summary,
)
from elevatorsim.config import OLLAMA_MODEL_ID

_ROOT = Path(__file__).resolve().parents[1]
_ospec = importlib.util.spec_from_file_location("oracle_sa", _ROOT / "scripts" / "oracle.py")
oracle = importlib.util.module_from_spec(_ospec)
sys.modules["oracle_sa"] = oracle
_ospec.loader.exec_module(oracle)


class _Fixed(LLMStructuralProvider):
    """Provider with a deterministic model — no Ollama, for offline tests."""

    def __init__(self, plan: StructuralPlan):
        self._plan = plan
        self._last_plan = plan
        self.stats = {"calls": 0, "invalid": 0}

    def _query_model(self, summary: str) -> StructuralPlan:
        return self._plan


class _Failing(LLMStructuralProvider):
    """Provider whose model call always raises — exercises the fallback path."""

    def __init__(self):
        self._last_plan = StructuralPlan(mode="conventional", hold="balanced")
        self.stats = {"calls": 0, "invalid": 0}

    def _query_model(self, summary: str) -> StructuralPlan:
        raise RuntimeError("model unavailable")


def test_render_traffic_summary_is_compact_and_excludes_call_dump():
    """The model input is the ~200-char traffic summary, not the 17 KB call dump."""
    sim = oracle.harvest_state("up_peak", 7, 120, floors=32)
    s = render_traffic_summary(sim)
    assert len(s) < 600  # compact; the full floor_calls dump is ~17 KB
    d = json.loads(s)
    assert d["frac_origin_lobby"] == 1.0  # up-peak signal present
    assert "floor_calls" not in d and "cars" not in d  # no per-passenger bloat


def test_provider_falls_back_to_last_plan_on_failure():
    """A model/parse failure forfeits to the last committed plan (a no-op epoch)."""
    sim = oracle.harvest_state("lunch", 7, 120, floors=20)
    p = _Failing()
    plan = p(sim)
    assert (plan.mode, plan.hold) == ("conventional", "balanced")  # cold-start default
    assert p.stats == {"calls": 1, "invalid": 1}
    assert p.valid_rate == 0.0


def test_provider_commits_then_reuses_last_good_plan():
    """A success updates the last plan; a later failure reuses it, not the default."""
    sim = oracle.harvest_state("lunch", 7, 120, floors=20)
    good = _Fixed(StructuralPlan(mode="zoned", hold="fill_batch"))
    assert good(sim).mode == "zoned"
    assert good.valid_rate == 1.0
    # Now make the same provider fail and confirm it reuses the committed plan.
    good._query_model = lambda summary: (_ for _ in ()).throw(RuntimeError("boom"))
    plan = good(sim)
    assert (plan.mode, plan.hold) == ("zoned", "fill_batch")
    assert good.stats["invalid"] == 1


def test_dispatcher_wiring_drives_a_full_episode():
    """A provider-backed StructuralDispatcher runs a full episode and delivers."""
    spec = importlib.util.spec_from_file_location("arena_sa", _ROOT / "scripts" / "arena.py")
    arena = importlib.util.module_from_spec(spec)
    sys.modules["arena_sa"] = arena
    spec.loader.exec_module(arena)
    base = arena._make_dispatcher
    arena._make_dispatcher = lambda n: (
        StructuralDispatcher(_Fixed(StructuralPlan(mode="zoned", hold="balanced")), min_epoch_ticks=300)
        if n == "_fixed" else base(n)
    )
    r = arena.run_one("_fixed", "lunch", 7, floors=32, cars=8, capacity=24,
                      arrival_rate=2.0, ticks=900, stop_ticks=9, transfer_ticks=1)
    assert r["delivered"] > 0 and r["completion"] > 0.3


def test_frozen_system_prompt_carries_the_contract():
    """The frozen prompt names every mode/hold and is shared by the inference path."""
    for token in ("conventional", "dd_delayed", "zoned", "depart_now", "balanced", "fill_batch"):
        assert token in STRUCTURAL_SYSTEM_PROMPT
    assert "Respond with the plan only." in STRUCTURAL_SYSTEM_PROMPT
    # The inference provider defaults to this exact frozen string (train == prod):
    # the same object the assembly path (WO-003) will import.
    import inspect
    default = inspect.signature(LLMStructuralProvider.__init__).parameters["system_prompt"].default
    assert default is STRUCTURAL_SYSTEM_PROMPT


def _ollama_ready() -> bool:
    try:
        import ollama
        models = [m.get("model", "") for m in ollama.list().get("models", [])]
        return any(OLLAMA_MODEL_ID in m or "gemma4" in m for m in models)
    except Exception:
        return False


@pytest.mark.skipif(not _ollama_ready(), reason="local Ollama + gemma model not available")
def test_real_model_returns_valid_plan():
    """Smoke: the real model produces a schema-valid plan via the production path.

    Latency is the dedicated G5 gate's concern (measured ~1.65s steady-state),
    not this test's — the first call here includes the ~9.6 GB cold model load.
    """
    sim = oracle.harvest_state("up_peak", 7, 120, floors=32)
    provider = LLMStructuralProvider()
    plan = provider(sim)
    assert isinstance(plan, StructuralPlan)
    assert plan.mode in ("conventional", "dd_delayed", "zoned")
    assert provider.valid_rate == 1.0
