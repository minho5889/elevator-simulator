# WO-001: Stage-1 decision-point descriptor harvester
Branch: laneb/wo-001
Status: HANDBACK


## Goal
Implement the Stage-1 harvester (`scripts/harvest.py`) that emits the stratified
set of **decision-point descriptors** the oracle (Stage 2) will label. A
descriptor is a compact, deterministic recipe for one epoch-boundary state —
NOT a serialized simulation. See `docs/training-plan.md` Stage 1 and
`docs/skyscraper-plan.md` §7 for the why; you do not need to read the engine.

A descriptor is exactly the keyword arguments of `oracle.harvest_state(...)`:
`{regime, seed, floors, cars, capacity, arrival_rate, stop_ticks, transfer_ticks,
warmup, harvest_tick}`. Stage 2 reconstructs each state by calling
`harvest_state(**descriptor)`, so the descriptor set IS the dataset specification.

## Files you may create/modify
- `scripts/harvest.py`   (new)
- (nothing else — `tests/`, engine, policy, schemas, oracle are all off-limits)

## What `scripts/harvest.py` must do
1. Provide `generate_descriptors(target: int, seed_base: int) -> list[dict]` that
   returns ~`target` descriptors sampled over the grid:
   - `regime` ∈ {up_peak, down_peak, lunch, uniform}, each ≥ 20% of the set.
   - `floors` drawn from height bands {20–28, 30–40, 44–60}, every band present.
   - `cars` ∈ [4, 12]; `capacity` ∈ {16, 20, 24}.
   - `arrival_rate` ∈ {0.4, 0.8, 1.2, 2.0} (cover moderate → super-saturated).
   - `warmup` ∈ {conventional, dd_delayed, zoned, switching} — each mode present
     for every regime (the mandatory warmup-mode sweep; "switching" alternates
     modes every ~150 ticks — implement as a sentinel string the value passes
     through, Stage 2 interprets it; do NOT build a dispatcher here).
   - `stop_ticks=9`, `transfer_ticks=1` fixed (the calibrated Tier-3 costs).
   - `harvest_tick` ∈ [80, 400], an epoch boundary (multiple of 20).
   - Oversample tight cells: ≥ 15% of descriptors carry a `weight_limit` in
     {120, 150, 200} (refusal curriculum); the rest omit it / set null.
   - Deterministic given `seed_base`: use a single `random.Random(seed_base)` —
     do NOT touch `elevatorsim.config.RNG`, and do NOT call the global `random`.
2. Write JSONL to a `--out` path, one descriptor per line,
   `json.dumps(d, sort_keys=True)`.
3. CLI: `--target` (default 50000), `--seed-base` (default 20000), `--out`
   (default `data/stage1_descriptors.jsonl`). Create parent dirs.
4. Print a one-line stratification report (per-regime %, per-band counts, refusal %).

## Hard prohibitions (from docs/antigravity-brief.md — violating fails audit)
- Do NOT import or construct any dispatcher, Simulation, or oracle here — this
  script only emits descriptors. (Stage 2 reconstructs/labels.)
- Do NOT consume `elevatorsim.config.RNG` or the global `random` module; use your
  own `random.Random(seed_base)` instance so harvesting cannot perturb sim RNG.
- Do NOT edit `tests/`, engine, policy, schemas, or `scripts/oracle.py`.
- `json.dumps(..., sort_keys=True)` everywhere.

## Gate tests (Lane A will commit these failing before you start)
- `tests/test_harvest.py`:
  - `generate_descriptors(2000, 7)` returns ~2000 dicts, each a superset of the
    required keys, every value in range.
  - Stratification: each regime ≥ 20%; all three height bands present; refusal
    cells ≥ 15%; all four warmup values present per regime.
  - Determinism: two calls with the same `(target, seed_base)` are identical;
    different `seed_base` differs.
  - Round-trip: a sample of descriptors can be passed to
    `oracle.harvest_state(**{k:v for k,v in d.items() if k in HARVEST_KEYS})`
    without error (proves the descriptor shape matches the reconstructor).
  - No global-RNG perturbation: `config.RNG.getstate()` is unchanged across a
    `generate_descriptors` call.

## Runtime commands
- `uv run pytest tests/test_harvest.py -q`
- `uv run pytest -q`   (full suite stays green; Gemini 503 smoke excepted)
- `uv run python scripts/harvest.py --target 2000 --out /tmp/d.jsonl`

## Writer handback
- **Implementation**: Created `scripts/harvest.py` implementing `generate_descriptors(target: int, seed_base: int)` and a CLI tool interface.
- **Stratification**: 
  - Regimes are round-robined to guarantee exactly 25% distribution each.
  - Warmups are cycled to ensure every warmup mode is present within every regime.
  - Heights are systematically distributed across low (20-28), mid (30-40), and high (44-60) floor bands.
  - Exactly 18% of generated descriptors carry `weight_limit` values in `{120, 150, 200}` for the refusal curriculum.
- **RNG Safety**: Used a local `random.Random(seed_base)` instance, avoiding any calls to global `random` or `config.RNG` to guarantee zero perturbation.
- **Verification**: All 5 gate tests in `tests/test_harvest.py` and the full `pytest` suite of 86 tests passed cleanly. Tested CLI with `uv run python scripts/harvest.py --target 2000 --out /tmp/d.jsonl` and verified the stratification report output.

## Audit findings
<filled by Claude>

