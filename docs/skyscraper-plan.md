# Skyscraper-Scale Extension Plan

*Plan of record for extending the simulator, arena, and learned-policy target from mid-rise (5–10 floors, 1–6 cars) to supertall group control — sky lobbies, zoning, destination dispatch, express shuttles. Grounded throughout in `docs/research/elevator-dispatch-algorithms.md` (cited `[Report §n]`) and sequenced on top of the Stage-0 arena (`scripts/arena.py`). Supersedes the scope line in `docs/training-plan.md` §1 ("floors 5–10, cars 1–6") — that band is now Phase 0, not the ceiling.*

---

## 1. The reframing: what "skyscraper" changes about the learned target

A fine-tuned **per-call** dispatcher is the right tool for mid-rise collective control and the **wrong** tool for supertall. The report is unambiguous: beyond ~40–50 floors a single group stops scaling, and the industry answer is *structural* — express shuttles to sky lobbies, then bounded local groups [Report §5.1]. Throughput at scale comes from **stop-count reduction** (destination batching / dynamic zoning more than doubles up-peak handling capacity on the same hardware — RTT 202.3 s → 100.8 s in KONE's verified worked example [Report §6]), not from a cleverer choice of next floor.

So the learned target moves up a layer. The model no longer just answers *"which floor next?"*; it operates the structural controls the report says actually move the needle:

- **Destination-dispatch assignment** — given origin→destination calls at a lobby, assign each to a car (or deck) to batch by destination and cut stops [Report §3, §6].
- **Dynamic zoning** — partition floors into car-dedicated sectors and adapt the partition to the regime [Report §2.3, §5.1].
- **Sky-lobby shuttle scheduling** — coordinate express shuttles feeding local groups [Report §5.1].

The distillation strategy from `training-plan.md` survives intact — oracle = expensive offline search over assignments, Gemma clones it [training-plan.md §2]. Only the **action space** and the **environment** grow. This is exactly the lineage the report endorses: learned *value/assignment* inside an engineered decision rule, not end-to-end RL [Report §9.2, §4.2].

---

## 2. The keystone problem: the engine charges zero stop/transfer time

Before any zoning or sky-lobby code, one foundational gap must close, or **every** skyscraper result will be wrong. The current engine (`core/`):

- moves cars at a fixed **1 floor / tick**, with no express or variable speed (no `t_v` term);
- opens doors for a flat 2 ticks regardless of how many people board (no stop penalty `t_s`);
- boards **every** waiting passenger who fits in that 2-tick window **instantly** (no per-passenger transfer time `t_p`).

Report §8 is explicit about why this is disqualifying:

> "A simulator that lets passengers board in zero time will **overstate conventional control and understate destination dispatch**, because batching's entire advantage is stop and transfer arithmetic." … "`t_s` — typically the **largest** term, which is why stop-count reduction dominates every capacity result in this report."

Destination dispatch's entire value is reducing stops and transfers. With `t_s = t_p = 0`, a destination-batched trip and a route-blind trip cost the *same* time — the simulator would show **zero** benefit from the central skyscraper technique, and the learned policy would have nothing to learn. **Phase 1 is therefore the time-cost model, and it gates everything downstream.**

### Compatibility constraint (non-negotiable)

The fixed-tick contract (1 floor/tick, 2-tick doors) is load-bearing for the WebSocket visualization and the recorded preset caches [`docs/decision-log.md` Decision 2; commit history on preset regen]. Changing core timing in place would invalidate every preset and desync the frontend. **The time-cost model ships as a config-gated "Tier 3 / skyscraper" mode**, leaving the Tier 0–2 contract byte-identical. The arena opts into Tier 3; the web stack stays on the legacy contract until/unless we migrate it deliberately.

---

## 3. Phased sequence

Each phase is independently shippable, arena-verified, and ordered so the one below it is a prerequisite. No phase begins before its predecessor passes its gate.

| Phase | Deliverable | Report basis | Verifies via |
|---|---|---|---|
| **P1. Time-cost model** | Tier-3 mode adding `t_v` (per-floor flight), `t_s` (stop penalty), `t_p` (per-passenger transfer). Config-gated; legacy contract untouched. | §8 time base; §6 RTT terms | Arena: reproduce the RTT formula `RTT ≈ 2H·t_v + (S+1)·t_s + 2P·t_p` within tolerance on a scripted up-peak trip |
| **P2. Express speed & travel envelope** | Multi-floor-per-tick / rated-speed travel with accel/decel folded into `t_s`; tall buildings (20–60 floors) become tractable. | §5.3 rated speed; §6 `t_v` | Arena: up-peak interval `UPPINT = RTT/L` matches analytic sizing on a 19-floor/8-car cell |
| **P3. Handling-capacity metrics** | Proper saturation **HC5** (passengers delivered per 5 min), **up-peak interval**, **RTT** instrumentation in the arena — beyond the current `hc5_equiv` proxy. Also fix the zero-delivery AWT wart (AWT must be conditioned on completion so a deliver-nobody policy can't score "best"). | §5.3, §6, §8 metrics | Arena: reproduce KONE's 12.0%-pop conventional baseline on the §6 building |
| **P4. Destination dispatch** | Destination known at call time (kiosk model); car-assignment action space; batching. Hold the **immediate-vs-delayed assignment** variable explicit — locking a call's car at registration degrades mixed traffic [Report §8, Sorsa 2019]. | §3, §6, §8 constraints | Arena: destination batching shows the §6 up-peak HC jump (~12% → ~24% pop) the conventional baseline cannot reach; **no** down-peak benefit [Report §3.3] |
| **P5. Static zoning / sectoring** | Partition floors into car-dedicated zones; dedicated express-to-zone routing. | §2.3, §5.1 | Arena: zoned up-peak beats single-group LOOK at 30+ floors on HC5 |
| **P6. Sky lobbies & shuttles** | Hierarchical model: ground → express shuttle → sky lobby transfer → local group. The transfer node adds a dispatching problem per node. | §5.1 | Arena: a 2-zone sky-lobby tower delivers an up-peak load a flat 50-floor single group cannot |
| **P7. Learned structural policy** | Oracle-label the P4/P5 assignment decisions; distill into Gemma per `training-plan.md` Stages 1–5; gate per regime. | training-plan.md; §9.2 | Acceptance gates (revised §4 below) |
| **P8. (Optional) Double-deck** | Two stacked cabs per sling with the coincident-stop coupling constraint; delayed deck assignment. | §5.2, Sorsa 2019 | Arena: delayed deck assignment beats immediate in mixed traffic |

Phases P1–P3 are pure engine/instrument work (no LLM). P4–P6 build the structural environment. P7 is the fine-tune. P8 is optional richness.

### Execution lanes

Per the amended `training-plan.md` §4: **Lane A** (Claude, this repo) writes every phase in this plan — P1–P6 are instrument and engine work, judgment-bound and gate-verified, where modeling errors pass tests silently (the zero-stop-time keystone is the proof case). **Lane B** (Gemini 3.5 Flash in Antigravity, audited against Lane-A-authored gate tests) opens only after P4–P5 freeze the structural action space; it then owns the volume code — harvest scripts, labeling notebooks, the training script. **Lane C** (Gemini 3.5 as teacher/judge) is unchanged from the training plan. The structural action space itself (destination-call assignment, zone maps) is defined as Strands tools + pydantic schemas in `policy/`, keeping the production harness and the training contract one artifact.

---

## 4. Revised scope and acceptance gates

The mid-rise gates (training-plan.md G1–G5) still apply within each local group, but the skyscraper effort adds system-level gates measured on held-out seeds, **per regime, never blended** [Report §5.3, §8]:

| Gate | Criterion |
|---|---|
| S1 | Tier-3 RTT matches the analytic formula `RTT ≈ 2H·t_v + (S+1)·t_s + 2P·t_p` within ~5% on scripted up-peak trips (validates P1/P2) |
| S2 | Conventional-control HC5 reproduces the §6 anchor (~12% pop for the 19-floor/8-car/24-cap building) — the instrument is calibrated before any policy claim |
| S3 | Destination dispatch shows a real up-peak HC5 gain over conventional, **and the destination-information channel is inert down-peak** — measured against the `shuttle` ablation (identical holding/turnstile/routing, FIFO batches, no destination info), dd must equal shuttle run-for-run down-peak while beating it ≥1.6× up-peak. *Amended from "no down-peak benefit vs conventional": the naive comparison conflates collection-routing quality with information value — measured, dd's down-peak edge over naive LOOK was 100% routing (shuttle ≡ dd, both 1.78× look_park) and 0% information. The ablation isolates the §3.3 claim exactly.* |
| S4 | Learned structural policy ≥ best engineered baseline (ETA group / destination batching) on HC5 up-peak **and** P95 wait in every regime — no starvation regression at scale |
| S5 | Immediate-vs-delayed assignment is logged and held explicit in every destination-dispatch comparison, so interface constraints are never conflated with algorithm quality [Report §8] |

---

## 5. Risks

1. **Stop-time model wrong → all downstream results invalid.** Mitigation: P1 is validated against the closed-form RTT (S1) before anything is built on it.
2. **Tier-3 timing leaks into presets/visualization.** Mitigation: strict config gate; Tier 0–2 contract has byte-identical behavior; a regression test asserts legacy traffic is unchanged.
3. **Scope explosion.** Sky lobbies (P6) and double-deck (P8) are deep. Mitigation: P1–P5 deliver a usable supertall arena on their own; P6/P8 are gated behind demonstrated value at P5.
4. **The technique still may not beat engineered control.** The report's honest verdict is that no learned dispatcher has shipped [Report §4.2]. Mitigation: the win condition is beating the engineered baselines *in this simulator* (S4), and the baselines are implemented from primary descriptions, not weakened [Report §8 reproducibility discipline].
5. **Verification gaps in the source canon.** Much of §5 is `[verification incomplete]` (rate-limit interruption). Mitigation: lean on the *verified* §6 RTT chain and §3.3 asymmetry as the calibration anchors; treat building-specific specs as context only.

---

## 6. Status and immediate next action

- **P1 ✅** — Tier-3 time-cost model (`stop_ticks`/`transfer_ticks` on `Simulation`, config-gated, legacy byte-identical). Gate S1 closed-form tests in `tests/test_timing.py`.
- **P2 ✅** — express/rated speed verified: multi-floor-per-tick travel clamps exactly (`ceil(d/v)` ticks per leg), doors never open mid-flight, energy is speed-invariant, and the full RTT decomposition (travel + 7·t_s stops + 12·t_p transfers) holds at v=3 on the 19-floor reference cell. Accel/decel folded into `stop_ticks` by design (documented on `Car.speed`).
- **P3 ✅ (gate S2 passed)** — true HC5 (per 300 ticks, 1 tick ≈ 1 s), measured per-car RTT and UPPINT, %POP via `--population`, the §6 analytic formula chain (`expected_stops`/`highest_reversal`/`analytic_rtt`/`hc5_from_interval` in `scripts/arena.py`), and survivorship discipline (zero-delivery wait metrics report None; best-in-column stars require completion ≥ 90% of the regime's best — `star_eligible`). **S2 calibration:** the formula code reproduces the published chain exactly (202.3 s → 12.0% pop), and the simulated reference cell (19 floors above terminal, 8 cars, cap 24, `look_park`, t_v=1/t_s=9/t_p=1) measures **11.9% vs the published 12.0%**. Finding en route: naive LOOK strands ~half the bank upstairs in up-peak (~8% pop); conventional staging required a new ladder rung — `MainTerminalParkingLook` (`look_park`) — added in `policy/baselines.py` without touching the frozen production LOOK.
- **P4 ✅ (gates S3 + S5 passed)** — destination dispatch: `Passenger.assigned_car_id` + kiosk-turnstile boarding in the engine (legacy walk-in behaviour byte-identical), super-saturation traffic (`arrival_rate > 1`, legacy RNG path untouched), and `policy/destination.py` (`dd_delayed` / `dd_immediate` / `shuttle` ablation) with departure control (batch threshold + patience). **Measured on the §6 cell at 600/5min demand:** conventional 11.8% pop → dd_delayed **26.0%** (2.20×, vs published 2.03×); causal decomposition via shuttle: information channel **2.02×** up-peak, **exactly 1.000×** down-peak (dd ≡ shuttle run-for-run). S5: delayed beats immediate in mixed traffic (completion 0.61 vs 0.47), assignment mode logged on every run. Two defects found and fixed en route: premature near-empty departures (fixed by departure control) and a bank-wide lobby deadlock from walk-ins stealing batch seats (fixed by the turnstile + full-cars-never-target-pickups guard).
- **P5 ✅ (gate passed)** — static zoning (`policy/zoning.py`, arena rung `zoned`): one contiguous zone per car, zone signage via the assigned-boarding machinery, destination-zone rule for lobby boardings / source-zone for sector collection; departure control, turnstile, routing and parking inherited from the DD family. **Measured at 32 floors:** zoned 13.3% pop vs look_park 6.1% (2.18×) and plain look 4.2% (3.20×), P95 tail halved. Dynamic re-zoning deliberately omitted — the zone map is the learned policy's action surface (P7). Two strategic findings: at 30+ floors **dd ≈ zoned** (1.02× — both travel-envelope-limited; dynamic windows degenerate to sectors when the queue is deep), and in mixed lunch traffic **zoned beats dd** (11.2% vs 9.3% — lobby-anchored batching mishandles bidirectional flow). The structural policy choice is therefore regime- and height-dependent — exactly the decision surface P7 trains Gemma on.
- **★ action-space freeze ✅ (2026-06-12)** — the frozen structural I/O contract is set, the offline oracle is built and gated, and Lane B is open. Authored via a 4-design adversarial panel (17 agents) synthesized against a freshly-measured winner grid; details below.
- **Stage-2 oracle calibration ✅ (2026-06-12)** — locked `(weights, horizon=300, settle=300)`; oracle policy beats/matches every fixed mode per regime, validated on held-out seeds + a held-out 48fl height (`scripts/calibrate.py`).
- **P6 sky lobbies ✅ (2026-06-13)** — two-zone hierarchical tower (`policy/skylobby.py`): express shuttles 0↔sky-lobby + a local high group, with engine-level passenger transfer (`Passenger.final_target` + the transfer branch in `Simulation._step_car`, byte-identical for single-leg) and `Car.service_range` boarding discipline. **Key finding:** the sky-lobby benefit is **architectural, not throughput** — at equal *cars* a flat bank wins (the transfer is pure dispatching overhead), but at equal **core area** (shaft-floors) the half-length sky-lobby shafts field ~2× the cars and win by 26–35%, a margin that grows with height (60→100fl). That reproduces §5.1's actual economic argument; the gate measures per core area, not per car. Low-rise service, down-traffic, and folding sky-lobby operation into the learned action space are deferred.
- **Next: Lane B execution (WO-001) ∥ P8 (optional double-deck) ∥ the pre-GPU G5 latency gate (needs local gemma4:e4b).**

---

## 7. The frozen structural action space (P7 contract)

**Output schema** — `StructuralPlan` in `policy/schemas.py`, two grammar-constrainable `Literal` enums, ~10 output tokens, no nesting, no reasoning field (teacher-only):

```
mode ∈ {conventional, dd_delayed, zoned}      # the structural strategy this epoch
hold ∈ {depart_now, balanced, fill_batch}     # departure-control preset
```

**Input** — the compact `get_traffic_summary` (regime/load sufficient statistics — `frac_origin_lobby` etc. — that cleanly separate the four regimes). **Amended by the G5 gate (2026-06-13):** the structural *mode* decision reads ONLY the traffic summary (~200 chars), NOT `get_floor_calls` — the full per-passenger call dump is ~17 KB at scale and overflows `gemma4:e4b`'s context, truncating generation. Per-passenger calls and per-car state feed the *within-mode* routing (deterministic), never the model. `get_all_cars_state` / `get_floor_calls` remain frozen tools for that routing layer; they are not in the learned policy's prompt. **Cadence** — per-epoch (≥ 1 measured RTT), never per-tick; within-epoch routing is the deterministic collective/batching/sectoring machinery, zero model calls. **Execution** — `policy/structural.py`: `plan_to_dispatcher`, `reset_assignment_state` (clean mode handover — clears the turnstile so a switch never strands committed passengers), and `StructuralDispatcher` (the production surface). **Offline oracle** — `scripts/oracle.py`: enumerate all 9 plans, roll each H ticks, argmin a survivorship-proof cost, explicit tie-break.

### Why these exact fields (the empirical winner grid, HC5, 5 seeds, heights 20/32/48)

| regime | winner (all heights) |
|---|---|
| up-peak | `dd_delayed` (≈2× conventional) |
| down-peak | `dd_delayed` |
| lunch | `zoned` |
| uniform interfloor | `conventional` (the Yavaş trap — the trivial policy wins) |

Each of the three modes wins a regime cleanly, so none is dead weight. `hold` is near-inert under saturation but a real lever at moderate load (`fill_batch` roughly halves the P95 wait tail at no throughput cost) — the oracle tie-breaks it to `balanced` when inert.

**Cut after measuring the live engine** (do not re-add without new evidence): `dd_immediate` (dominated by `dd_delayed` at every cell — kept only as an arena ablation rung for the S5 discipline), weighted zone-split templates, and the `dd_lobby_cars` split-bank hybrid. The last two were the panel's recommended expressiveness extensions, but they require unbuilt engine surface and are unmeasured, and `zoned` already wins lunch — so they are **deferred** to a post-P7 optimization gated on the learned 3-mode policy plateauing below a measured hybrid oracle.

### The two project-saving catches from the panel (would have silently poisoned every label)

1. **CRN / frozen-future oracle bug.** The brief (and all four designs) assumed "deterministic given seed, just clone and roll." False: arrivals are drawn from a module-global `config.RNG` that `deepcopy` does not clone, so rolling candidate A then B from one cloned state gives each a *different* arrival stream — the cost gap would be arrival noise, mislabeling exactly the near-ties. **Confirmed empirically** (two clones of one state, same dispatcher, diverged) and **fixed** with Common Random Numbers (snapshot/restore `config.RNG` around every candidate). The arena was unaffected (it reseeds per run) — this was a latent bug in oracle infrastructure that did not yet exist.
2. **Objective ≠ HC5, and the lunch myopia — now CLOSED.** "Does a label match the single-mode HC5 grid winner" is the wrong calibration target — the deployed policy switches modes per epoch and is never committed to one mode for a whole episode. The correct target is **oracle-policy-vs-baselines full-episode** (`scripts/calibrate.py`). At freeze time the adaptive oracle policy beat/matched the best fixed mode in up-peak/down-peak/uniform but was **~12% short in lunch** — a myopia where a bounded window rewards fast-start `conventional` over slow-starting steady-state `zoned`. **Resolved in the Stage-2 calibration:** a `settle_ticks=300` period (let each candidate establish its mode before scoring) plus throughput-balanced weights closes it — the oracle policy now beats/matches every fixed mode in every regime (lunch 0.88 → 1.02), validated on held-out seeds AND a held-out 48-floor height. The locked `(weights, horizon=300, settle=300)` are the `oracle.py` defaults [docs/training-plan.md Stage 2].

### G5 latency gate — MEASURED + PASSED (2026-06-13)

Measured on real `gemma4:e4b` (Q4_K_M, Ollama): a single pre-rendered `StructuralPlan` decision is **median 1.65s, p95 1.68s, max 1.68s, 100% schema-valid** — under the 2s budget with margin. Bonus: the **zero-shot base model already picks the oracle/grid winner in 3 of 4 regimes** (up-peak, down-peak, uniform; misses only lunch), so the contract carries clean signal and fine-tuning starts from a strong prior.

Three findings the gate surfaced (all now load-bearing for P7 deployment):
1. **Input = `get_traffic_summary` only.** The full `get_floor_calls` serialization is ~17 KB and overflows context → truncated output (`'{'`). The compact summary (~200 chars) decides the mode; see the input amendment above.
2. **`think=False` is mandatory.** Thinking ON is ~16.9s (12×); off is ~1.65s — reasoning tokens dominate latency, exactly as the no-reasoning-field design anticipated.
3. **Do not use Strands `agent.structured_output` for the structural policy.** It truncated to `'{"'` on the real model; a direct `ollama.chat(model, messages, format=StructuralPlan.model_json_schema(), options, think=False)` single call is what works and is the freeze's prescribed "single pre-rendered call" (no two-turn tool-observe loop). P7's `DispatcherAgent` structural variant must use the direct path.
