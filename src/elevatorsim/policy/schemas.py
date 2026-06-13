# src/elevatorsim/policy/schemas.py
"""Pydantic schemas defining the structured outputs required from the agentic policy."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class DispatchDecision(BaseModel):
    """Structured output representing a single-car elevator dispatching decision."""

    target_floor: int = Field(
        ...,
        description="The target floor (0-indexed) where the elevator car should go next.",
    )
    reasoning: str = Field(
        ...,
        description="Concise rationale explaining the choice of the target floor.",
    )

    @field_validator("target_floor")
    @classmethod
    def validate_floor(cls, value: int) -> int:
        """Ensure the target floor is a non-negative index.

        The upper bound depends on the building height, which is not known to the
        schema; the dispatcher validates the target against ``building.num_floors``.
        """
        if value < 0:
            raise ValueError(f"Target floor {value} must be a non-negative index.")
        return value


class CarAssignment(BaseModel):
    """A single car -> target-floor assignment within a group dispatch decision."""

    car_id: str = Field(..., description="The id of the car being assigned (e.g. 'C1').")
    target_floor: int = Field(
        ...,
        description="The target floor (0-indexed) this car should travel to next.",
    )

    @field_validator("target_floor")
    @classmethod
    def validate_floor(cls, value: int) -> int:
        if value < 0:
            raise ValueError(f"Target floor {value} must be a non-negative index.")
        return value


class GroupDispatchDecision(BaseModel):
    """Structured output assigning target floors to idle cars in a multi-car bank."""

    assignments: list[CarAssignment] = Field(
        default_factory=list,
        description=(
            "One entry per idle car that should be dispatched this tick. "
            "Omit a car to leave it idle. Do not assign cars that are not idle."
        ),
    )
    reasoning: str = Field(
        ...,
        description="Concise rationale explaining how calls were distributed across cars.",
    )


# ---------------------------------------------------------------------------
# FROZEN structural action space (skyscraper P7 / action-space freeze, 2026-06-12).
#
# This supersedes the mid-rise GroupDispatchDecision (car -> target floor) as the
# learned policy's contract at skyscraper scale. Rationale and the empirical
# winner grid that fixed these exact fields are in docs/skyscraper-plan.md
# (§ Action-space freeze) and docs/training-plan.md Stage 3.
#
# Design (synthesized from a 4-design adversarial panel + the measured winner grid):
#   - The policy picks a STRUCTURAL MODE per epoch (>= 1 round trip), not a
#     next-floor per car. Within-mode routing is the deterministic collective /
#     batching / sectoring machinery already in policy/{heuristic,destination,
#     zoning}.py — never a model output.
#   - Both fields are str Literals so Ollama/llama.cpp GBNF grammar-constrains
#     them: an out-of-range value is structurally un-emittable, which is the
#     unanimous fix for the G4 >=99.5%-valid gate on a 4-bit 4B model. No nested
#     objects, no arrays sized by floor/car count, no free-text. ~10 output
#     tokens => the G5 <=2s latency budget is met per epoch (one call per ~RTT,
#     not per tick).
#   - NO reasoning field: Gemma emits the plan only. Teacher rationales (Gemini)
#     are attached at dataset-assembly time, never decoded at inference — the
#     single largest latency win (a reasoning field measured ~3x slower).
#
# Deliberately EXCLUDED after measuring the live engine (do not re-add without
# new evidence): dd_immediate mode (dominated by dd_delayed at every cell in the
# winner grid — kept only as an arena ablation rung), weighted zone-split
# templates, and the dd-lobby split-bank hybrid (both unimplemented and
# unmeasured). See docs/skyscraper-plan.md for the deferred-extensions note.
# ---------------------------------------------------------------------------

StructuralMode = Literal["conventional", "dd_delayed", "zoned"]
HoldPolicy = Literal["depart_now", "balanced", "fill_batch"]


class StructuralPlan(BaseModel):
    """The learned skyscraper group-control decision for one epoch.

    Each field is independently measured to win some region of the operating
    envelope, so none is dead weight the model must learn to ignore:
      - ``mode`` selects the structural strategy. Measured winners (HC5, 5 seeds,
        all heights 20/32/48): ``dd_delayed`` for up-peak and down-peak,
        ``zoned`` for lunch, ``conventional`` for uniform interfloor.
      - ``hold`` is the departure-control preset (batch fullness + patience).
        Near-inert under saturation but a real lever at moderate load, where
        ``fill_batch`` roughly halves the P95 wait tail at no throughput cost.
        Inert for ``conventional`` (no batching); the oracle tie-breaks it to a
        canonical default there so the model learns a clean pairing.
    """

    mode: StructuralMode = Field(
        ...,
        description=(
            "Structural control strategy for the next epoch. "
            "'conventional' = collective/LOOK with main-terminal parking; "
            "'dd_delayed' = destination dispatch with delayed assignment; "
            "'zoned' = static contiguous sectoring, one band per car."
        ),
    )
    hold: HoldPolicy = Field(
        ...,
        description=(
            "Departure-control preset. 'depart_now' sends a car on any call; "
            "'balanced' holds for a 75%-full batch up to ~30 ticks; "
            "'fill_batch' holds for a full batch up to ~60 ticks. "
            "Ignored when mode='conventional'."
        ),
    )
