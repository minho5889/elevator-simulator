# src/elevatorsim/policy/agentic.py
"""Strands-backed agentic elevator dispatcher policy using Gemini."""

from typing import Any
from strands import Agent
from elevatorsim.policy.base import Dispatcher
from elevatorsim.policy.schemas import DispatchDecision
from elevatorsim.config import get_gemini_model, get_gemini_api_key
from elevatorsim.tools.sim_tools import (
    set_active_simulation,
    clear_active_simulation,
    get_elevator_state,
    get_floor_calls
)

class DispatcherAgent(Dispatcher):
    """
    Agentic elevator dispatcher policy.
    
    Uses Strands Agent SDK and a Gemini 3.5 Flash model to observe state via tools
    and output a validated Pydantic decision.
    """

    def __init__(self) -> None:
        """Initialize the dispatcher agent policy."""
        self.model = None

    def dispatch(self, simulation: Any) -> int | None:
        """
        Determine the next target floor using an LLM-backed Strands agent.

        Args:
            simulation: Active simulation instance

        Returns:
            Target floor index (0-indexed) or None if idle
        """
        api_key = get_gemini_api_key()
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set in environment or .env file. "
                "The agentic policy cannot run without an API key."
            )

        if self.model is None:
            self.model = get_gemini_model()

        # Set up system guidelines for the elevator agent
        system_prompt = (
            "You are a smart elevator dispatcher managing a single elevator in a 5-floor building "
            "(floors 0 to 4).\n"
            "Your objective is to minimize average passenger wait times and route the car efficiently.\n\n"
            "Guidelines:\n"
            "- First, gather the current state using your tools.\n"
            "- Next, decide the optimal target floor (0-4) to navigate to next.\n"
            "- Ground your decisions strictly in the simulation state returned by the tools."
        )

        # Initialize the Strands Agent with our state-reading tools
        agent = Agent(
            model=self.model,
            tools=[get_elevator_state, get_floor_calls],
            system_prompt=system_prompt
        )

        # Set the active simulation context so our tools can read its data
        set_active_simulation(simulation)

        try:
            # Phase 1: Tool Call / State Gathering
            # The agent is triggered to inspect the environment and output text reasoning.
            agent("Observe the current elevator state and floor queues using tools. Analyze which calls are outstanding.")

            # Phase 2: Structured Output Response
            # We call the structured_output method to retrieve the validated Pydantic model.
            # Message history is carried over automatically.
            decision: DispatchDecision = agent.structured_output(
                DispatchDecision,
                "Make your final target floor selection. Choose the next floor (0-4) the elevator should target."
            )

            # Log the decision trace to stdout for debugging and learning
            if simulation.verbose:
                print(
                    f"\n[AGENTIC POLICY DECISION] Target: Floor {decision.target_floor} | "
                    f"Reasoning: {decision.reasoning}\n"
                )

            return decision.target_floor

        finally:
            # Always clear the context to avoid side effects across ticks/runs
            clear_active_simulation()
