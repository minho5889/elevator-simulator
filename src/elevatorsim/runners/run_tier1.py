# src/elevatorsim/runners/run_tier1.py
"""Stochastic A/B simulation runner: LOOK Heuristic vs. DispatcherAgent."""

import sys
from elevatorsim.core.building import Building
from elevatorsim.core.car import Car
from elevatorsim.core.metrics import MetricsCollector
from elevatorsim.core.simulation import Simulation
from elevatorsim.core.traffic import TrafficGenerator
from elevatorsim.policy.heuristic import HeuristicDispatcher
from elevatorsim.policy.agentic import DispatcherAgent
from elevatorsim.config import seed_rng, get_gemini_api_key

def run_heuristic_stochastic(seed: int, ticks: int, arrival_rate: float, profile: str) -> MetricsCollector:
    """Run stochastic simulation with Heuristic (LOOK) policy."""
    print("\n" + "=" * 50)
    print(" RUNNING HEURISTIC STOCHASTIC BASELINE (LOOK)")
    print(f" Profile: {profile} | Arrival Rate: {arrival_rate} | Ticks: {ticks} | Seed: {seed}")
    print("=" * 50)

    # 1. Reset and Seed RNG
    seed_rng(seed)

    # 2. Instantiate core components
    building = Building(num_floors=5)
    car = Car(car_id="C1", initial_floor=0)
    dispatcher = HeuristicDispatcher()
    metrics = MetricsCollector()
    
    # 3. Instantiate TrafficGenerator
    traffic = TrafficGenerator(num_floors=5, arrival_rate=arrival_rate, profile=profile)
    
    # 4. Create and run simulation
    sim = Simulation(building, car, dispatcher, metrics, traffic_generator=traffic, verbose=True)
    sim.run_until_complete(max_ticks=ticks)
    
    metrics.print_summary("Heuristic LOOK Stochastic Summary")
    return metrics


def run_agentic_stochastic(seed: int, ticks: int, arrival_rate: float, profile: str) -> MetricsCollector:
    """Run stochastic simulation with Strands DispatcherAgent."""
    print("\n" + "=" * 50)
    print(" RUNNING AGENTIC STOCHASTIC POLICY (Strands + Gemini-3.5-Flash)")
    print(f" Profile: {profile} | Arrival Rate: {arrival_rate} | Ticks: {ticks} | Seed: {seed}")
    print("=" * 50)

    # 1. Reset and Seed RNG
    seed_rng(seed)

    # 2. Instantiate core components
    building = Building(num_floors=5)
    car = Car(car_id="C1", initial_floor=0)
    dispatcher = DispatcherAgent()
    metrics = MetricsCollector()
    
    # 3. Instantiate TrafficGenerator
    traffic = TrafficGenerator(num_floors=5, arrival_rate=arrival_rate, profile=profile)
    
    # 4. Create and run simulation
    sim = Simulation(building, car, dispatcher, metrics, traffic_generator=traffic, verbose=True)
    sim.run_until_complete(max_ticks=ticks)
    
    metrics.print_summary("Agentic Strands/Gemini Stochastic Summary")
    return metrics


def main() -> None:
    """Execute Tier 1 Stochastic Comparison."""
    seed = 42
    arrival_rate = 0.2
    profile = "UNIFORM"
    
    # CLI args override
    ticks = 50
    if "--full" in sys.argv:
        ticks = 150
        print("Running full 150-tick simulation. Note: This requires a paid Google AI Studio billing account to avoid daily rate limits.")

    # 1. Run the Heuristic LOOK baseline (requires no API key)
    heuristic_metrics = run_heuristic_stochastic(seed, ticks, arrival_rate, profile)
    
    # 2. Check if API Key is configured
    api_key = get_gemini_api_key()
    if not api_key:
        print("\n" + "!" * 80)
        print("WARNING: GEMINI_API_KEY is not set. Skipping agentic stochastic policy run.")
        print("To run the agentic comparison, populate GEMINI_API_KEY in your local .env file.")
        print("!" * 80 + "\n")
        return

    # 3. Warn about quota limits if running without --full
    if "--full" not in sys.argv:
        print("\n" + "*" * 80)
        print("NOTICE: Running a short 50-tick A/B simulation to preserve daily free tier quotas.")
        print("To run a full 150-tick simulation, pass the '--full' command-line flag.")
        print("*" * 80 + "\n")

    # 4. Run the Agentic policy (apples-to-apples comparison using same seed & traffic)
    try:
        agentic_metrics = run_agentic_stochastic(seed, ticks, arrival_rate, profile)
        
        # 5. Print A/B Comparison Report
        h_summary = heuristic_metrics.get_summary()
        a_summary = agentic_metrics.get_summary()
        
        print("\n" + "=" * 60)
        print(" TIER 1 STOCHASTIC PERFORMANCE COMPARISON")
        print("=" * 60)
        print(" Metric                  | Heuristic (LOOK) | Agentic (Gemini)")
        print("-------------------------|------------------|------------------")
        print(f" Total Ticks Run         | {h_summary['total_ticks']:<16} | {a_summary['total_ticks']:<16}")
        print(f" Total Car Movements     | {h_summary['total_car_moves']:<16} | {a_summary['total_car_moves']:<16}")
        print(f" Passengers Spawned      | {h_summary['passengers_spawned']:<16} | {a_summary['passengers_spawned']:<16}")
        print(f" Passengers Completed    | {h_summary['passengers_completed']:<16} | {a_summary['passengers_completed']:<16}")
        print("-------------------------|------------------|------------------")
        print(f" Avg Wait Time (ticks)   | {h_summary['avg_wait_time']:<16} | {a_summary['avg_wait_time']:<16}")
        print(f" Avg Transit Time (ticks)| {h_summary['avg_transit_time']:<16} | {a_summary['avg_transit_time']:<16}")
        print(f" Avg Total Time (ticks)  | {h_summary['avg_total_time']:<16} | {a_summary['avg_total_time']:<16}")
        print("=" * 60)
        print("Gemini decisions are non-deterministic and thinking is active by default.")
        print("=" * 60 + "\n")
        
    except Exception as e:
        print("\n" + "!" * 80)
        print(f"ERROR: Agentic policy execution failed: {e}")
        print("This is likely due to your Google AI Studio Free Tier daily quota (20 requests/day)")
        print("being exhausted. Enable pay-as-you-go billing to lift this limit.")
        print("!" * 80 + "\n")


if __name__ == "__main__":
    main()
