# src/elevatorsim/policy/skylobby.py
"""Sky-lobby / shuttle group control for supertall towers [Report §5.1].

Beyond ~40-50 floors a single flat elevator group stops scaling: shaft count
grows with population while core area grows with shaft count, cannibalising the
rentable plate. The supertall answer is hierarchical — express **shuttles** carry
passengers from the ground to a **sky lobby**, where they transfer to a **local
group** serving a bounded upper zone, replacing one impossible group with a tree
of feasible ones at the cost of a transfer per trip.

This implements a two-zone tower (one sky lobby) for the up-peak case that sizes
supertall buildings: shuttle cars run express 0 <-> sky_lobby; local cars run
within [sky_lobby, top]. Passenger transfer is handled by the engine
(``Passenger.final_target`` + the transfer branch in ``Simulation._step_car``);
boarding discipline is the per-car ``service_range`` so a shuttle never carries a
high-zone passenger and vice versa. Low-rise service, down-traffic, and folding
this into the learned action space are later refinements — this increment proves
the topology beats a flat bank at height.
"""

import random
from typing import Any, Dict, List, Set, Tuple

from elevatorsim.core.building import Building
from elevatorsim.core.car import Car
from elevatorsim.core.metrics import MetricsCollector
from elevatorsim.core.passenger import Passenger
from elevatorsim.core.simulation import Simulation
from elevatorsim.policy.base import GroupDispatcher
from elevatorsim.policy.baselines import MainTerminalParkingLook
from elevatorsim.policy.heuristic import GroupHeuristicDispatcher


class SkyLobbyDispatcher(GroupDispatcher):
    """Two-zone hierarchical dispatcher: express shuttles + a local high group.

    Shuttle cars cycle 0 <-> sky_lobby (boarding only sky-lobby-bound riders);
    local cars run LOOK within [sky_lobby, top], collecting transferred riders at
    the sky lobby. Service zones are installed once on the cars so boarding stays
    disciplined without per-passenger assignment.
    """

    def __init__(self, sky_lobby: int, shuttle_ids: List[str], local_ids: List[str]) -> None:
        self.sky_lobby = sky_lobby
        self.shuttle_ids: Set[str] = set(shuttle_ids)
        self.local_ids: Set[str] = set(local_ids)
        self._zoned = False

    def _ensure_zones(self, simulation: Any) -> None:
        if self._zoned:
            return
        top = simulation.building.num_floors - 1
        for car in simulation.cars:
            if car.car_id in self.shuttle_ids:
                car.service_range = (0, self.sky_lobby)
            elif car.car_id in self.local_ids:
                car.service_range = (self.sky_lobby, top)
        self._zoned = True

    def dispatch_group(self, simulation: Any) -> Dict[str, int | None]:
        self._ensure_zones(simulation)
        building = simulation.building
        top = building.num_floors - 1
        assignments: Dict[str, int | None] = {}

        idle = [c for c in simulation.cars if c.door_state == "CLOSED" and c.target_floor is None]
        ground_waiting = len(building.get_waiting_at(0)) > 0
        active = set(building.get_active_calls())

        for car in sorted(idle, key=lambda c: c.car_id):
            if car.car_id in self.shuttle_ids:
                # Express leg: deliver to the sky lobby, else fetch from ground,
                # else stage at the ground terminal ready for the next load.
                if car.passenger_count > 0:
                    assignments[car.car_id] = self.sky_lobby
                elif ground_waiting:
                    assignments[car.car_id] = 0
                elif car.current_floor != 0:
                    assignments[car.car_id] = 0
            else:
                # Local high group: deliver onboard riders by LOOK, else pick up
                # at the sky lobby / nearest high call, else stage at the lobby.
                onboard = {p.target_floor for p in car.passengers}
                if onboard:
                    assignments[car.car_id] = GroupHeuristicDispatcher._look_target(
                        car, onboard, set())
                else:
                    high_calls = {f for f in active if self.sky_lobby <= f <= top}
                    if high_calls:
                        assignments[car.car_id] = min(
                            high_calls, key=lambda f: (abs(f - car.current_floor), f))
                    elif car.current_floor != self.sky_lobby:
                        assignments[car.car_id] = self.sky_lobby
        return assignments


def arrival_schedule(
    seed: int, ticks: int, top: int, sky_lobby: int, arrival_rate: float
) -> List[Tuple[int, int]]:
    """Deterministic ground->high up-peak arrival list: [(tick, final_dest), ...].

    Generated once from a private RNG so the SAME traffic can be replayed through
    both the flat bank and the sky-lobby tower — an apples-to-apples topology
    comparison where only the routing differs. Supports super-saturation
    (rate > 1) the same way the main TrafficGenerator does.
    """
    rng = random.Random(seed)
    schedule: List[Tuple[int, int]] = []
    for tick in range(1, ticks + 1):
        n = int(arrival_rate)
        frac = arrival_rate - n
        if frac > 0 and rng.random() < frac:
            n += 1
        for _ in range(n):
            schedule.append((tick, rng.randint(sky_lobby + 1, top)))
    return schedule


def _run(sim: Simulation, schedule: List[Tuple[int, int]], make_passenger, ticks: int) -> Dict[str, Any]:
    counter = 0
    for tick, dest in schedule:
        counter += 1
        sim.schedule_passenger(tick, make_passenger(counter, dest))
    sim.run_until_complete(max_ticks=ticks)
    delivered = len(sim.metrics.completed_passengers)
    return {
        "delivered": delivered,
        "spawned": len(sim.metrics.all_passengers),
        "hc5": round(delivered / ticks * 300, 2),
        "completion": round(delivered / len(sim.metrics.all_passengers), 3)
        if sim.metrics.all_passengers else 0.0,
    }


def run_flat(
    seed: int, *, floors: int, cars: int, sky_lobby: int, arrival_rate: float,
    ticks: int, capacity: int = 24, stop_ticks: int = 9, transfer_ticks: int = 1,
    speed: float = 1.0,
) -> Dict[str, Any]:
    """Baseline: one flat group serving ground -> high directly (no transfer)."""
    top = floors - 1
    schedule = arrival_schedule(seed, ticks, top, sky_lobby, arrival_rate)
    building = Building(num_floors=floors)
    car_list = [Car(f"C{i + 1}", 0, capacity=capacity, speed=speed) for i in range(cars)]
    sim = Simulation(
        building, car_list[0], MainTerminalParkingLook(), MetricsCollector(),
        verbose=False, extra_cars=car_list[1:], stop_ticks=stop_ticks, transfer_ticks=transfer_ticks,
    )
    return _run(sim, schedule, lambda i, dest: Passenger(f"P{i}", 0, dest, 0), ticks)


def run_skylobby(
    seed: int, *, floors: int, shuttle_cars: int, local_cars: int, sky_lobby: int,
    arrival_rate: float, ticks: int, capacity: int = 24, stop_ticks: int = 9,
    transfer_ticks: int = 1, shuttle_speed: float = 1.0, local_speed: float = 1.0,
) -> Dict[str, Any]:
    """Sky-lobby tower: ``shuttle_cars`` express + ``local_cars`` high-zone."""
    top = floors - 1
    schedule = arrival_schedule(seed, ticks, top, sky_lobby, arrival_rate)
    building = Building(num_floors=floors)
    shuttles = [Car(f"S{i + 1}", 0, capacity=capacity, speed=shuttle_speed)
                for i in range(shuttle_cars)]
    locals_ = [Car(f"L{i + 1}", sky_lobby, capacity=capacity, speed=local_speed)
               for i in range(local_cars)]
    car_list = shuttles + locals_
    dispatcher = SkyLobbyDispatcher(
        sky_lobby, [c.car_id for c in shuttles], [c.car_id for c in locals_])
    sim = Simulation(
        building, car_list[0], dispatcher, MetricsCollector(),
        verbose=False, extra_cars=car_list[1:], stop_ticks=stop_ticks, transfer_ticks=transfer_ticks,
    )
    # Leg 1 target is the sky lobby; final_target is the true high-zone floor.
    return _run(
        sim, schedule,
        lambda i, dest: Passenger(f"P{i}", 0, sky_lobby, 0, final_target=dest), ticks)
