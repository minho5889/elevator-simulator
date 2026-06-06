# src/elevatorsim/runners/run_tier0.py
"""Scripted simulation runner comparison: Heuristic vs. Agentic Dispatching."""

from elevatorsim.core.building import Building
from elevatorsim.core.car import Car
from elevatorsim.core.passenger import Passenger
from elevatorsim.core.metrics import MetricsCollector
from elevatorsim.core.simulation import Simulation
from elevatorsim.policy.heuristic import HeuristicDispatcher
from elevatorsim.policy.agentic import DispatcherAgent
from elevatorsim.config import seed_rng, get_gemini_api_key

def build_scripted_scenario(sim: Simulation) -> None:
    """
    Populate a simulation with a standard scripted passenger request sequence.

    Scenario:
    - Tick 1: P1 at Floor 0 wants to go to Floor 4 (UP)
    - Tick 3: P2 at Floor 3 wants to go to Floor 1 (DOWN)
    - Tick 5: P3 at Floor 2 wants to go to Floor 4 (UP)
    """
    sim.schedule_passenger(1, Passenger("P1", source_floor=0, target_floor=4, spawn_time=1))
    sim.schedule_passenger(3, Passenger("P2", source_floor=3, target_floor=1, spawn_time=3))
    sim.schedule_passenger(5, Passenger("P3", source_floor=2, target_floor=4, spawn_time=5))


def run_heuristic_baseline(seed: int) -> MetricsCollector:
    """Run simulation with Heuristic (LOOK) policy."""
    print("\n" + "=" * 50)
    print(f" RUNNING HEURISTIC BASELINE (LOOK) - Seed {seed}")
    print("=" * 50)
    
    # 1. Reset and Seed RNG
    seed_rng(seed)
    
    # 2. Instantiate components
    building = Building(num_floors=5)
    car = Car(car_id="C1", initial_floor=0)
    dispatcher = HeuristicDispatcher()
    metrics = MetricsCollector()
    
    # 3. Create simulation
    sim = Simulation(building, car, dispatcher, metrics, verbose=True)
    build_scripted_scenario(sim)
    
    # 4. Execute simulation
    sim.run_until_complete(max_ticks=50)
    
    metrics.print_summary("Heuristic (LOOK) Policy Summary")
    return metrics


def run_agentic_policy(seed: int) -> MetricsCollector:
    """Run simulation with LLM-backed Strands Agent policy."""
    print("\n" + "=" * 50)
    print(f" RUNNING AGENTIC POLICY (Strands + Gemini-3.5-Flash) - Seed {seed}")
    print("=" * 50)
    
    # 1. Reset and Seed RNG
    seed_rng(seed)
    
    # 2. Instantiate components
    building = Building(num_floors=5)
    car = Car(car_id="C1", initial_floor=0)
    dispatcher = DispatcherAgent()
    metrics = MetricsCollector()
    
    # 3. Create simulation
    sim = Simulation(building, car, dispatcher, metrics, verbose=True)
    build_scripted_scenario(sim)
    
    # 4. Execute simulation
    sim.run_until_complete(max_ticks=50)
    
    metrics.print_summary("Agentic (Strands + Gemini) Policy Summary")
    return metrics


def main() -> None:
    """Run A/B Comparison."""
    seed = 42
    
    # Run the LOOK baseline (always runs, no API key needed)
    heuristic_metrics = run_heuristic_baseline(seed)
    
    # Check if Gemini key is available for the agentic run
    api_key = get_gemini_api_key()
    if not api_key:
        print("\n" + "!" * 80)
        print("WARNING: GEMINI_API_KEY is not set. Skipping agentic policy run.")
        print("To run the agentic comparison, populate GEMINI_API_KEY in your .env file.")
        print("!" * 80 + "\n")
        return

    # Run the agentic policy (apples-to-apples comparison on the same scenario and seed)
    agentic_metrics = run_agentic_policy(seed)
    
    # Print A/B Comparison Report
    h_summary = heuristic_metrics.get_summary()
    a_summary = agentic_metrics.get_summary()
    
    print("\n" + "=" * 60)
    print(" A/B PERFORMANCE COMPARISON")
    print("=" * 60)
    print(" Metric                  | Heuristic (LOOK) | Agentic (Gemini)")
    print("-------------------------|------------------|------------------")
    print(f" Total Ticks to Clear    | {h_summary['total_ticks']:<16} | {a_summary['total_ticks']:<16}")
    print(f" Total Car Movements     | {h_summary['total_car_moves']:<16} | {a_summary['total_car_moves']:<16}")
    print(f" Completed Passengers    | {h_summary['passengers_completed']:<16} | {a_summary['passengers_completed']:<16}")
    print(f" Avg Wait Time (ticks)   | {h_summary['avg_wait_time']:<16} | {a_summary['avg_wait_time']:<16}")
    print(f" Avg Transit Time (ticks)| {h_summary['avg_transit_time']:<16} | {a_summary['avg_transit_time']:<16}")
    print(f" Avg Total Time (ticks)  | {h_summary['avg_total_time']:<16} | {a_summary['avg_total_time']:<16}")
    print("=" * 60)
    print("Note: Gemini decisions are non-deterministic due to legacy temperature parameters")
    print("being deprecated in Gemini 3.5 Flash and thought preservation being enabled.")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
