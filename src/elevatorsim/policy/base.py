# src/elevatorsim/policy/base.py
"""Shared Dispatcher interface definitions for single-car and multi-car policies."""

from typing import Protocol, runtime_checkable, Any, Dict


@runtime_checkable
class Dispatcher(Protocol):
    """
    Interface/Protocol defining the contract for single-car elevator dispatchers.
    
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


@runtime_checkable
class GroupDispatcher(Protocol):
    """
    Interface for multi-car group dispatchers (Tier 2+).

    A GroupDispatcher decides targets for ALL idle cars in a single call,
    enabling coordinated group scheduling across an elevator bank.
    """

    def dispatch_group(self, simulation: Any) -> Dict[str, int | None]:
        """
        Assign target floors to all idle cars in the elevator bank.

        Args:
            simulation: The active Simulation instance to query.
                Access ``simulation.cars`` for the full car bank,
                ``simulation.building`` for floor queues and hall calls.

        Returns:
            Dictionary mapping ``car_id`` -> target floor (0-indexed), or
            ``None`` if that car should remain idle. Only idle cars
            (door closed, no target) should be assigned.
        """
        ...
