# src/elevatorsim/policy/agentic.py
"""Strands-backed agentic elevator dispatcher policy using Gemini.

Implements both the single-car ``Dispatcher`` protocol (``dispatch``) and the
multi-car ``GroupDispatcher`` protocol (``dispatch_group``), so it stays at parity
with ``GroupHeuristicDispatcher`` in Tier 2 multi-car A/B comparisons. Prompts are
built from the live building (floor count, car bank) rather than hardcoded to the
Tier 0 5-floor geometry.
"""

import time
from typing import Any, Dict

from strands import Agent

from elevatorsim.policy.base import Dispatcher, GroupDispatcher
from elevatorsim.policy.schemas import DispatchDecision, GroupDispatchDecision
from elevatorsim.config import get_gemini_model, get_gemini_api_key
from elevatorsim.tools.sim_tools import (
    set_active_simulation,
    clear_active_simulation,
    get_elevator_state,
    get_all_cars_state,
    get_floor_calls,
)

# Seconds to wait before each Gemini call to respect Google AI Studio free-tier
# rate limits (~15 RPM). Two calls per tick => ~26s/tick of pacing.
RATE_LIMIT_SECONDS = 13


class DispatcherAgent(Dispatcher, GroupDispatcher):
    """
    Agentic elevator dispatcher policy.

    Uses the Strands Agent SDK and a Gemini model to observe state via tools and
    output a validated Pydantic decision. Supports both single-car and multi-car
    (group) dispatch.
    """

    def __init__(self) -> None:
        """Initialize the dispatcher agent policy."""
        self.model = None

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _ensure_model(self) -> None:
        """Lazily construct the Gemini model, requiring an API key."""
        api_key = get_gemini_api_key()
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set in environment or .env file. "
                "The agentic policy cannot run without an API key."
            )
        if self.model is None:
            self.model = get_gemini_model()

    @staticmethod
    def _rate_limit(simulation: Any, note: str) -> None:
        """Pause to stay under Google AI Studio free-tier rate limits."""
        if getattr(simulation, "verbose", False):
            print(f"[RATE LIMITING] Waiting {RATE_LIMIT_SECONDS}s {note}...")
        time.sleep(RATE_LIMIT_SECONDS)

    # ------------------------------------------------------------------
    # Single-car dispatch (legacy Tier 0/1 protocol)
    # ------------------------------------------------------------------

    def dispatch(self, simulation: Any) -> int | None:
        """
        Determine the next target floor for a single car using an LLM-backed agent.

        Args:
            simulation: Active simulation instance (``simulation.car`` is the car
                under consideration).

        Returns:
            Target floor index (0-indexed) or None if idle.
        """
        self._ensure_model()

        num_floors = simulation.building.num_floors
        top = num_floors - 1
        system_prompt = (
            f"You are a smart elevator dispatcher managing a single elevator in a "
            f"{num_floors}-floor building (floors 0 to {top}).\n"
            "Your objective is to minimize average passenger wait times and route the "
            "car efficiently.\n\n"
            "Guidelines:\n"
            "- First, gather the current state using your tools.\n"
            f"- Next, decide the optimal target floor (0-{top}) to navigate to next.\n"
            "- Ground your decisions strictly in the simulation state returned by the tools."
        )

        agent = Agent(
            model=self.model,
            tools=[get_elevator_state, get_floor_calls],
            system_prompt=system_prompt,
        )

        set_active_simulation(simulation)
        try:
            self._rate_limit(simulation, "to avoid Google AI Studio Free Tier 429 quota limits")
            agent(
                "Observe the current elevator state and floor queues using tools. "
                "Analyze which calls are outstanding."
            )

            self._rate_limit(simulation, "before structured decision call")
            decision: DispatchDecision = agent.structured_output(
                DispatchDecision,
                f"Make your final target floor selection. Choose the next floor "
                f"(0-{top}) the elevator should target.",
            )

            target = self._clamp(decision.target_floor, num_floors)
            if getattr(simulation, "verbose", False):
                print(
                    f"\n[AGENTIC POLICY DECISION] Target: Floor {target} | "
                    f"Reasoning: {decision.reasoning}\n"
                )
            return target
        finally:
            clear_active_simulation()

    # ------------------------------------------------------------------
    # Multi-car group dispatch (Tier 2 protocol)
    # ------------------------------------------------------------------

    def dispatch_group(self, simulation: Any) -> Dict[str, int | None]:
        """
        Assign target floors to all idle cars in the bank in a single LLM call.

        Args:
            simulation: Active simulation instance (``simulation.cars`` is the bank).

        Returns:
            Dictionary mapping ``car_id`` -> target floor (0-indexed). Only idle
            cars are assigned; non-idle or unknown car ids are dropped.
        """
        self._ensure_model()

        num_floors = simulation.building.num_floors
        top = num_floors - 1
        idle_cars = [
            c for c in simulation.cars
            if c.door_state == "CLOSED" and c.target_floor is None
        ]
        idle_ids = {c.car_id for c in idle_cars}
        if not idle_ids:
            return {}

        idle_list = ", ".join(sorted(idle_ids))
        system_prompt = (
            f"You are a group elevator controller managing a bank of "
            f"{len(simulation.cars)} elevators in a {num_floors}-floor building "
            f"(floors 0 to {top}).\n"
            "Your objective is to minimize average passenger wait times by spreading "
            "the cars across outstanding calls rather than sending them all to the "
            "same floor.\n\n"
            "Guidelines:\n"
            "- First, gather the current state of all cars and floor queues using your tools.\n"
            f"- Then assign a target floor (0-{top}) only to currently idle cars.\n"
            "- Avoid assigning two idle cars to the same floor unless demand requires it.\n"
            "- Ground your decisions strictly in the simulation state returned by the tools."
        )

        agent = Agent(
            model=self.model,
            tools=[get_all_cars_state, get_floor_calls],
            system_prompt=system_prompt,
        )

        set_active_simulation(simulation)
        try:
            self._rate_limit(simulation, "to avoid Google AI Studio Free Tier 429 quota limits")
            agent(
                "Observe the state of every car and all floor queues using tools. "
                "Analyze which calls are outstanding and which cars are idle."
            )

            self._rate_limit(simulation, "before structured group decision call")
            decision: GroupDispatchDecision = agent.structured_output(
                GroupDispatchDecision,
                f"Assign target floors (0-{top}) to the idle cars: {idle_list}. "
                "Return one assignment per car you choose to dispatch.",
            )

            assignments: Dict[str, int | None] = {}
            for a in decision.assignments:
                if a.car_id in idle_ids and a.car_id not in assignments:
                    assignments[a.car_id] = self._clamp(a.target_floor, num_floors)

            if getattr(simulation, "verbose", False):
                print(
                    f"\n[AGENTIC GROUP DECISION] Assignments: {assignments} | "
                    f"Reasoning: {decision.reasoning}\n"
                )
            return assignments
        finally:
            clear_active_simulation()

    @staticmethod
    def _clamp(floor: int, num_floors: int) -> int:
        """Clamp a model-proposed floor into the valid building range."""
        return max(0, min(floor, num_floors - 1))
