# src/elevatorsim/policy/base.py
"""Shared Dispatcher interface definition."""

from typing import Protocol, runtime_checkable, Any

@runtime_checkable
class Dispatcher(Protocol):
    """
    Interface/Protocol defining the contract for all elevator dispatchers.
    
    Both HeuristicDispatcher and DispatcherAgent must implement this interface,
    allowing them to be transparently swapped in the Simulation engine.
    """

    def dispatch(self, simulation: Any) -> int | None:
        """
        Given the current state of the simulation, make a decision on the next target floor.

        Args:
            simulation: The active Simulation instance to query

        Returns:
            The floor index (0-indexed) where the car should navigate next, 
            or None if the car should remain standby/idle.
        """
        ...
