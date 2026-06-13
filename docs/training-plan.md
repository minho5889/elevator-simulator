# Training Plan: Fine-Tuning Gemma 4 e4b as an Elevator Dispatcher

*Plan of record for making the local `gemma4:e4b` model (8.0B params, ~4B active, Q4_K_M, Ollama) a genuinely strong AI Brain, using Antigravity + Gemini 3.5 as the teacher/judge stack. Grounded throughout in `docs/research/elevator-dispatch-algorithms.md` (cited as [Report §n]).*

> **Amendment (2026-06-12) — skyscraper pivot + action-space freeze complete.** `docs/skyscraper-plan.md` moved the learned action space up a layer: a per-epoch `StructuralPlan` (mode + hold), not a next-floor pick. The freeze is **done** — the contract (`policy/schemas.py` `StructuralPlan`), execution (`policy/structural.py`), input tools (`tools/sim_tools.py` incl. `get_traffic_summary`), and the CRN oracle (`scripts/oracle.py`) are built and gated. Stages 1–3 below are **re-specced against it** and Lane B is open (WO-001..003). Stage 0 and the Stage 4–6 mechanics are unaffected.

---

## 1. Objective and success criteria

Train Gemma 4 e4b to dispatch elevators in this repo's simulator well enough to **beat the LOOK heuristic per traffic regime** — including uniform/interfloor traffic, the regime where learned policies historically *lose* to trivial heuristics ([Report §4.2], Yavaş 2024: DQN lost uniform traffic by 37%).

**Acceptance gates** (all measured on held-out seeds, never-trained scenarios):

| Gate | Criterion |
|---|---|
| G1 | ≥ LOOK on average waiting time in **each** of: up-peak, down-peak, lunch, uniform — not on a blended average [Report §8: "single blended average is disqualifying"] |
| G2 | No starvation regression: P95 waiting time ≤ LOOK's P95 in every regime [Report §1.2: tail, not mean, is where greedy fails] |
| G3 | Weight-aware: fewer boarding refusals per delivered passenger than LOOK at 300kg limit (the lever LOOK is blind to — our simulator models refusals; the report flags weight-aware dispatching as an open problem [Report §9.6]) |
| G4 | Valid structured output ≥ 99.5% (parse failures count as forfeited turns) |
| G5 | Latency: ≤ 2 s per decision on the M4 via Ollama (turn-based sim tolerates this; keep prompts/outputs short — repo already has Gemma latency mitigations, commit `cd6a15e`) |

**Report metrics to log for every run:** AWT, ATTD, squared wait, P95 wait, energy, HC5-equivalent (delivered per 50 turns), refusal count [Report §8 metrics discipline].

---

## 2. Strategy: distillation, not RL

The report's central verified lesson: **no RL dispatcher has ever shipped**; the production-grade lineage is engineered optimization, and the one industrial lab that evaluated RL rejected it for convergence cost [Report §4.2, Nikovski & Brand 2003 / US 7,014,015]. We adopt the lesson instead of repeating the mistake:

- **Supervised fine-tuning (behavior cloning) from labels we can compute to be near-optimal offline.** The simulator is deterministic given a seed — we can afford expensive offline search per decision that no real-time controller could run [Report §2.1: the <500 ms budget is the production constraint; offline labeling has no such budget].
- **Gemini 3.5 as teacher for *reasoning*, search as teacher for *answers*.** LLM rationales make Gemma generalize; simulator-verified search makes labels correct. Never trust the teacher's floor choice without simulator scoring.
- **Optional preference round (DPO) scored by the simulator** — offline, no online exploration on "live" passengers, mirroring the report's structural argument for why engineered systems win [Report §4.2 closing paragraph].

---

## 3. Pipeline overview

```
Stage 0  Eval arena (build FIRST)          — this repo, headless Python
Stage 1  Decision-point harvesting          — this repo, headless Python
Stage 2  Label generation                   — oracle search (local) + Gemini 3.5 (Antigravity)
Stage 3  Dataset assembly + QC              — local + Gemini 3.5 as judge (Antigravity)
Stage 4  LoRA fine-tune                     — cloud GPU (recommended) or M4/MLX
Stage 5  Convert → GGUF → Ollama → evaluate — this repo
Stage 6  (Optional) DPO round from arena    — repeat 4–5
```

### Stage 0 — Build the evaluation arena first

Extend the existing core into a headless arena runner (`scripts/arena.py`):
- Inputs: dispatcher name, regime (UNIFORM / DOWN_PEAK / UP_PEAK / LUNCH*), floors (5–10), cars (1–6), weight limit, seed list (≥20 per cell), ticks (100+).
- Outputs: per-run JSON of all report metrics (§1 table).
- Baseline ladder to implement/verify, per the report's canon [Report §8]: FCFS → nearest-car → LOOK (exists) → ETA-cost assignment (worth adding; ~50 lines) → the fine-tuned model.
- *Lunch regime doesn't exist in `traffic.py` yet — add a bidirectional profile with an incoming component [Report §3.3].*

**Why first:** every later stage needs this to score labels, filter data, and gate releases. Without it we'd be training blind.

> **Re-specced 2026-06-12 against the frozen structural action space** (`docs/skyscraper-plan.md` §7). The action is now a per-epoch `StructuralPlan` (`mode` ∈ {conventional, dd_delayed, zoned} × `hold` ∈ {depart_now, balanced, fill_batch}), not a per-car next floor. The oracle is built and gated (`scripts/oracle.py`, `tests/test_structural.py`).

### Stage 1 — Harvest decision-point descriptors

A decision point is an **epoch-boundary state** (≥ 1 measured RTT apart), not a per-tick state. Because the simulator is deterministic given a seed, a decision point is stored as a compact **descriptor** — `(regime, seed, floors, cars, capacity, arrival_rate, stop_ticks, transfer_ticks, warmup_mode, harvest_tick)` — that Stage 2 reconstructs exactly via `oracle.harvest_state(...)`, rather than pickling 50k full simulation states. Determinism is the storage format.

Sampling grid: regimes × heights (20–60 floors) × cars (4–12) × arrival_rate (moderate 0.4 → super-saturated 2.0) × weight limits × seeds, **× warmup_mode** (run the warmup under each of the three structural modes *and* a mode-switching policy). The warmup-mode sweep is mandatory and is a finding of the freeze: a single-mode warmup biases the harvested state toward that mode (measured — a conventional-warmed state under-credits `zoned`), so the corpus must cover the states each mode actually produces. Oversample refusal-rich (tight weight-limit) cells (G3 curriculum). Target **~50k descriptors**, stratified so each regime is ≥ 20% and each height band is represented — the Crites & Barto trap is one-regime training [Report §4.2].

**Lane B — WO-001.** Pure stratified enumeration/sampling logic; gate-testable on stratification proportions, count, and determinism. No engine edits.

### Stage 2 — Label generation (two tiers)

**Tier A — Oracle labels (bulk, free, local).** For each descriptor: reconstruct the state (`harvest_state`), call `oracle.label_decision(sim, horizon, weights, settle_ticks)` — which enumerates all **9** candidate plans (constant in N and L), rolls each forward under **Common Random Numbers** (the snapshot/restore that makes candidates differ only by action — see the freeze §7 catch #1), and returns the argmin-cost plan with an explicit tie-break. Measured throughput: ~1.5–4 ms per candidate → ~50k labels in well under an hour on the M4, ~8× headroom.

**Cost-function + horizon + settle calibration — LOCKED (2026-06-12).** Labels are judged by the *oracle policy*, not by matching a single-mode HC5 grid: `scripts/calibrate.py` drives a `StructuralDispatcher(plan_provider=oracle)` full-episode across all regimes and reports oracle-vs-best-fixed-mode HC5. The locked config is `weights={wait:1.0, p95:0.1, energy:0.005, hc5:0.5, refusals:2.0}`, `horizon=300`, `settle_ticks=300` — now the `oracle.py` defaults. With it the oracle policy **beats or matches the best fixed mode in every regime** (up-peak 1.07×, down-peak 1.00×, lunch 0.99×, uniform 1.00×), and it **generalises to held-out seeds and a held-out height** (48fl: all regimes ≥ 1.00×). The `settle` period was the lever — it credits the steady-state advantage of slow-starting `zoned` that a myopic window misses, closing the freeze's lunch gap (0.88 → 1.02). Re-run `calibrate.py` after any oracle/cost/dispatcher change.

**Tier B — Teacher rationales (Antigravity, Gemini 3.5).** Sample 3–5k diverse labeled descriptors (stratified, refusal-heavy oversampled). Prompt Gemini with the serialized state view + the oracle's chosen plan + the full scored candidate table + Report §8 principles, asking for a **≤40-token rationale** justifying the plan in dispatching terms (regime → mode, stop-batching, tail guard, parking). The oracle decides; the teacher explains. Gemini never overrides the plan — disagreements are flagged for re-simulation, never substituted [`docs/antigravity-master-prompt.md` §6].

> **Quota warning:** the repo's Gemini key is free-tier (20 req/day). Tier B needs your Antigravity/AI-Pro quota; batch 10 states per call.

### Stage 3 — Dataset assembly

Each training sample = the **exact frozen production I/O contract** (`policy/schemas.py`):
- *Input:* the structural system prompt + the serialized **`get_traffic_summary`** view (`json.dumps(sort_keys=True)`, ~200 chars). **G5-amended (2026-06-13):** do NOT include `get_floor_calls` (its ~17 KB per-passenger dump overflows `gemma4:e4b` context and truncates output) — the traffic summary is the sufficient statistic for the mode decision and is what the latency gate validated at 1.65s.
- *Output:* a `StructuralPlan` JSON — `{"mode": "...", "hold": "..."}`. **No reasoning field on Gemma's output** (the single biggest G5 latency win; thinking ON measured 12× slower); teacher rationales live in a separate, teacher-only field for the optional reasoning-distillation variant, never decoded at inference.
- *Inference path:* a single direct `ollama.chat(..., format=StructuralPlan.model_json_schema(), think=False)` call — **not** Strands `agent.structured_output`, which truncated on the real model.

Mix: ~85% plan-only samples, ~15% with teacher rationale (for the reasoning-distillation ablation). Hold out: 2 seeds per regime cell, plus one entire config never seen in training (e.g., 52 floors / 10 cars) for generalization. QC: Gemini-as-judge spot-checks 500 samples for state/label consistency.

**Lane B — WO-002 (label driver) + WO-003 (assembly).** The labeling loop and the record assembler are well-specified scripts over the Lane-A oracle and frozen schemas; gate-tested on schema validity and determinism. The cost-weight calibration and the format-fidelity audit below stay Lane A.

**Format-fidelity audit (pre-GPU gate):** before any Stage-4 spend, a Lane-A audit (Claude, this repo) validates ~500 assembled records by round-tripping them through the production Strands structured-output schemas (`policy/schemas.py`) and re-rendering the exact chat template the trainer will use. Template/format mismatch is the #1 silent SFT killer; catching it here costs minutes, catching it at Stage 5 (G4) costs a GPU run.

### Stage 4 — LoRA fine-tune (decision fork)

| Option | Where | Feasibility on this project | Recommendation |
|---|---|---|---|
| **A. Cloud GPU QLoRA (Unsloth/PEFT)** | Colab/RunPod A100 or T4 | 8B base in 4-bit QLoRA fits in 16–24 GB VRAM; hours not days; Unsloth's Gemma support is mature — **verify gemma4/e4b support at execution time**; export merged weights → GGUF | **Recommended.** Fastest iteration, cheapest failure |
| B. Local MLX on the M4 | This Mac (16 GB) | mlx-lm LoRA on a 4-bit 8B is *borderline* on 16 GB unified memory — small batch (1–2), gradient accumulation, slow (days for 50k samples); fine for a 5k-sample pilot | Use for the **pilot run only** |
| C. Vertex AI managed tuning | Google Cloud | Clean fit with the Antigravity/Google stack if Gemma 4 tuning is offered there; less control over export path to GGUF | Fallback if A hits gemma4-support gaps |

Hyperparameter starting points: LoRA r=16, α=32, lr 1e-4 cosine, 2–3 epochs, target modules = attention + MLP projections, **text tower only** (freeze the model's vision/audio towers — they're dead weight for this task). Keep a ~5% general-instruction replay mix to limit catastrophic forgetting (the model still has to parse instructions).

**Pilot first:** 5k samples → quick LoRA → Stage 5 eval. If the pilot doesn't move AWT at all, the bug is in data format or prompt mismatch, not scale. Then the full run.

### Stage 5 — Deploy and evaluate

1. Merge LoRA → convert to GGUF (llama.cpp **current master** — required for gemma4 GGUF support — `convert_hf_to_gguf.py`, Q4_K_M to match current footprint) → `ollama create elevator-gemma -f Modelfile`.
2. Point the arena at it: `structural:elevator-gemma` rung (or `OLLAMA_MODEL_ID=elevator-gemma`). The P7 inference surface (`policy/structural_agent.py`) needs no code change — the fine-tuned model drops into the validated direct-`ollama.chat` path.
3. Run the Stage-0 arena: fine-tuned `structural` vs the full baseline ladder, all regimes, held-out seeds. Gate on G1–G5 (and the per-regime structural winner grid).
4. If gates pass: regenerate presets with the new model (`LLM_PROVIDER=gemma`, see memory note — verify no mock fallback), confirm the preset races still tell an honest story, ship.

**Pre-GPU train==prod checklist (from the format-fidelity audit, skyscraper-plan §7 — a format slip here silently poisons the whole run, attributable to no metric). The served base is `google/gemma-4-E4B-it`; Gemma 4 uses a NEW turn scheme — `<bos>` once, then `<|turn>ROLE\n … <turn|>\n` per turn (open `<|turn>`=105, close/eot `<turn|>`=106, assistant role → `model`) with a native `<|turn>system` turn — NOT Gemma-2/3's `<start_of_turn>`/`<end_of_turn>`, which are not tokens in the Gemma-4 vocab. See memory `gemma4-e4b-base-and-format.md` and the `scripts/train.py` docstring:**
- [ ] **Both sides apply the SAME official Gemma-4 template, neither hand-rolled.** Trainer: `tokenizer.apply_chat_template` (the model's own template) with `add_special_tokens=False` (the template emits `<bos>` itself). Serve: the version-controlled Modelfile inherits Ollama's built-in `RENDERER gemma4` + `PARSER gemma4` with a passthrough `TEMPLATE {{ .Prompt }}` — do NOT hand-write a turn template (a phantom `<start_of_turn>` tokenizes as raw text → the `---`-on-repeat breakage). Gemma 4 HAS a native `<|turn>system` turn, so the system role is its own turn, not folded into the first user turn. [G1]
- [ ] **EOS-pin (Unsloth #5386):** set `tokenizer.eos_token = "<turn|>"` (id 106) before save/GGUF, else the merge resets EOS to `<eos>` (id 1) and the served model never stops. The stop is `<turn|>`, NOT `<end_of_turn>` (a Gemma-2 phantom); at serve time `PARSER gemma4` owns it, so the Modelfile sets NO `stop` param. [G2]
- [ ] **Stop-decode proof:** a one-epoch pilot, decoded ONCE without the GBNF grammar, ends cleanly after the JSON — proves the model learned to stop on `<turn|>`. [G2]
- [ ] **Render-identity gate** (`tests/test_structural_agent.py`): `test_chat_template_render_identity` is the OFFLINE structural half — runs everywhere, can fail; it forbids the Gemma-2 phantom markers and asserts the Modelfile inherits `RENDERER`/`PARSER gemma4` + the passthrough TEMPLATE. `test_chat_template_token_identity_online` is the REAL token-identity check — it renders the anchor messages with the exact base tokenizer and proves the served prompt is a token-level prefix of the trained sequence; it needs `transformers` + the base tokenizer, so run it in the Stage-4 env with `GEMMA4_RENDER_IDENTITY_STRICT=1` (which turns the offline skip into a hard failure). [G1/G2]
- [ ] **Tokenizer / special-token identity** across the HF base used for LoRA, the merge, and the Q4_K_M GGUF — a vocab/added-token mismatch at convert time corrupts every prompt. [uncovered]
- [ ] **Modelfile PARAMETERs don't fight inference**: `temperature 0`, `num_ctx >= max assembled sample length`, no stray `top_p`/`repeat_penalty` defaults; Unsloth `max_seq_len >= longest sample`. [uncovered]
- [ ] **input_view parity** is gated (`tests/test_label.py::test_input_view_parity_train_vs_inference`) — train and serve build the model's sole input identically. [G3, done]

### Stage 6 — Optional preference round (only if SFT plateaus above LOOK but below oracle)

Generate best-of-4 samples from the fine-tuned model per held-out state; score each by simulator rollout; build (chosen, rejected) pairs from the spread; one DPO epoch. This is offline, simulator-verified preference learning — the safe sliver of the RL idea [Report §2 strategy rationale].

---

## 4. Division of labor — three execution lanes

**Writer/auditor protocol.** The strong model (Claude, this repo) authors the spec and the *failing gate tests first*; Gemini 3.5 Flash (Antigravity) writes volume code against them; the audit then reduces to running the gates plus a targeted diff review (RNG discipline, I/O-contract drift, report fidelity) instead of open-ended code reading. Decision rule: **delegate to Flash only where spec + tests fully determine correctness.** Where correctness lives in modeling judgment, the strong model writes — the two real defects so far (zero stop-time engine, AWT survivorship bias) were modeling errors that passed every test and were caught only by reasoning against the report.

| Lane | Workstream | Writer | Verified by | Notes |
|---|---|---|---|---|
| **A — Instrument & engine** | Arena, Tier-3 timing, metrics, destination-dispatch/zoning engine (skyscraper P2–P6), oracle scorer, all gate tests, GGUF/Ollama deploy, final evaluation | **Claude (this repo)** | Gates S1–S5 / G1–G5 | Judgment-bound, not volume-bound; errors here silently poison every downstream label |
| **B — Volume code** | Stage-1 harvest scripts, labeling notebooks, Unsloth/PEFT training script, plotting, GPU-babysitting glue | **Gemini 3.5 Flash (Antigravity)** | Pre-written Lane-A gate tests + Claude diff audit | **Closed until skyscraper P4–P5 freeze the new action space.** Prompt Flash with invariants as *prohibitions*: never consume `config.RNG` outside seeded paths; never alter Tier 0–2 timing defaults; output must match the exact frozen schema |
| **C — Semantic work** | Tier B teacher rationales, judge QC spot-checks | **Gemini 3.5 as teacher/judge (Antigravity)** | Oracle re-simulation of disagreements | Gemini's highest-value role; hand it Report §8 as system context |
| — | LoRA compute (Stage 4) | Cloud GPU (Option A) | Stage-5 arena gates | One-off cost, ~$5–20 for the full run on a rented A100 |

### Strands SDK role

Strands is the **production harness and the format anchor** — load-bearing at three points, deliberately absent everywhere else:

1. **Harvest serialization (Stage 1).** State snapshots must be produced by the same Strands tool functions the agent uses at inference (`tools/sim_tools.py`: `get_all_cars_state`, `get_floor_calls`), so training states are byte-identical to production input. One serializer, two consumers.
2. **The frozen I/O contract (Stage 3).** The training sample format *is* the Strands artifact: `agentic.py` system prompt + `policy/schemas.py` structured-output models. G4 (≥99.5% valid output) is enforced through Strands' structured-output path; the format-fidelity audit round-trips records through those same pydantic models.
3. **Deployment & evaluation (Stage 5 / skyscraper P7).** The fine-tuned model runs inside `DispatcherAgent`, and the skyscraper action space (destination assignment, zone maps) is defined *as* Strands tools + schemas — so the harness and the training contract remain one artifact.

**Where Strands stays out:** oracle labeling and arena baselines. Stage 2 Tier A is ~50k deterministic rollouts where wall-clock and RNG discipline dominate; wrapping them in an agent loop buys nothing and risks both.

## 5. Risks and mitigations

1. **gemma4/e4b not yet supported by Unsloth/MLX/llama.cpp fine-tune path** — *check before Stage 4; fallback chain A→C→B; worst case, fine-tune gemma3:4b instead and accept the swap (architecture verified supported everywhere).*
2. **Uniform-traffic regression (the Yavaş trap)** — *regime-stratified data (≥20% each) + G1 gating per regime.*
3. **Format drift breaking structured output** — *the I/O contract is frozen from production code; G4 gate; parse-failure samples recycled as negative QC examples.*
4. **Teacher quota exhaustion** — *oracle labels carry the bulk; Tier B is enrichment, the plan survives with zero Gemini calls.*
5. **Latency regression** — *≤60-token reasoning enforced in data; G5 gate.*
6. **Overfitting to the simulator's quirks** — *acceptable by design: the model's job IS this simulator. Held-out configs measure within-domain generalization.*

## 6. Effort estimate

| Stage | Wall-clock |
|---|---|
| 0 Arena + lunch profile | 0.5–1 day |
| 1 Harvesting | 0.5 day + overnight runs |
| 2 Oracle labels | 1–2 nights compute |
| 2 Teacher labels | 0.5 day in Antigravity |
| 3 Assembly + QC | 0.5 day |
| 4 Pilot + full LoRA | 1–2 days incl. iteration |
| 5 Deploy + eval | 0.5 day |
| **Total** | **~1 week part-time** |

## 7. Immediate next actions

1. Build `scripts/arena.py` + lunch traffic profile (Stage 0) — can start now in this repo.
2. Verify gemma4 fine-tune support in Unsloth + llama.cpp GGUF export (5-minute check, decides Option A vs C).
3. In Antigravity: set up the teacher-labeling notebook with the report's §8 as system context.
4. Run Stage 1 harvest overnight.
