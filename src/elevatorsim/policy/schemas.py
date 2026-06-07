# src/elevatorsim/policy/schemas.py
"""Pydantic schemas defining the structured outputs required from the agentic policy."""

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
