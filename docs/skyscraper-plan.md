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

---

## 4. Revised scope and acceptance gates

The mid-rise gates (training-plan.md G1–G5) still apply within each local group, but the skyscraper effort adds system-level gates measured on held-out seeds, **per regime, never blended** [Report §5.3, §8]:

| Gate | Criterion |
|---|---|
| S1 | Tier-3 RTT matches the analytic formula `RTT ≈ 2H·t_v + (S+1)·t_s + 2P·t_p` within ~5% on scripted up-peak trips (validates P1/P2) |
| S2 | Conventional-control HC5 reproduces the §6 anchor (~12% pop for the 19-floor/8-car/24-cap building) — the instrument is calibrated before any policy claim |
| S3 | Destination dispatch shows a real up-peak HC5 gain over conventional **and** no down-peak benefit (matches the verified asymmetry [Report §3.3]; a down-peak "gain" means the model is wrong) |
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

## 6. Immediate next action

**Phase 1, step 1: the Tier-3 time-cost model**, config-gated, validated against the §6 RTT formula (gate S1). Everything else is blocked on it. The one decision that governs how P1 is built — evolve the core timing vs. add a parallel Tier-3 path — is settled in favor of the **config-gated parallel path** above, to protect the preset/visualization contract.
