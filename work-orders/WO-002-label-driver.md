# WO-002: Stage-2 oracle label driver
Branch: laneb/wo-002
Status: READY — all prerequisites cleared (WO-001 merged; calibration locked;
        `switching` warmup reconstruct handler landed)

## Goal
Implement `scripts/label.py`: stream WO-001 descriptors, reconstruct each state
(`oracle.harvest_state`), label it (`oracle.label_decision(sim)` — call it with
NO weights/horizon/settle overrides; the LOCKED Stage-2 defaults are already the
oracle's defaults), and write training records
`{descriptor, input_view, label: {mode, hold}, scored}` as JSONL. `input_view`
is the serialized **`get_traffic_summary`** of the reconstructed state ONLY —
`json.dumps(sort_keys=True)`, ~200 chars. **Do NOT include `get_floor_calls` or
`get_all_cars_state`** in `input_view`: the G5 latency gate (2026-06-13) proved
the full call dump (~17 KB) overflows `gemma4:e4b` context and truncates output,
while the traffic summary alone decides the mode at 1.65s/100%-valid.

## Prerequisites (all cleared 2026-06-13)
- WO-001 merged: `scripts/harvest.py` emits descriptors; format final.
- Cost calibration locked + validated: `oracle.DEFAULT_WEIGHTS/HORIZON/SETTLE`
  (`scripts/calibrate.py`). Pass NO overrides — just `label_decision(sim)`.
- `switching` warmup is reconstructable: `oracle.harvest_state(**descriptor)`
  now handles every warmup value, so `harvest_state(**{k:v for k,v in d.items()
  if k in HARVEST_KEYS})` works for ALL descriptors (verified end-to-end).

## Files you may create/modify (when unblocked)
- `scripts/label.py` (new)

## Hard prohibitions
- Do NOT modify the oracle, the cost weights, the schemas, or `tests/`.
- Serialize the input view ONLY via the three frozen Strands tools — never a
  hand-rolled state serializer.
- `json.dumps(..., sort_keys=True)`.

## Gate tests (Lane A authors when unblocked)
- Records validate against `StructuralPlan`; `input_view` round-trips the tools;
  labeling is deterministic; the global RNG is unperturbed across the run.
