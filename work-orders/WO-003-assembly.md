# WO-003: Stage-3 dataset assembly
Branch: laneb/wo-003
Status: SPEC — gate test authored (tests/test_assemble.py); ready when WO-002
        labels exist (WO-002 is merged) and Tier-B rationales are produced

## Goal
Implement `scripts/assemble.py`: turn WO-002 labeled records into trainer-ready
SFT samples, split train / held-out, and emit JSONL. This is the LAST script
before the LoRA run, so the format must be exact — a prompt drift here is the #1
silent SFT killer (the model trains on one prompt, is served another).

## The train==prod anchor — USE IT, do not hand-roll the prompt
The exact prompt format is fixed in `policy/structural.py` and is shared with the
inference path (`policy/structural_agent.py`). You MUST build samples through it:
- `build_structural_messages(input_view)` -> the `[{system}, {user}]` pair.
- `structural_target_json(StructuralPlan(**label))` -> the assistant target string.
Never write your own `f"Traffic summary: ..."` or `json.dumps(label)` — call these.

## Sample format (chat JSONL)
Each labeled record -> one sample:
```
{"messages": [
    {"role": "system",    "content": <build_structural_messages[0].content>},
    {"role": "user",      "content": <build_structural_messages[1].content>},
    {"role": "assistant", "content": <structural_target_json(plan)>}   # bare {mode,hold}
 ],
 "rationale": "<≤40-token teacher text>"     # OPTIONAL, teacher-only, NEVER in messages
}
```
- ~85% plan-only (no `rationale` key), ~15% with a Tier-B rationale (the
  reasoning-distillation ablation set). The rationale is metadata only — it must
  never appear inside `messages`, or it corrupts what the model learns to emit.

## Required functions (the gate imports these by name)
- `build_sample(record: dict, rationale: str | None = None) -> dict`
- `split(records: list[dict]) -> dict`  → `{"train": [...], "heldout": [...]}`
- `assemble(records: list[dict], rationales: dict | None = None) -> {"train":[samples],"heldout":[samples]}`

## Held-out split (zero leakage)
- Hold out a fixed seed set per regime (2 seeds/regime), AND
- one entire **config never seen in training** — the `(floors=52, cars=10)` cell.
- Train and held-out must be disjoint; no held-out seed or the unseen config may
  appear in train.

## CLI
- `--labels data/stage2_labels.jsonl` `--rationales <path|none>`
  `--out-train data/sft_train.jsonl` `--out-heldout data/sft_heldout.jsonl`.
- `json.dumps(sample, sort_keys=True)` per line; create parent dirs.

## Hard prohibitions
- Output schema is `StructuralPlan` EXACTLY — assistant content is `{mode,hold}`
  only, via `structural_target_json`. No reasoning field on the model output.
- Build prompts ONLY through `build_structural_messages` (no inline templates).
- Do NOT edit `policy/`, `schemas.py`, `tests/`, or the oracle.
- `json.dumps(..., sort_keys=True)`.

## Gate tests (ALREADY AUTHORED — `tests/test_assemble.py`, gate-first)
Currently skips (no `assemble.py`); becomes enforced on implementation:
- samples built through the anchor; assistant target is a bare StructuralPlan
  (no reasoning leak); rationale teacher-only; every output parses as
  StructuralPlan; train/held-out disjoint with the unseen config held out.

## Writer handback
<filled by Antigravity>

## Audit findings
<filled by Claude>
