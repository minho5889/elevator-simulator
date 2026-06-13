# WO-003: Stage-3 dataset assembly
Branch: laneb/wo-003
Status: BLOCKED (on WO-002 records + Tier-B rationales)

## Goal
Implement `scripts/assemble.py`: take WO-002 labeled records (+ optional Tier-B
teacher rationales from Antigravity/Gemini), render each into the exact frozen
SFT sample — structural system prompt + serialized input view → `StructuralPlan`
JSON output — split train / held-out (2 seeds per regime cell + one unseen
config), and emit the trainer-ready files. ~85% plan-only, ~15% with a
teacher-only rationale field (reasoning-distillation ablation; never decoded at
inference).

## Blocked until
WO-002 produces labeled records, and Tier-B rationales exist for the sampled
subset.

## Files you may create/modify (when unblocked)
- `scripts/assemble.py` (new)

## Hard prohibitions
- The output schema is `StructuralPlan` EXACTLY (`policy/schemas.py`) — no extra
  fields on Gemma's output; the rationale is a separate teacher-only column.
- Do NOT edit schemas, the system prompt contract, or `tests/`.

## Gate tests (Lane A authors when unblocked)
- Every assembled output parses as `StructuralPlan`; the held-out split is
  disjoint by seed/config; the chat template matches what the trainer renders
  (this is the pre-GPU **format-fidelity audit**, run by Lane A — see
  docs/training-plan.md Stage 3).
