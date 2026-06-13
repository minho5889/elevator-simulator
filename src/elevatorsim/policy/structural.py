# src/elevatorsim/policy/structural.py
"""Execution layer for the frozen StructuralPlan contract [skyscraper P7].

The learned policy (Gemma) emits a ``StructuralPlan`` (mode + hold) per epoch;
this module turns a plan into the concrete underlying group dispatcher and runs
it. The schema itself is frozen in ``policy/schemas.py``; this is the runtime
that the same plans drive at training-label time (the oracle) and at inference
(``StructuralDispatcher`` with a Gemma-backed plan provider).

Key invariant — clean mode handover: destination dispatch and zoning admit
passengers through a kiosk turnstile (``Car.assigned_only`` + a passenger's
``assigned_car_id``). Switching modes mid-flight would strand passengers already
committed to a now-defunct zone/car, and — because that committed state lives on
the cloned objects — would also make an oracle rollout diverge from what the live
system can reproduce. ``reset_assignment_state`` clears the turnstile on every
mode change so the incoming mode starts from a clean slate.
"""

import json
from typing import Any, Callable, Dict, List

from elevatorsim.policy.base import GroupDispatcher
from elevatorsim.policy.baselines import MainTerminalParkingLook
from elevatorsim.policy.destination import DestinationGroupDispatcher
from elevatorsim.policy.schemas import StructuralPlan
from elevatorsim.policy.zoning import ZonedStaticDispatcher

# FROZEN structural system prompt — part of the I/O contract. The training input
# (WO-003 assembly) and the inference path (policy/structural_agent.py) must use
# THIS exact string so train == prod. Concise by design: it rides in every
# training sample and competes for the G5 latency budget. The mode rules track
# the measured winner grid (skyscraper-plan §7); the 0-shot base model already
# follows them in 3 of 4 regimes (G5 gate).
STRUCTURAL_SYSTEM_PROMPT = (
    "You are a skyscraper elevator group controller. Each epoch, from the traffic "
    "summary, choose one structural control plan.\n"
    "mode:\n"
    "- dd_delayed: lobby-dominated traffic (high frac_origin_lobby or frac_dest_lobby) "
    "— destination dispatch.\n"
    "- zoned: mixed / lunch traffic (lobby plus interfloor) — static sectoring.\n"
    "- conventional: uniform interfloor traffic — collective control.\n"
    "hold (departure control): fill_batch when load is light, balanced normally, "
    "depart_now when saturated.\n"
    "Respond with the plan only."
)

# THE train==prod format anchor. Both the inference path (LLMStructuralProvider)
# and the Stage-3 assembly (WO-003) MUST build the model's prompt through
# ``build_structural_messages`` and target through ``structural_target_json`` —
# never inline their own f-string — so a fine-tuned model sees byte-identical
# prompts at train and inference time. A drift of one space or word here is the
# #1 silent SFT killer (the model trained on prompt A, served prompt B).
STRUCTURAL_USER_TEMPLATE = "Traffic summary: {input_view}\nPlan:"


def build_structural_messages(
    input_view: str, system_prompt: str = STRUCTURAL_SYSTEM_PROMPT
) -> List[Dict[str, str]]:
    """The exact (system, user) message pair the model sees, train and prod.

    ``input_view`` is the serialized ``get_traffic_summary`` (the only model
    input — see the G5 amendment). Returns the two prompt turns; assembly appends
    the assistant target (``structural_target_json``), inference reads the
    model's reply.
    """
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": STRUCTURAL_USER_TEMPLATE.format(input_view=input_view)},
    ]


def structural_target_json(plan: StructuralPlan) -> str:
    """The canonical assistant-target string for a plan — what the model is
    trained to emit and what it must produce at inference. Field order matches
    the schema (mode, hold); compact separators; no trailing whitespace."""
    return json.dumps({"mode": plan.mode, "hold": plan.hold}, separators=(",", ":"))


# Departure-control presets: hold name -> (batch_threshold, patience_ticks).
# These are the exact knobs on DestinationGroupDispatcher / ZonedStaticDispatcher;
# the learned policy chooses among presets rather than emitting raw floats, so the
# output stays grammar-constrainable [schemas.py].
HOLD_PRESETS: Dict[str, tuple] = {
    "depart_now": (0.0, 0),
    "balanced": (0.75, 30),
    "fill_batch": (1.0, 60),
}

# The full candidate menu the oracle enumerates (3 modes x 3 holds = 9). Constant
# in floors N and cars L — the entire point of the mode-selector framing.
ALL_PLANS: List[StructuralPlan] = [
    StructuralPlan(mode=m, hold=h)
    for m in ("conventional", "dd_delayed", "zoned")
    for h in ("depart_now", "balanced", "fill_batch")
]


def plan_to_dispatcher(plan: StructuralPlan) -> GroupDispatcher:
    """Build the concrete group dispatcher that executes ``plan``."""
    batch_threshold, patience = HOLD_PRESETS[plan.hold]
    if plan.mode == "conventional":
        # Collective/LOOK + main-terminal parking; hold is inert here.
        return MainTerminalParkingLook()
    if plan.mode == "dd_delayed":
        return DestinationGroupDispatcher(
            "delayed", batch_threshold=batch_threshold, patience_ticks=patience
        )
    if plan.mode == "zoned":
        return ZonedStaticDispatcher(
            batch_threshold=batch_threshold, patience_ticks=patience
        )
    raise ValueError(f"Unknown structural mode: {plan.mode!r}")


def reset_assignment_state(simulation: Any) -> None:
    """Clear destination-dispatch turnstile state across the bank.

    Call on every mode switch (and at the start of each oracle candidate rollout)
    so the incoming mode is not handed stranded ``assigned_car_id`` commitments
    from the outgoing one. Onboard passengers are untouched — they are mid-ride
    and committed to delivery, not to a turnstile.
    """
    for car in simulation.cars:
        car.assigned_only = False
    building = simulation.building
    for floor in range(building.num_floors):
        for p in building.get_waiting_at(floor):
            p.assigned_car_id = None


class StructuralDispatcher(GroupDispatcher):
    """Production surface: run a plan, re-query the provider once per epoch.

    ``plan_provider(simulation) -> StructuralPlan`` is the learned policy (Gemma)
    at inference, the oracle's argmin at evaluation, or a constant for tests. The
    provider is consulted only at epoch boundaries — never per tick — so the
    expensive call (a model decode) fires ~once per round trip while the cheap
    deterministic within-mode machinery runs every tick.

    ``min_epoch_ticks`` must be >= one measured round trip for the cell, so a
    committed trip is never re-moded mid-RTT (the stranded-turnstile hazard).
    """

    def __init__(
        self,
        plan_provider: Callable[[Any], StructuralPlan],
        min_epoch_ticks: int = 60,
    ) -> None:
        self.plan_provider = plan_provider
        self.min_epoch_ticks = min_epoch_ticks
        self._plan: StructuralPlan | None = None
        self._inner: GroupDispatcher | None = None
        self._epoch_start = 0

    @property
    def current_plan(self) -> StructuralPlan | None:
        """The plan committed for the current epoch (None before the first)."""
        return self._plan

    def dispatch_group(self, simulation: Any) -> Dict[str, int | None]:
        now = getattr(simulation, "current_time", 0)
        if self._inner is None or (now - self._epoch_start) >= self.min_epoch_ticks:
            self._recommit(simulation, now)
        return self._inner.dispatch_group(simulation)

    def _recommit(self, simulation: Any, now: int) -> None:
        plan = self.plan_provider(simulation)
        mode_changed = self._plan is None or plan.mode != self._plan.mode
        plan_changed = self._plan is None or plan != self._plan
        if mode_changed:
            # Clean handover; preserves within-mode inner state across same-mode
            # epochs (zone map, committed batches live on passengers, not here).
            reset_assignment_state(simulation)
        if plan_changed:
            self._inner = plan_to_dispatcher(plan)
        self._plan = plan
        self._epoch_start = now
