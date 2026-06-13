#!/usr/bin/env python3
# scripts/rationalize.py
"""Stage-2 Tier B — Teacher rationales generator (Lane C)."""

import os
import sys
import json
import time
import argparse
from typing import List, Dict, Any, Optional

# Ensure project root is in python path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from google import genai
from google.genai import types

SYSTEM_INSTRUCTION = (
    "You are a master elevator dispatching teacher. Your goal is to write a short, "
    "concise rationale (under 40 tokens) explaining why a structural dispatching "
    "plan was chosen by an offline search oracle.\n"
    "Respond in plain text with exactly one short sentence. Do not use markdown, backticks, or code blocks.\n\n"
    "Examples:\n"
    "- 'Destination dispatch is chosen to batch passengers and reduce stop count under heavy up-peak traffic.'\n"
    "- 'Conventional collective control is chosen because uniform interfloor traffic lacks dominant flow patterns.'\n"
    "- 'Static zoning is chosen to partition floors and prevent car clustering under mixed lunch traffic.'\n"
    "- 'Balanced holding is selected to trade off wait times with batch sizes at moderate load.'"
)

def rationalize_record(client: genai.Client, r: Dict[str, Any]) -> str:
    """Send record details to Gemini and return the <=40-token rationale."""
    descriptor = r["descriptor"]
    input_view = r["input_view"]
    label = r["label"]
    scored = r["scored"]
    
    # Format candidates list for context
    candidates_lines = []
    for c in sorted(scored, key=lambda x: x["cost"]):
        candidates_lines.append(
            f"Plan(mode={c['mode']}, hold={c['hold']}) -> cost={c['cost']} "
            f"(del={c['delivered']}, pend={c['pending']}, awt={c['mean_eff_wait']}, p95={c['p95']})"
        )
    candidates_str = "\n".join(candidates_lines[:4]) # top 4 plans
    
    prompt = (
        f"Regime: {descriptor['regime']} | Floors: {descriptor['floors']} | Cars: {descriptor['cars']}\n"
        f"Traffic Summary: {input_view}\n\n"
        f"Oracle Chosen Plan: mode={label['mode']}, hold={label['hold']}\n\n"
        f"Top Candidate Plan Costs:\n{candidates_str}\n\n"
        f"Write a concise explanation (<= 40 tokens) of why this plan was chosen."
    )
    
    # Simple retry loop for robustness / rate limits
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    max_output_tokens=100,
                    temperature=0.2
                )
            )
            rationale = response.text.strip()
            # Clean up newlines or quotes
            rationale = rationale.replace("\n", " ").strip('"').strip()
            return rationale
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"Error rationalizing seed {descriptor['seed']}: {e}")
                return "LOOK default fallback rationale due to API error"
            time.sleep(13)
            
    return "LOOK default fallback rationale"

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate teacher rationales for labeled records (Lane C).")
    parser.add_argument("--labels", default="data/stage2_labels.jsonl", help="Path to input labels JSONL.")
    parser.add_argument("--out", default="data/stage2_rationales.json", help="Path to output rationales mapping JSON.")
    parser.add_argument("--limit", type=int, default=5, help="Number of records to rationalize.")
    
    args = parser.parse_args()
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        from elevatorsim.config import get_gemini_api_key
        api_key = get_gemini_api_key()
        
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable is not set. Skipping rationale generation.")
        sys.exit(1)
        
    if not os.path.exists(args.labels):
        print(f"Error: Input labels file not found at {args.labels}")
        sys.exit(1)
        
    # Read labels
    records = []
    with open(args.labels, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
                
    # Sample subset
    if args.limit and args.limit < len(records):
        records = records[:args.limit]
        
    print(f"Generating rationales for {len(records)} records using Gemini...")
    client = genai.Client(api_key=api_key)
    
    rationales = {}
    for idx, r in enumerate(records):
        seed = r["descriptor"]["seed"]
        rationale = rationalize_record(client, r)
        rationales[str(seed)] = rationale
        print(f"[{idx+1}/{len(records)}] Seed {seed} -> '{rationale}'")
        time.sleep(1) # rate limit pacing
        
    # Write output JSON
    out_dir = os.path.dirname(args.out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(rationales, f, indent=2, sort_keys=True)
        
    print(f"Successfully wrote {len(rationales)} rationales to {args.out}")

if __name__ == "__main__":
    main()
