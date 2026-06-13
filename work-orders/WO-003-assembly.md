# WO-003: Stage-3 dataset assembly
Branch: laneb/wo-003
Status: HANDBACK

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
 "descriptor": <record["descriptor"]>,        # REQUIRED out-of-band metadata (see Split)
 "rationale": "<≤40-token teacher text>"      # OPTIONAL, teacher-only, NEVER in messages
}
```
- Carry `descriptor` on every sample as out-of-band metadata (NOT inside
  `messages`) so the split is auditable at the descriptor level — the gate checks
  leakage on `(regime, seed)`, not on RNG-dependent rendered prompts.
- ~85% plan-only (no `rationale` key), ~15% with a Tier-B rationale (the
  reasoning-distillation ablation set), applied to BOTH train and held-out. The
  rationale is metadata only — it must never appear inside `messages`, or it
  corrupts what the model learns to emit.
- Emit assistant `content` as a BARE JSON plan with NO turn terminator / EOS in
  the string. Turn terminators are the trainer's chat_template's job (next
  section) — hand-rolling `<end_of_turn>` here would double-inject.

## Chat template, EOS & the Modelfile — owned by Stage 4/5, gated before GPU
The adversarial format-fidelity audit (skyscraper-plan §7) flagged the train!=prod
risks that live OUTSIDE assembly. Assembly's contract is only role/content
messages; these are the binding requirements on the trainer and the Modelfile:
- **One chat_template, both sides.** The LoRA trainer (Unsloth/PEFT) and the
  served GGUF Modelfile MUST both use Gemma's official `chat_template` — the same
  one from the HF model used for the fine-tune. Do NOT rely on Ollama's default
  template: it can fold the system role into the first user turn, and Gemma has
  no native system turn, so the served token stream would differ from training.
- **EOS injection** comes from that chat_template (`<end_of_turn>`/`<eos>`); the
  pilot must confirm the model learned to stop (one non-grammar-constrained decode
  that ends cleanly after the JSON).
- The exact Modelfile is version-controlled at Stage 5 (`docs/training-plan.md`),
  with `num_ctx >= max assembled sequence length`, `temperature 0`, and the stop
  token set. A render-identity gate (HF `apply_chat_template` token ids ==
  Ollama's) gates the GPU run.

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
- **Implementation**: Created `scripts/assemble.py` implementing `build_sample(record: dict, rationale: str | None = None)`, `split(records: list[dict])`, and `assemble(records: list[dict], rationales: dict | None = None)`.
- **Formatting**: SFT samples are built strictly using the `build_structural_messages` and `structural_target_json` anchors from `elevatorsim.policy.structural`.
- **Metadata**: Out-of-band `descriptor` is preserved on every sample, and `rationale` is optionally added as metadata on ~15% of samples (neither leaks into messages).
- **Split validation**: Held-out split isolates two seeds per regime and the unseen `(floors=52, cars=10)` configuration.
- **Verification**: Verified using `tests/test_assemble.py` (all 7 tests passed).

## Audit findings
<filled by Claude>
