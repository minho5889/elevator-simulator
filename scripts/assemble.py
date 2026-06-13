#!/usr/bin/env python3
# scripts/assemble.py
"""Stage-3 dataset assembly."""

import os
import sys
import json
import argparse
from typing import List, Dict, Any, Optional

# Ensure project root is in python path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from elevatorsim.policy.schemas import StructuralPlan
from elevatorsim.policy.structural import (
    STRUCTURAL_SYSTEM_PROMPT,
    build_structural_messages,
    structural_target_json,
)

def build_sample(record: Dict[str, Any], rationale: Optional[str] = None) -> Dict[str, Any]:
    """Build a single SFT sample from a labeled record."""
    input_view = record["input_view"]
    msgs = build_structural_messages(input_view)
    
    # Append the assistant target plan
    plan = StructuralPlan(**record["label"])
    msgs.append({
        "role": "assistant",
        "content": structural_target_json(plan)
    })
    
    sample = {
        "messages": msgs,
        "descriptor": record["descriptor"]
    }
    if rationale is not None:
        sample["rationale"] = rationale
        
    return sample

def split(records: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Split records into train and heldout sets with zero leakage."""
    # Heldout config: floors == 52 and cars == 10
    heldout_unseen = [
        r for r in records 
        if r["descriptor"]["floors"] == 52 and r["descriptor"]["cars"] == 10
    ]
    
    others = [
        r for r in records 
        if not (r["descriptor"]["floors"] == 52 and r["descriptor"]["cars"] == 10)
    ]
    
    # Find all unique seeds per regime for the remaining records
    regime_seeds = {}
    for r in others:
        regime = r["descriptor"]["regime"]
        seed = r["descriptor"]["seed"]
        if regime not in regime_seeds:
            regime_seeds[regime] = set()
        regime_seeds[regime].add(seed)
        
    # Pick first 2 seeds per regime as held-out seeds
    heldout_seeds_map = {}
    for regime, seeds in regime_seeds.items():
        sorted_seeds = sorted(list(seeds))
        heldout_seeds_map[regime] = set(sorted_seeds[:2])
        
    train = []
    heldout = list(heldout_unseen)
    
    for r in others:
        regime = r["descriptor"]["regime"]
        seed = r["descriptor"]["seed"]
        if seed in heldout_seeds_map.get(regime, set()):
            heldout.append(r)
        else:
            train.append(r)
            
    return {"train": train, "heldout": heldout}

def assemble(records: List[Dict[str, Any]], rationales: Optional[Dict[Any, str]] = None) -> Dict[str, List[Dict[str, Any]]]:
    """Assemble SFT samples from records, splitting train and heldout."""
    split_data = split(records)
    train_recs = split_data["train"]
    heldout_recs = split_data["heldout"]
    
    train_samples = []
    for idx, r in enumerate(train_recs):
        seed = r["descriptor"]["seed"]
        rationale = None
        if rationales:
            if seed in rationales:
                r_val = rationales[seed]
            elif str(seed) in rationales:
                r_val = rationales[str(seed)]
            else:
                r_val = None
                
            if r_val is not None:
                if idx % 7 == 0:
                    rationale = r_val
        train_samples.append(build_sample(r, rationale))
        
    heldout_samples = []
    for idx, r in enumerate(heldout_recs):
        seed = r["descriptor"]["seed"]
        rationale = None
        if rationales:
            if seed in rationales:
                r_val = rationales[seed]
            elif str(seed) in rationales:
                r_val = rationales[str(seed)]
            else:
                r_val = None
                
            if r_val is not None:
                if idx % 7 == 0:
                    rationale = r_val
        heldout_samples.append(build_sample(r, rationale))
        
    return {"train": train_samples, "heldout": heldout_samples}

def main() -> None:
    parser = argparse.ArgumentParser(description="Assemble SFT dataset.")
    parser.add_argument("--labels", default="data/stage2_labels.jsonl", help="Path to input labels JSONL.")
    parser.add_argument("--rationales", default="none", help="Path to input rationales JSON, or 'none'.")
    parser.add_argument("--out-train", default="data/sft_train.jsonl", help="Path to output train JSONL.")
    parser.add_argument("--out-heldout", default="data/sft_heldout.jsonl", help="Path to output held-out JSONL.")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.labels):
        print(f"Error: Input labels file not found at {args.labels}")
        sys.exit(1)
        
    # Load labels
    records = []
    with open(args.labels, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
                
    # Load rationales
    rationales = None
    if args.rationales and args.rationales.lower() != "none":
        print(f"Loading rationales from {args.rationales}...")
        with open(args.rationales, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if content:
                try:
                    rationales = json.loads(content)
                except Exception:
                    rationales = {}
                    for line in content.splitlines():
                        line = line.strip()
                        if line:
                            data = json.loads(line)
                            if "seed" in data and "rationale" in data:
                                rationales[data["seed"]] = data["rationale"]
                            else:
                                for k, v in data.items():
                                    rationales[k] = v
                                    
    # Assemble SFT samples
    print(f"Assembling {len(records)} records...")
    dataset = assemble(records, rationales)
    train_samples = dataset["train"]
    heldout_samples = dataset["heldout"]
    
    # Create output directories
    for path in (args.out_train, args.out_heldout):
        out_dir = os.path.dirname(path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
            
    # Write train samples
    with open(args.out_train, "w", encoding="utf-8") as f:
        for s in train_samples:
            f.write(json.dumps(s, sort_keys=True) + "\n")
            
    # Write heldout samples
    with open(args.out_heldout, "w", encoding="utf-8") as f:
        for s in heldout_samples:
            f.write(json.dumps(s, sort_keys=True) + "\n")
            
    print(f"Successfully assembled SFT dataset:")
    print(f"  Train samples:   {len(train_samples)} -> {args.out_train}")
    print(f"  Heldout samples: {len(heldout_samples)} -> {args.out_heldout}")

if __name__ == "__main__":
    main()
