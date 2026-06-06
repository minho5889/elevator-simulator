# src/elevatorsim/policy/schemas.py
"""Pydantic schemas defining the structured outputs required from the agentic policy."""

from pydantic import BaseModel, Field, field_validator

class DispatchDecision(BaseModel):
    """Structured output representing a single elevator dispatching decision."""

    target_floor: int = Field(
        ...,
        description="The target floor (0-indexed) where the elevator car should go next."
    )
    reasoning: str = Field(
        ...,
        description="Concise rationale explaining the choice of the target floor."
    )

    @field_validator("target_floor")
    @classmethod
    def validate_floor(cls, value: int) -> int:
        """Ensure the target floor index is valid (0 to 4)."""
        if not (0 <= value <= 4):
            raise ValueError(f"Target floor {value} must be between 0 and 4 inclusive.")
        return value
