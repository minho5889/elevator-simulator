# src/elevatorsim/policy/structural_agent.py
"""Deployable learned structural policy — the P7 inference surface.

A ``StructuralPlan`` is produced per epoch by the local Gemma model and executed
by ``StructuralDispatcher``. The model id is configurable, so the fine-tuned
``elevator-gemma`` drops in over the base ``gemma4:e4b`` with zero code change.

Why a direct ``ollama.chat`` call rather than Strands ``agent.structured_output``:
the G5 latency gate (skyscraper-plan §7) measured the Strands structured-output
path TRUNCATING on the real model (returned ``'{"'``), while a single
``ollama.chat(..., format=StructuralPlan.model_json_schema(), think=False)`` call
is 1.65s / 100%-valid. The pydantic schema is still the contract anchor; we just
issue the constrained-decode call directly, which is also the freeze's prescribed
"single pre-rendered call" (no two-turn tool-observe loop). Three non-negotiables
the gate established and this encodes: compact ``get_traffic_summary`` input only
(the full call dump overflows context), ``think=False`` (12x slower otherwise),
and no reasoning field on the output.
"""

import json
from typing import Any, Optional

import ollama

from elevatorsim.config import DEFAULT_SEED, OLLAMA_HOST, OLLAMA_MODEL_ID
from elevatorsim.policy.schemas import StructuralPlan
from elevatorsim.policy.structural import (
    STRUCTURAL_SYSTEM_PROMPT,
    StructuralDispatcher,
    build_structural_messages,
)
from elevatorsim.tools.sim_tools import (
    clear_active_simulation,
    get_traffic_summary,
    set_active_simulation,
)

# Safe default when the model has never produced a valid plan yet (cold start).
_COLD_START_PLAN = StructuralPlan(mode="conventional", hold="balanced")


def render_traffic_summary(simulation: Any) -> str:
    """Serialize the compact ``get_traffic_summary`` view — the ONLY model input.

    Deliberately excludes ``get_floor_calls`` / ``get_all_cars_state``: the G5
    gate proved the full call dump (~17 KB) overflows the model's context and
    truncates output. The summary (~200 chars) is the sufficient statistic for
    the structural mode decision.

    MUST call ``get_traffic_summary()`` exactly as ``scripts/label.py`` does, so
    the training input_view and the served input_view are byte-identical — this
    is the model's only input. The render-parity gate (tests) enforces it. (A
    prior ``tool.func() if hasattr(...)`` guard was removed: the Strands wrapper
    has no ``.func`` today, but the dead branch was a version-bump landmine that
    could silently split the two serializers.)
    """
    set_active_simulation(simulation)
    try:
        summary = get_traffic_summary()
    finally:
        clear_active_simulation()
    return json.dumps(summary, sort_keys=True)


class LLMStructuralProvider:
    """Plan provider: render the traffic summary, ask the model for a StructuralPlan.

    Used as the ``plan_provider`` of a ``StructuralDispatcher`` (queried once per
    epoch, never per tick). On any model/parse failure it forfeits to the last
    committed plan — a true no-op for that epoch rather than a structural
    collapse — and counts the miss so the G4 valid-rate (>=99.5%) is observable.
    ``stats`` exposes ``calls`` / ``invalid`` for that monitoring.
    """

    def __init__(
        self,
        model_id: Optional[str] = None,
        host: Optional[str] = None,
        system_prompt: str = STRUCTURAL_SYSTEM_PROMPT,
        seed: int = DEFAULT_SEED,
    ) -> None:
        self.model_id = model_id or OLLAMA_MODEL_ID
        self.host = host or OLLAMA_HOST
        self.system_prompt = system_prompt
        self.seed = seed
        self._schema = StructuralPlan.model_json_schema()
        self._client = ollama.Client(host=self.host)
        self._last_plan = _COLD_START_PLAN
        self.stats = {"calls": 0, "invalid": 0}

    def _query_model(self, summary: str) -> StructuralPlan:
        """Single constrained-decode call. Overridable so tests can run offline.

        The prompt is built through ``build_structural_messages`` — the SAME
        anchor Stage-3 assembly uses — so a fine-tuned model is served the exact
        prompt it was trained on (train == prod).
        """
        response = self._client.chat(
            model=self.model_id,
            messages=build_structural_messages(summary, self.system_prompt),
            format=self._schema,
            options={"temperature": 0, "seed": self.seed},
            think=False,
        )
        return StructuralPlan.model_validate_json(response["message"]["content"])

    def __call__(self, simulation: Any) -> StructuralPlan:
        self.stats["calls"] += 1
        try:
            plan = self._query_model(render_traffic_summary(simulation))
        except Exception:
            self.stats["invalid"] += 1
            return self._last_plan  # forfeit = keep last committed plan (no-op)
        self._last_plan = plan
        return plan

    @property
    def valid_rate(self) -> float:
        """Fraction of calls that produced a valid plan (the G4 gate metric)."""
        n = self.stats["calls"]
        return 1.0 if n == 0 else (n - self.stats["invalid"]) / n


def make_structural_dispatcher(
    model_id: Optional[str] = None,
    host: Optional[str] = None,
    min_epoch_ticks: int = 300,
) -> StructuralDispatcher:
    """Build a group dispatcher driven by the learned structural policy.

    ``model_id`` defaults to the configured Ollama model; pass ``elevator-gemma``
    (the fine-tuned model) once Stage 5 produces it. ``min_epoch_ticks`` should be
    >= one measured RTT for the cell (300 is the calibrated default).
    """
    provider = LLMStructuralProvider(model_id=model_id, host=host)
    return StructuralDispatcher(provider, min_epoch_ticks=min_epoch_ticks)
