#!/usr/bin/env python3
# scripts/label.py
"""Stage-2 oracle label driver."""

import os
import sys
import json
import argparse
from typing import List, Dict, Any

# Ensure project root is in python path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, "scripts"))

from elevatorsim.config import RNG
from elevatorsim.tools.sim_tools import set_active_simulation, clear_active_simulation, get_traffic_summary
import oracle

def label_descriptor(d: Dict[str, Any]) -> Dict[str, Any]:
    """Label a single descriptor and return the training record."""
    harvest_keys = {
        "regime", "seed", "harvest_tick", "floors", "cars", "capacity",
        "arrival_rate", "stop_ticks", "transfer_ticks", "warmup", "weight_limit",
    }
    kwargs = {k: v for k, v in d.items() if k in harvest_keys}
    
    rng_state = RNG.getstate()
    try:
        sim = oracle.harvest_state(**kwargs)
        
        # input_view is the serialized get_traffic_summary ONLY
        set_active_simulation(sim)
        try:
            traffic_summary = get_traffic_summary()
        finally:
            clear_active_simulation()
            
        input_view = json.dumps(traffic_summary, sort_keys=True)
        
        # Label the state using the locked Stage-2 oracle defaults
        best_plan, scored = oracle.label_decision(sim)
        
        # Return record matching structural contract
        return {
            "descriptor": d,
            "input_view": input_view,
            "label": {
                "mode": best_plan.mode,
                "hold": best_plan.hold,
            },
            "scored": scored
        }
    finally:
        RNG.setstate(rng_state)

def label_descriptors(descriptors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Label a list of descriptors, preserving the global RNG state."""
    rng_state = RNG.getstate()
    try:
        records = []
        for d in descriptors:
            records.append(label_descriptor(d))
        return records
    finally:
        RNG.setstate(rng_state)

def main() -> None:
    parser = argparse.ArgumentParser(description="Label Stage-1 descriptors using the oracle.")
    parser.add_argument("--in", dest="in_path", default="data/stage1_descriptors.jsonl", help="Path to input JSONL descriptors.")
    parser.add_argument("--out", dest="out_path", default="data/stage2_labels.jsonl", help="Path to output JSONL labeled records.")
    parser.add_argument("--limit", type=int, default=None, help="Max number of descriptors to process.")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.in_path):
        print(f"Error: Input descriptors file not found at {args.in_path}")
        sys.exit(1)
        
    print(f"Streaming descriptors from {args.in_path}...")
    descriptors = []
    with open(args.in_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                descriptors.append(json.loads(line))
                if args.limit is not None and len(descriptors) >= args.limit:
                    break
                    
    print(f"Loaded {len(descriptors)} descriptors. Labeling...")
    
    # Process and write records
    out_dir = os.path.dirname(args.out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        
    count = 0
    with open(args.out_path, "w", encoding="utf-8") as f:
        for d in descriptors:
            record = label_descriptor(d)
            f.write(json.dumps(record, sort_keys=True) + "\n")
            count += 1
            if count % 100 == 0:
                print(f"Processed {count}/{len(descriptors)}...")
                
    print(f"Successfully wrote {count} labeled records to {args.out_path}")

if __name__ == "__main__":
    main()
