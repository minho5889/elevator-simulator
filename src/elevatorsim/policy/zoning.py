# src/elevatorsim/policy/zoning.py
"""Static zoning / sectoring group control [Report §2.3, §5.1].

Partition the upper floors into contiguous zones, one car per zone — the
classical conventional up-peak strategy: shrink each round trip's stop set and
travel envelope by dedicating cars to floor bands. Zoning is the conceptual
ancestor of destination dispatch's batching [Report §2.3] and of static
sky-lobby partitioning [Report §5.1], and it reuses the same pre-boarding
information machinery (assigned boarding + kiosk turnstile) as zone *signage*:
"Floors 12–15 — Car E".

Static map only (P5): equal contiguous zones, fixed for the run.
Regime-adaptive re-zoning is deliberately NOT implemented here — redrawing the
zone map is part of the learned policy's structural action space (P7).
"""

from typing import Any, Dict, List

from elevatorsim.policy.destination import DestinationGroupDispatcher


class ZonedStaticDispatcher(DestinationGroupDispatcher):
    """One contiguous static zone per car; zone signage via assigned boarding.

    Assignment is trivially immediate — the zone map is static, so the owning
    car is known the moment a passenger registers; timing carries no
    information here (contrast gate S5, where it does for free assignment).
    Departure control (batch threshold + patience), turnstile boarding, LOOK
    routing over obligations, and main-terminal parking are all inherited from
    the destination-dispatch family; only the assignment rule differs:

        zone floor = destination for lobby boardings (up-peak signage),
                     source otherwise (down-peak / interfloor sector collection)

    Zone discipline is strict: overflow queues for its zone car rather than
    spilling to neighbours — that is what makes zoned stop-counts collapse.
    """

    def __init__(self, batch_threshold: float = 0.75, patience_ticks: int = 30) -> None:
        super().__init__(
            assignment="immediate",
            batch_threshold=batch_threshold,
            patience_ticks=patience_ticks,
        )
        self._zone_car: Dict[int, str] = {}

    def _build_zone_map(self, num_floors: int, cars: List[Any]) -> None:
        """Equal contiguous partition of floors 1..N-1 across cars (by id)."""
        upper = list(range(1, num_floors))
        ids = [c.car_id for c in sorted(cars, key=lambda c: c.car_id)]
        base, extra = divmod(len(upper), len(ids))
        start = 0
        for i, cid in enumerate(ids):
            size = base + (1 if i < extra else 0)
            for floor in upper[start:start + size]:
                self._zone_car[floor] = cid
            start += size

    def dispatch_group(self, simulation: Any) -> Dict[str, int | None]:
        if not self._zone_car:
            self._build_zone_map(simulation.building.num_floors, simulation.cars)
        return super().dispatch_group(simulation)

    def _assign_immediate(self, p: Any, cars: List[Any], committed: Dict[str, List[Any]]) -> None:
        """Zone lookup replaces marginal-cost search: the map is the policy."""
        zone_floor = p.target_floor if p.source_floor == 0 else p.source_floor
        cid = self._zone_car.get(zone_floor)
        if cid is None:
            # Defensive: more cars than upper floors leaves some floors unmapped
            # only when num_floors < 2; fall back deterministically.
            cid = min(cars, key=lambda c: c.car_id).car_id
        p.assigned_car_id = cid
        committed.setdefault(cid, []).append(p)
