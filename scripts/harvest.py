#!/usr/bin/env python3
# scripts/harvest.py
"""Stage-1 decision-point descriptor harvester."""

import os
import sys
import json
import argparse
import random
from typing import List, Dict, Any, Optional

def generate_descriptors(target: int, seed_base: int) -> List[Dict[str, Any]]:
    """Generate stratified decision-point descriptors deterministically."""
    rng = random.Random(seed_base)
    descriptors = []
    
    regimes = ["up_peak", "down_peak", "lunch", "uniform"]
    warmups = ["conventional", "dd_delayed", "zoned", "switching"]
    capacities = [16, 20, 24]
    arrival_rates = [0.4, 0.8, 1.2, 2.0]
    refusal_weights = [120, 150, 200]
    
    bands = [
        (20, 28),
        (30, 40),
        (44, 60)
    ]
    
    for i in range(target):
        regime = regimes[i % len(regimes)]
        warmup = warmups[(i // len(regimes)) % len(warmups)]
        
        band = bands[i % 3]
        floors = rng.randint(band[0], band[1])
        
        cars = rng.randint(4, 12)
        capacity = rng.choice(capacities)
        arrival_rate = rng.choice(arrival_rates)
        
        ticks_choices = list(range(80, 401, 20))
        harvest_tick = rng.choice(ticks_choices)
        
        if (i % 100) < 18:
            weight_limit = rng.choice(refusal_weights)
        else:
            weight_limit = None
            
        seed = rng.randint(0, 1000000)
        
        d = {
            "regime": regime,
            "seed": seed,
            "floors": floors,
            "cars": cars,
            "capacity": capacity,
            "arrival_rate": arrival_rate,
            "stop_ticks": 9,
            "transfer_ticks": 1,
            "warmup": warmup,
            "harvest_tick": harvest_tick,
            "weight_limit": weight_limit,
        }
        descriptors.append(d)
        
    return descriptors

def main() -> None:
    parser = argparse.ArgumentParser(description="Harvest Stage-1 decision-point descriptors.")
    parser.add_argument("--target", type=int, default=50000, help="Target number of descriptors to generate.")
    parser.add_argument("--seed-base", type=int, default=20000, help="Base seed for reproducibility.")
    parser.add_argument("--out", type=str, default="data/stage1_descriptors.jsonl", help="Output JSONL path.")
    
    args = parser.parse_args()
    
    # Generate descriptors
    descriptors = generate_descriptors(args.target, args.seed_base)
    
    # Create parent directories
    out_dir = os.path.dirname(args.out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        
    # Write JSONL file
    with open(args.out, "w", encoding="utf-8") as f:
        for d in descriptors:
            f.write(json.dumps(d, sort_keys=True) + "\n")
            
    # Compute stats for stratification report
    total = len(descriptors)
    if total > 0:
        regime_counts = {r: 0 for r in ["up_peak", "down_peak", "lunch", "uniform"]}
        band_counts = {"20-28": 0, "30-40": 0, "44-60": 0}
        refusals = 0
        
        for d in descriptors:
            regime_counts[d["regime"]] += 1
            f = d["floors"]
            if f <= 28:
                band_counts["20-28"] += 1
            elif f <= 40:
                band_counts["30-40"] += 1
            else:
                band_counts["44-60"] += 1
                
            if d.get("weight_limit") is not None:
                refusals += 1
                
        regime_pct = ", ".join(f"{r}: {regime_counts[r]/total*100:.1f}%" for r in regime_counts)
        band_counts_str = ", ".join(f"{b}: {band_counts[b]}" for b in band_counts)
        refusal_pct = refusals / total * 100
        
        print(f"Stratification Report: Regimes: {{{regime_pct}}} | Height Bands: {{{band_counts_str}}} | Refusals: {refusal_pct:.1f}%")

if __name__ == "__main__":
    main()
