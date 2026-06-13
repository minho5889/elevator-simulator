# WO-002: Stage-2 oracle label driver
Branch: laneb/wo-002
Status: BLOCKED (on WO-001 output format + Lane-A cost calibration)

## Goal
Implement `scripts/label.py`: stream WO-001 descriptors, reconstruct each state
(`oracle.harvest_state`), label it (`oracle.label_decision` with the LOCKED
`(weights, horizon, settle_ticks)`), and write training records
`{descriptor, input_view, label: {mode, hold}, scored}` as JSONL. `input_view`
is the serialized `get_all_cars_state` + `get_floor_calls` + `get_traffic_summary`
of the reconstructed state (the frozen Gemma input).

## Blocked until
1. WO-001 lands (descriptor JSONL format final).
2. **Lane A locks the Stage-2 oracle calibration** — `weights`, `horizon`,
   `settle_ticks` chosen so the oracle policy ≥ best fixed mode in every regime
   (the lunch myopia closed). Those constants are passed into this driver; do
   NOT pick them here. Until then this WO is a spec only.

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
