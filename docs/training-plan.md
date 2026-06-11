# Training Plan: Fine-Tuning Gemma 4 e4b as an Elevator Dispatcher

*Plan of record for making the local `gemma4:e4b` model (8.0B params, ~4B active, Q4_K_M, Ollama) a genuinely strong AI Brain, using Antigravity + Gemini 3.5 as the teacher/judge stack. Grounded throughout in `docs/research/elevator-dispatch-algorithms.md` (cited as [Report §n]).*

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

### Stage 1 — Harvest decision points

Run LOOK-driven and random-policy episodes across the full config grid (regimes × floors × cars × weight limits × seeds) and dump every dispatcher decision point as a JSON state snapshot — exactly the state the `DispatcherAgent` tools expose (`get_all_cars_state`, `get_floor_calls`, now weight-aware). Include episodes where cars run full (refusal-rich states are the differentiating curriculum, G3).

Target: **50k–100k raw decision points**, deduplicated by state hash, stratified so each regime is ≥20% of the corpus — the Crites & Barto failure to avoid is training on one regime only [Report §4.2: "down-peak profile only"].

### Stage 2 — Label generation (two tiers)

**Tier A — Oracle labels (bulk, free, local).** For each harvested state, enumerate candidate target floors per idle car; roll the simulator forward H≈12–20 ticks per candidate (clone sim state, deterministic); score with the report's cost function shape — `cost = mean_wait + λ₁·P95_wait + λ₂·energy + λ₃·refusals` [Report §2.2: cost-function design is the design space]. The argmin is the label. This is brute-force lookahead the report's production systems can't afford in 500 ms but we can offline. Estimated: ~1–2 s per state on the M4 → run overnight, parallelized; budget ~50k labeled states.

**Tier B — Teacher rationales (small, high-quality, Antigravity).** Sample 3–5k diverse states (stratified, refusal-heavy oversampled). In Antigravity, prompt Gemini 3.5 with: the state JSON + the *oracle's answer* + the report's §8 implementation principles, asking for a **≤60-token rationale** that justifies the oracle move (stop-count reduction, batching, weight headroom, starvation guard). The teacher explains; the oracle decides. Discard any sample where Gemini argues for a different floor than the oracle unless re-simulation shows Gemini's move scores better (then keep Gemini's — free label improvement).

> **Quota warning:** the repo's Gemini API key is free-tier — 20 requests/day (verified when preset generation silently fell back to mock). Tier B at 3–5k calls requires your Antigravity/AI-Pro quota or a paid key. Batch 10 states per call to cut request count 10×.

### Stage 3 — Dataset assembly

Each training sample = the **exact production I/O contract**:
- *Input:* the dispatcher system prompt (current `agentic.py` gemma variant, frozen) + serialized state.
- *Output:* `{"reasoning": "<≤60 tokens>", "target_floors": {"C1": n, ...}}` — short reasoning then decision, matching the structured-output path the agent already parses. Short outputs are also the G5 latency lever.

Mix: ~85% oracle-only samples (reasoning omitted or templated one-liner), ~15% teacher-rationale samples. Hold out: 2 full seeds per regime cell, plus one entire config never seen in training (e.g., 9 floors / 3 cars) to measure generalization. QC pass in Antigravity: Gemini 3.5 as judge spot-checks 500 random samples for label/state consistency.

### Stage 4 — LoRA fine-tune (decision fork)

| Option | Where | Feasibility on this project | Recommendation |
|---|---|---|---|
| **A. Cloud GPU QLoRA (Unsloth/PEFT)** | Colab/RunPod A100 or T4 | 8B base in 4-bit QLoRA fits in 16–24 GB VRAM; hours not days; Unsloth's Gemma support is mature — **verify gemma4/e4b support at execution time**; export merged weights → GGUF | **Recommended.** Fastest iteration, cheapest failure |
| B. Local MLX on the M4 | This Mac (16 GB) | mlx-lm LoRA on a 4-bit 8B is *borderline* on 16 GB unified memory — small batch (1–2), gradient accumulation, slow (days for 50k samples); fine for a 5k-sample pilot | Use for the **pilot run only** |
| C. Vertex AI managed tuning | Google Cloud | Clean fit with the Antigravity/Google stack if Gemma 4 tuning is offered there; less control over export path to GGUF | Fallback if A hits gemma4-support gaps |

Hyperparameter starting points: LoRA r=16, α=32, lr 1e-4 cosine, 2–3 epochs, target modules = attention + MLP projections, **text tower only** (freeze the model's vision/audio towers — they're dead weight for this task). Keep a ~5% general-instruction replay mix to limit catastrophic forgetting (the model still has to parse instructions).

**Pilot first:** 5k samples → quick LoRA → Stage 5 eval. If the pilot doesn't move AWT at all, the bug is in data format or prompt mismatch, not scale. Then the full run.

### Stage 5 — Deploy and evaluate

1. Merge LoRA → convert to GGUF (llama.cpp `convert_hf_to_gguf.py`, Q4_K_M to match current footprint) → `ollama create elevator-gemma -f Modelfile`.
2. Point the simulator at it: Settings → Ollama model id `elevator-gemma` (no code changes needed — already configurable, commit `9c471f7` lineage).
3. Run the Stage-0 arena: fine-tuned model vs full baseline ladder, all regimes, held-out seeds. Gate on G1–G5.
4. If gates pass: regenerate presets with the new model (`LLM_PROVIDER=gemma`, see memory note — verify no mock fallback), confirm the preset races still tell an honest story, ship.

### Stage 6 — Optional preference round (only if SFT plateaus above LOOK but below oracle)

Generate best-of-4 samples from the fine-tuned model per held-out state; score each by simulator rollout; build (chosen, rejected) pairs from the spread; one DPO epoch. This is offline, simulator-verified preference learning — the safe sliver of the RL idea [Report §2 strategy rationale].

---

## 4. Division of labor

| Workstream | Tool | Notes |
|---|---|---|
| Arena runner, harvesting, oracle labeling, GGUF/Ollama deploy, final evaluation | **This repo / Claude Code** | All local, simulator-native |
| Teacher rationales, judge QC, training-script authoring, cloud-GPU run babysitting | **Antigravity + Gemini 3.5** | Where your Gemini quota lives; hand it `docs/research/elevator-dispatch-algorithms.md` §8 as the system context for labeling |
| LoRA compute | Cloud GPU (Option A) | One-off cost, ~$5–20 for the full run on a rented A100 |

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
