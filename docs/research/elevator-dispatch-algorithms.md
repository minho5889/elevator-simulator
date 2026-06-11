# Elevator Dispatching Algorithms: From a Single Car to the Supertall Group

*A research report for engineers implementing elevator simulation. Compiled 2026-06-10 from three adversarially-verified research rounds; every load-bearing claim survived a three-vote refutation panel against its primary source unless flagged otherwise. Verification flags used throughout: **[single source]** = rests on one credible source; **[verification incomplete]** = extracted from a credible source but the adversarial check was interrupted (compute limits), content matches standard textbook treatment; **[unverified]** = could not be confirmed to this report's standard and is presented only as context.*

---

## Executive summary

Elevator dispatching is the problem of deciding, continuously and under uncertainty, which car serves which call. This report traces its evolution through four regimes. First, the single car: collective control — the industry's workhorse — serves calls in direction-sorted sweeps rather than arrival order, because greedy nearest-call service provably starves edge floors; the identical insight appears in Denning's 1967 disk-scheduling analysis, whose primary text, notably, never mentions elevators at all [Denning, 1967]. Second, the multi-car group: allocating hall calls to cars is a combinatorial assignment problem containing traveling-salesman subproblems, NP-hard even for a single car when pickup orders are free [Seckinger & Koehler, 1999], solved in production by heuristics, fuzzy logic, and — best documented — KONE's genetic-algorithm lineage, which meets sub-500 ms real-time budgets via memoization [Tyni & Ylinen, 1999/2006]. Third, destination dispatch: passengers enter their destination at a lobby kiosk, letting the controller batch by destination before boarding. Conceived by Leo Port in 1961, made dynamic by Closs (1970), analyzed by dos Santos (1974), and commercialized as Schindler's Miconic 10 in 1990 [Barney, n.d.], it boosts up-peak handling capacity 10–120% depending on group size — but offers no down-peak benefit [Sorsa et al., 2005; Barney, n.d.]. Fourth, learning-based control: Crites & Barto's 1998 multi-agent reinforcement learning beat academic heuristics in simulation, yet no production deployment of RL dispatching has ever been credibly documented; the one industrial lab that evaluated it rejected it as impractical and patented a decision-theoretic alternative [Nikovski & Brand, 2003; US 7,014,015]. The report closes with skyscraper-scale systems, a comparative table, a worked round-trip-time example, and open problems.

---

## 1. Foundations: controlling a single elevator

### 1.1 From the attendant to collective control

The earliest automatic systems replaced a human attendant with **single automatic push button** control: one call at a time, served to completion — functionally first-come-first-served (FCFS). The industry's lasting answer is **collective control**: the car *collects* calls along its direction of travel, answering every registered stop in sweep order, reversing only when no further demand exists ahead. In **full collective**, landing calls are a single button and the car stops for any waiting passenger when passing; in **selective collective** — the modern standard for simplex installations — landings have separate up/down buttons and the car stops while traveling up only for up calls, reserving down calls for its downward sweep [Barney & Al-Sharif, 2015; Elevator World, n.d.].

*Status: established practice; taxonomy per the standard textbook [Barney & Al-Sharif, 2015].*

### 1.2 Why FCFS fails, and what SCAN actually is

FCFS treats call order as service order, so the car shuttles across the building in request sequence, repeatedly crossing floors it will revisit later. Two structural problems follow. Travel is wasted: expected per-request movement scales with building height regardless of locality. And service variance explodes under load, since a burst of geographically scattered calls is served in arrival order rather than route order. Direction-preserving sweeps fix both by converting the service sequence into a route — this is the "elevator algorithm," known in computing as **SCAN** (sweep to the end of the range, reverse), with the practical variant **LOOK** reversing at the last *requested* floor rather than the terminal one, and **C-SCAN/C-LOOK** returning to one end to serve in a single direction for fairness uniformity.

The cross-pollination question — did computing borrow from elevators, or vice versa? — has a verifiable answer on the computing side. The foundational disk-scheduling source is Denning (1967), which introduces the back-and-forth sweep for moving-head disks, shows it dominates both FCFS and greedy shortest-seek-time-first (SSTF), and identifies **starvation** as SSTF's decisive flaw: under heavy load the head dwells where requests are dense, and edge requests "might be overlooked indefinitely." The adversarial verification for this report obtained the full 49-page text (MIT Project MAC Memo-26, identical to the AFIPS publication): it describes SCAN with a *shuttle bus* analogy and **contains zero occurrences of the words "elevator" or "lift."** The "elevator algorithm" name was attached later by others; the primary source claims no derivation from elevator practice [Denning, 1967]. Elevator collective control predates the paper by decades as engineering practice, so the honest statement is: the two fields converged on the same direction-discipline independently, and the *naming* flowed from elevators to computing, not the algorithm itself — at least, no primary source documenting an algorithmic borrowing in either direction survived verification.

The elevator-domain reading of Denning's starvation result transfers directly: a **nearest-car / nearest-call** policy is SSTF in a shaft. It minimizes the next stop's cost while unboundedly deferring unlucky floors — which is precisely why naive "dispatch the closest car" rules, attractive as they are for a first simulation, fail as load grows.

*Status: theoretically established (Denning's results are proofs-plus-measurement on a formal model; the starvation mechanism is load-independent logic). The independence-of-invention conclusion is an absence-of-evidence finding from primary-text verification.*

### 1.3 The single-car up-peak problem

Even one perfectly controlled car faces a structural wall each morning: every passenger boards at the lobby and exits upward (up-peak). The car's round trip — lobby, stops, return — bounds throughput regardless of policy cleverness, which is why up-peak is the *sizing* scenario for buildings (Section 5.3) and why a 5-floor simulation with one car saturates abruptly once arrivals outpace round trips. Under conventional control, up-peak is the limiting traffic case: measured against it, down-peak handling capacity is 50–80% greater and lunch/two-way capacity 20–40% greater [Sorsa et al., 2005; corroborated by Siikonen, 1997]. The asymmetry is mechanical — descending cars fill from multiple floors toward one sink, while ascending cars must all load serially through the single lobby door.

*Status: simulation-validated, originating from one research group (KONE/Siikonen); the qualitative ordering is standard textbook material [Barney & Al-Sharif, 2015].*

---

## 2. Multi-car group control with conventional hall calls

### 2.1 The hall call allocation problem

With a group of L cars and up/down landing buttons, the controller's decision is an **assignment**: map each active hall call to a car (the car's own car-calls are fixed obligations). Formally, the problem is a *bilevel* or hierarchical optimization: the upper level assigns calls to cars; each car's lower level is a routing problem — a traveling-salesman-like sequencing of its assigned stops under direction and capacity constraints. The dispatching problem "contains a set of traveling salesman problems as constraints" [Sorsa et al., 2009 (manuscript); peer-reviewed statement in Ruokokoski et al., 2016; Sorsa, 2019].

The hardness is not folklore: **Seckinger & Koehler (1999)** proved the elevator planning problem NP-hard *even for a single car* when all n! pickup orders of n assigned passengers may be considered. The attribution is verified through two independent peer-reviewed citing sources [Nikovski & Brand, 2003; DOI 10.1007/s10696-013-9175-6]; the original German workshop paper was not directly inspected **[proof text: single-step indirection]**. Practical consequence: production controllers do not solve to optimality; they search (GA, enumeration over restricted orders) under a clock.

That clock is harsh. Dispatching is a *dynamic, stochastic* problem — the instance changes every time a button is pressed — and each instance must be solved in **under 500 ms** to feel instantaneous. KONE's published benchmarks for its GA: ~23 ms per down-peak instance and ~92 ms in mixed traffic on 8 cars / 20 pickup requests, maxima under the half-second budget [Sorsa et al., 2009] **[single source for exact timings; ~2009 hardware]**.

*Status: NP-hardness theoretically established; formulation peer-reviewed; timing figures simulation/benchmark-validated by the algorithm's own developers.*

### 2.2 Cost functions and ETA dispatching

Classical group control scores each tentative assignment with an **estimated time of arrival (ETA)** model: for each call, predict the candidate car's arrival time given its committed route, and choose the assignment minimizing a cost. The design space lies in the cost function: pure **waiting time** (call registration to car arrival) is the industry's headline metric; **journey/time-to-destination** weighting penalizes routes that pick passengers up early only to drag them through many stops; **energy** terms credit assignments that reduce starts and empty travel. The most explicit published treatment of the trade-off is KONE's bi-objective formulation, which optimizes waiting time and energy jointly and can *regulate* service to a target waiting-time level while minimizing energy spend [Tyni & Ylinen, 2006]. This is the genuinely load-bearing idea for simulation work: dispatching quality is not one number, and a dispatcher that wins on average wait may lose on energy or on the wait-time tail.

*Status: peer-reviewed formulation (EJOR); the wait/energy trade-off curve results are simulation-validated by KONE authors.*

### 2.3 Traffic patterns and zoning

Group control is traffic-conditional. The canonical patterns: **up-peak** (morning, lobby→up), **down-peak** (evening, floors→lobby), **lunch peak** (bidirectional with an incoming component), and **interfloor** (background, roughly uniform). Classical controllers detect the regime and switch strategy; the classical up-peak strategy is **zoning/sectoring** — partition upper floors into contiguous zones, dedicate cars per zone, and shrink each round trip's stop count. Zoning is also the conceptual ancestor of destination dispatch's batching (Section 3) and of static sky-lobby partitioning (Section 5).

*Status: established practice [Barney & Al-Sharif, 2015]; the quantified zoning gains used in this report appear in the destination-dispatch context [Sorsa et al., 2005].*

### 2.4 The industrial control lineage: relays → microprocessors → fuzzy → GA

Through the mid-20th century, group logic lived in **relay circuits** — which is precisely why Leo Port's 1961 destination-entry concept (Section 3.2) could only be implemented with *fixed* allocation: dynamic reassignment exceeded relay-era hardware [Barney, n.d.]. Microprocessor group controllers (commercially from the late 1970s onward) made ETA computation and regime detection feasible **[date band: standard history, not independently verified here]**.

Two AI waves followed. **Fuzzy logic** group supervisory control is documented in the peer-reviewed record by 1994 [Ming Ho & Robertson, 1994], with Japanese manufacturers' fuzzy controllers and elevator-group fuzzy patents (e.g., US 5,022,498; US 5,233,138) predating that date — the 1994 paper is a conservative *anchor*, not the origin. A claim that fuzzy logic had previously served only as a supporting component inside expert systems was **refuted** in verification (1–2 vote) and is deliberately absent here. **Genetic algorithms** are the best-documented production-adjacent lineage, thanks to KONE: US Patent 5,907,137 (Tyni & Ylinen; Finnish priority August 15, 1997; granted May 25, 1999) encodes each candidate allocation as a chromosome of (call, car) gene pairs, evaluates fitness per chromosome, and — its characterizing claim — maintains a **"gene bank"** memoization cache so previously evaluated chromosomes skip re-evaluation, an explicit real-time-budget mechanism. The mature academic statement is the bi-objective EJOR formulation above [Tyni & Ylinen, 2006]. In simulation the GA outperformed KONE's conventional ESP dispatcher by ~15% transportation capacity in down-peak with 10–16% better service quality [Sorsa et al., 2009] **[single source; self-evaluation]**; an independent 2024 study likewise found a GA beating directional-continuity heuristics and simulated annealing on average wait, at higher compute cost [Gharbi, 2024] **[single MDPI simulation study]**.

*Status: patent and EJOR formulation primary-source verified; comparative percentages simulation-validated, self-reported.*

---

## 3. Destination dispatch

### 3.1 The idea

Conventional control learns a passenger's destination only after boarding. **Destination dispatch** (hall call allocation) moves that information to the lobby: the passenger keys a destination at a kiosk, the controller assigns a car *before boarding* and directs the passenger to it. Knowing origin–destination pairs upfront lets the controller **batch passengers by destination**, cutting the stops per round trip — the same lever as zoning, but computed per-passenger and dynamically.

### 3.2 History, verified

The lineage is documented in the authoritative account by Gina Barney (editor of CIBSE Guide D): **Leo Port (1961)** proposed landing destination entry, but relay technology confined him to fixed allocation; the system was installed in two Australian buildings and ran in one for roughly 20 years **[single source for the 20-year detail]**. The *dynamic* allocation algorithm was first described by **G. D. Closs (1970)**, analyzed in depth by **Sergio dos Santos (1974, with Barney)**, and first commercially implemented by **Joris Schroeder in 1990 as Schindler Miconic 10** — the first deployment independently corroborated (first installation: Hamburg Electric Company) [Barney, n.d.]. One textual caveat: Barney's abstract says Schroeder "implemented" hall call allocation where the body says "partially implemented."

*Status: historically established via the primary historiographic source, with flagged single-source details.*

### 3.3 What it buys — quantified

The central verified quantitative result comes from KONE's Elevcon 2005 analysis: destination control can raise **up-peak handling capacity by 10–120%** over conventional collective control, with **group size the dominant parameter** — roughly +30% for a two-car group rising to +120% for a ten-car group [Sorsa et al., 2005]. The mechanism is arithmetic, not magic: with L cars and destination batching, the controller can emulate optimal dynamic zoning, and a car serving a narrow destination band makes fewer stops per trip, shrinking round-trip time (the worked example in Section 6 shows a halving). The same source's honesty matters: these are calculated/simulated ideal up-peak maxima, and the authors state a real system "cannot probably" reach the theoretical ceiling **[KONE-authored simulation figures]**.

Equally verified is what destination dispatch does *not* buy: it **improves up-peak only** — "does not assist down peak or interfloor traffic handling" [Barney, n.d.], independently corroborated by Peters Research work noting benefits concentrate in up-peak with some lunchtime gain (lunch traffic has an incoming component), and by KONE's own findings that up-peak-derived capacity must be derated 20–30% for lunch traffic [Sorsa et al., 2005-lineage]. Down-peak batching has nothing to compress: everyone is going to the same place already.

*Status: simulation-validated; concentrated in the KONE/Aalto research group with partial independent corroboration (Peters Research); treat exact percentages as simulation results, not field measurements.*

### 3.4 Commercial systems

The commercial field comprises Schindler Miconic 10 and its successor PORT Technology, Otis Compass/CompassPlus, KONE Polaris, TK Elevator AGILE, and Mitsubishi DOAS. This report verified technical substance only for **KONE Polaris**: its 2014 fact sheet documents a stack of traffic forecasting, fuzzy logic, genetic algorithms, and multi-objective optimization — consistent with the company's entire published research lineage — and a traffic-intensity-adaptive policy: optimize waiting time or energy in light traffic, switch to handling capacity in heavy traffic. Notably, the fact sheet's own comparison chart concedes the field's known weakness, showing "typical destination control" with markedly worse light-traffic waits (~33 s vs ~13 s for Polaris) [KONE, 2014]. KONE's headline claim — Polaris raises up-peak handling capacity 20–100% — is **[manufacturer claim, methodology undisclosed]**, though consistent with and narrower than the published 10–120% research range. Launch years, hybrid-vs-full destination entry, and assignment-policy differences for the competitor systems (Compass, PORT, AGILE, DOAS) **did not survive source verification for this report** and are deliberately omitted rather than approximated.

*Status: explicitly split — peer-reviewed-adjacent for the Polaris technical stack, manufacturer-claim for its performance figure, unverified for competitor specifics.*

### 3.5 Known weaknesses

Three weaknesses carry verified or manufacturer-acknowledged support. **Light-traffic inefficiency**: acknowledged in KONE's own collateral (chart above) and the motivating reason Polaris modulates its objective by traffic intensity [KONE, 2014]. **Immediate assignment rigidity**: destination UX conventionally *locks* the car assignment the moment the passenger is directed ("immediate assignment"), and verified double-deck research shows that relaxing this — allowing reassignment until the last moment ("delayed assignment") — dramatically improves service under mixed lunch traffic, where immediate-assignment destination control "does not function optimally" [Sorsa, 2019] **[single simulation study]**. The UX-vs-optimization tension is structural: the kiosk must tell the passenger something, and what it tells them removes the optimizer's freedom. **Passenger non-compliance** — groups entering one destination for many bodies, passengers boarding the wrong car, reverse journeys — plus perceived-wait psychology and accessibility concerns for visually impaired users are documented in industry literature (Peters Research "Reverse journeys and destination control"; Elevator World "Is Destination Dispatch User-Friendly?"), but those specific sources were fetched and **not verified to this report's standard** before compute limits intervened **[verification incomplete]**; they are flagged as the right starting points rather than cited for specific figures.

---

## 4. Optimization theory and learning-based approaches

### 4.1 Formal models and rolling re-solution

The verified formal skeleton: dispatching is a **bilevel program** — upper-level call-to-car assignment over lower-level per-car TSP routing (Section 2.1) — re-solved on a rolling basis as the stochastic process reveals new calls [Ruokokoski et al., 2016; Sorsa, 2019]. This is the elevator instance of dynamic vehicle routing; model-predictive/rolling-horizon framing follows naturally (re-optimize over the current known state each event), though dedicated MPC-for-elevators papers were not among this report's surviving verified sources **[coverage gap, stated rather than filled]**. Queueing-theoretic up-peak models underlie the analytic capacity formulas in Section 6 [Barney & Al-Sharif, 2015] **[verification incomplete for specific derivations]**.

The **immediate vs delayed assignment** axis deserves an implementer's attention: conventional systems may silently reassign a hall call to a different car until the moment of arrival (delayed); destination systems conventionally cannot (immediate). Sorsa (2019) formulates the double-deck destination problem in both regimes, finds delayed assignment markedly better under mixed traffic, and demonstrates a bilevel GA meeting real-time budgets that outperforms its single-level predecessor on both quality and computation time **[KONE-affiliated self-comparison]**.

### 4.2 Reinforcement learning: the seminal work and the honest assessment

The seminal work is **Crites & Barto, "Elevator Group Control Using Multiple Reinforcement Learning Agents," Machine Learning 33(2–3):235–262, November 1998** (the NeurIPS 1995 paper is its precursor) — bibliography verified field-for-field across four independent records. The architecture: one RL agent per car, the team forming "a new collective learning algorithm... for the team as a whole"; in simulation it "surpass[ed] the best of the heuristic elevator control algorithms of which we are aware" [Crites & Barto, 1998]. Scope verified with equal care: the baselines were *academic reimplementations* (ESA, sectoring, dynamic load balancing), not proprietary commercial dispatchers, and training used a **down-peak profile only**. A frequently repeated detail — that the simulator was Lewis's 4-elevator, 10-floor testbed — did **not** survive verification and is flagged **[unverified]**.

The strongest *industrial* assessment comes from Mitsubishi Electric Research Labs. Nikovski & Brand's decision-theoretic scheduler (ESA-DP: exact expected residual waiting times via dynamic programming over a Markov chain on the car's phase-space) reduced average waits by up to 70% in heavy traffic vs a competitive zoning baseline, ~20% on average across 20,000 trials, 30–40% at saturation — presented at **ICAPS 2003** (a commonly miscited venue: it is not IJCAI or an AAAI conference; AAAI is merely ICAPS's publisher) [Nikovski & Brand, 2003] **[self-reported simulation vs own baseline]**. Critically, both the paper and the granted patent record MERL's evaluation of Crites & Barto's approach: it beat FIM and ESA by only **2.65%** in one down-peak scenario and took **~60,000 hours of simulated operation** to converge — "not practical for real elevator systems" / "completely impractical for commercial systems" [Nikovski & Brand, 2003; US 7,014,015, granted 2006]. Fairness caveats, verified alongside: this is a competitor's adversarial framing; Crites & Barto reported larger gains on squared-wait metrics against weaker baselines; and 60,000 simulated hours was about four days of 1998 compute.

The modern deep-RL lineage is real but remains simulation-bound. Verified entries: **Wei et al. (IEEE TNNLS 31(12):5245–5256, 2020)** — A3C actor-critic group control, reduced average waits vs traditional algorithms in a simulated building, no deployment; **Wan, Lee & Shin (Advanced Engineering Informatics 61:102497, 2024)** — dispatching as a semi-Markov decision process under Dueling Double DQN, a single "all-in-one" model across traffic patterns that beats pattern-specific RL baselines *in the authors' own simulator against round-robin/random heuristics*; and an instructive 2024 M.Sc. thesis [Yavaş, 2024] in which Double DQN beats a nearest-car heuristic in up-peak (42.5 vs 60.9 s average travel time) and roughly ties in down-peak (44.6 vs 46.9) but **loses badly in uniform traffic** (45.6 vs 33.3 — the trivial heuristic wins by 37%), with the thesis itself conceding training cost "was a limiting factor in real-world deployment."

The synthesis, stated as this report's verified honest assessment: **no shipped production elevator group controller using RL has ever been credibly documented.** The chain: the academic success was simulation-only; the industrial lab that examined it rejected it and patented a decision-theoretic alternative; the post-2018 deep-RL wave is simulation-only with mixed results against trivial baselines outside peak regimes; and what manufacturers document shipping is GA/fuzzy/multi-objective optimization (KONE) and exact DP scheduling (Mitsubishi). This is an absence-of-evidence conclusion — strongly supported, unfalsifiable without exhaustive review of all manufacturer literature — and the deeper reasons are structural: a dispatcher must satisfy hard real-time budgets, behave acceptably on day one (no online exploration on live passengers), degrade predictably, and be certifiable to building owners. Engineered optimizers satisfy those constraints by construction; learned policies must prove each one.

*Status: bibliographies and quoted results primary-source verified; all RL performance numbers are self-reported simulation results without independent replication.*

---

## 5. Skyscraper-scale systems

*Coverage note: this section's building-specific specifications (Burj Khalifa, Shanghai Tower, One WTC), TK Elevator TWIN/MULTI operating constraints, and core floor-area economics figures were researched but their claims did not complete verification (rate-limit interruption, not refutation); CTBUH source papers exist and are listed in `sources.md`. What follows confines itself to what is verified, plus clearly-labeled context.*

### 5.1 Verticalizing the network: sky lobbies and zoning

Beyond ~40–50 floors, a single elevator group stops scaling: shaft count grows with population but core area grows with shaft count, cannibalizing the rentable floor plate the elevators exist to serve. The supertall answer is hierarchical: express **shuttles** carry passengers from the ground to **sky lobbies**, where they transfer to **local groups** serving a bounded zone — replacing one impossible group with a tree of feasible ones, at the cost of a transfer and a dispatching problem per node. Real installations in the supertall canon (Burj Khalifa/Otis, Shanghai Tower/Mitsubishi with its documented 20.5 m/s cars, One WTC/ThyssenKrupp) are documented in CTBUH technical papers **[verification incomplete — see coverage note]**.

### 5.2 Double-deck and multi-car shafts

The verified skyscraper-dispatching result in this report concerns **double-deck elevators** — two stacked cabs on one sling, serving adjacent floors simultaneously. Dispatching gains a coupling constraint: every stop positions *both* decks, so the optimizer must coordinate deck assignments such that coincident stops serve real demand on both levels rather than dragging an empty deck along. Sorsa (2019) formulates this as the bilevel double-deck dispatching problem, solves it with a real-time GA, and shows delayed deck/car assignment dramatically improves mixed-traffic service versus immediate assignment [Sorsa, 2019] **[single simulation study, KONE-affiliated]**. TK Elevator's TWIN (two independently driven cars per shaft, with minimum-separation safety constraints and a destination-control requirement) and MULTI (ropeless linear-motor cars moving vertically and horizontally) extend the same theme — more capacity per shaft purchased with harder coupled dispatching — but their specifics are **[verification incomplete]** here.

### 5.3 Design metrics and simulation practice

The industry sizes buildings around **up-peak design criteria**: the elevator group must move a target percentage of building population in five minutes (the **5-minute handling capacity**, with 12% of population per 5 minutes a conventional multi-tenant design demand; 18% single-tenant) at an acceptable **up-peak interval** (round-trip time divided by number of cars) and resulting **average waiting time** (classically approximated as a fraction of interval, ~50–60% in up-peak). These criteria and the probabilistic round-trip-time method beneath them (Section 6) are codified in CIBSE Guide D and the Barney & Al-Sharif handbook [Barney & Al-Sharif, 2015; Smith, 2012] **[verification incomplete for the specific criteria values; formulas match the standard textbook treatment]**. The round-trip-time concept itself traces to Bassett Jones (1923), with the probabilistic highest-reversal-floor refinement attributed to Schroeder (1980) [Smith, 2012] **[verification incomplete]**.

Design practice today is simulation-first: analytic RTT for sizing, then discrete-event simulation for control evaluation — Peters Research's Elevate being the de-facto commercial tool and KONE's Building Traffic Simulator the manufacturer-internal exemplar, with Siikonen's SIMULATION journal work (1993) the citable validation lineage **[verification incomplete; sources fetched and logged]**. For the implementer, the verified takeaway from Section 2 stands in for the whole methodology: evaluate dispatchers *per traffic regime*, never on a single blended average, because capacity ratios between regimes differ by up to 80% [Sorsa et al., 2005].

---

## 6. Worked example: up-peak round-trip time and what destination batching does to it

The standard up-peak RTT model (notation per the textbook treatment [Barney & Al-Sharif, 2015; Smith, 2012] **[formulas verification-incomplete, standard]**): with N floors above the main terminal, P passengers boarding per trip, rated speed v, floor height d, single-floor flight time t_v, stop time penalty t_s per stop, and passenger transfer time t_p,

- Expected stops per round trip: `S = N · (1 − (1 − 1/N)^P)`
- Expected highest reversal floor: `H = N − Σ_{i=1}^{N−1} (i/N)^P`
- Round-trip time: `RTT ≈ 2·H·t_v + (S + 1)·t_s + 2·P·t_p`
- Up-peak interval: `UPPINT = RTT / L` for L cars; 5-minute handling capacity: `HC5 = 300·P / UPPINT` passengers, quoted as `%POP = HC5 / population`.

The intuition: 2H·t_v is the travel envelope (up to the highest reversal and back), (S+1)·t_s charges each door cycle including the lobby, and 2P·t_p charges every passenger's entry and exit.

The verified numerical anchor is KONE's Elevcon 2005 example [Sorsa et al., 2005]: a building with **19 floors above the entrance, 100 persons/floor (population 1,900), 8 cars of 24-person capacity** (loaded at the conventional 80%, P = 19.2). Under conventional collective control the computed **RTT is 202.3 s**, giving interval 202.3/8 = 25.3 s and handling capacity of 8 round trips × (300/202.3) × 19.2 ≈ **227.8 persons per 5 minutes = 12.0% of population** — exactly the conventional design demand, i.e., a correctly-sized conventional building. Switching the same hardware to destination control with optimized dynamic zoning cuts each car's stop set: **RTT falls to 100.8 s**, and capacity rises to **463.2 persons per 5 minutes (24.4%)** in simulation — slightly above the paper's corrected analytic prediction of 432.9, validating the formula chain. Same shafts, same cars: the dispatching layer alone **more than doubles** up-peak throughput. That is the entire economic argument for dispatching research in one table — and, per Section 3.3, it is an up-peak-specific, simulation-validated ideal that real systems approach but do not reach.

---

## 7. Comparative analysis

| Algorithm family | Information used | Up-peak | Down-peak | Interfloor / light | Compute cost | Verified evidence class |
|---|---|---|---|---|---|---|
| FCFS (single car) | Call order | Poor | Poor | Poor; high variance | Trivial | Theoretical (dominated; starvation-free but route-blind) [Denning, 1967 analog] |
| Nearest car / SSTF-like | Distance | Mediocre | Mediocre | Good until load rises, then starves edges | Trivial | Theoretical (starvation proven for SSTF analog) [Denning, 1967] |
| Collective / LOOK | Direction + calls | Baseline | Baseline (HC 1.5–1.8× up-peak) [Sorsa et al., 2005] | Good | Trivial | Established practice; simulation-validated ratios |
| ETA group control | Routes + ETA model | Baseline group standard | Good | Good | Low | Established practice [Barney & Al-Sharif, 2015] |
| Fuzzy group control | Traffic regime + rules | Improved peak handling (vendor era claims) | — | — | Low | Peer-reviewed existence by 1994 [Ming Ho & Robertson]; performance figures unverified |
| GA group control (KONE lineage) | Full assignment search | Strong | +15% capacity vs ESP **[single source]** | Bi-objective wait/energy regulation | ~23–92 ms/instance, <500 ms budget | Simulation-validated, peer-reviewed formulation [Tyni & Ylinen, 2006; Sorsa et al., 2009] |
| Destination dispatch | Origin–destination pre-boarding | **+10–120% HC** (group-size dependent) | ~No benefit | Weak; worse waits in light traffic (vendor-acknowledged) | Moderate | Simulation-validated [Sorsa et al., 2005; Barney, n.d.]; vendor figures flagged |
| Decision-theoretic DP (MERL ESA-DP) | Exact expected waits | Fades with many shafts | Strong | ~20% avg wait reduction; up to 70% heavy traffic **[self-reported]** | Real-time feasible | Peer-reviewed venue, self-evaluated simulation [Nikovski & Brand, 2003] |
| RL (tabular→deep) | Learned value/policy | Wins vs simple heuristics in-sim | Wins narrowly in-sim | **Loses to nearest-car** in uniform traffic [Yavaş, 2024] | Training-heavy; inference ok | Simulation-only, no production deployment documented (verified absence) |

---

## 8. Implementation guide: turning this literature into a faithful simulator

This section translates the verified findings into engineering decisions for anyone building an elevator dispatching simulator — the audience this report was commissioned for. Nothing here introduces new external claims; it operationalizes the cited ones.

**Time base and event model.** The literature's analytic layer (Section 6) is continuous-time and probabilistic; its evaluation layer is discrete-event simulation — Siikonen's KONE simulator and Peters' Elevate are both discrete-event systems [Siikonen, 1993; Peters Research, R3†]. A fixed-tick simulation (1 tick ≈ 1 second) is acceptable for algorithm comparison provided every duration that appears in the RTT formula has an explicit tick cost: per-floor flight time (t_v), a stop penalty covering deceleration, door cycle, and re-acceleration (t_s — typically the *largest* term, which is why stop-count reduction dominates every capacity result in this report), and per-passenger transfer time (t_p). A simulator that lets passengers board in zero time will overstate conventional control and understate destination dispatch, because batching's entire advantage is stop and transfer arithmetic [Sorsa et al., 2005].

**Traffic generation.** The single most consequential verified fact for experimental design is that capacity ratios between regimes differ by up to 80% [Sorsa et al., 2005; Siikonen, 1997]. A dispatcher evaluation must therefore generate and report *per-regime* results: up-peak (all origins at the lobby), down-peak (all destinations to the lobby), lunch (bidirectional with an incoming component — the regime where Sorsa (2019) showed immediate assignment hurts), and uniform interfloor. The Yavaş (2024) result — deep RL winning up-peak by 30% yet losing uniform traffic to a nearest-car heuristic by 37% — is the canonical demonstration of why a single blended average is disqualifying as a headline metric.

**Metrics.** Three passenger-experience metrics recur in the verified literature and are not interchangeable: **average waiting time** (registration to boarding — the industry headline), **average time to destination** (registration to alighting — the metric destination dispatch can trade against waiting time, since batching may hold a passenger at the kiosk slightly longer to deliver them much faster), and **squared waiting time** (the fairness-sensitive objective Crites & Barto optimized, which penalizes the starvation tail that plain averages hide [Crites & Barto, 1998; Nikovski & Brand, 2003]). Report all three plus the wait-time distribution's tail (e.g., P95): Denning's starvation analysis says the *tail*, not the mean, is where greedy policies fail [Denning, 1967]. Add **energy** (per Tyni & Ylinen's bi-objective result, wait and energy genuinely trade off [Tyni & Ylinen, 2006]) and **handling capacity** (passengers delivered per 5 minutes at saturation) for the system-design view.

**The baseline ladder.** The literature implies a canonical ladder of baselines, each exposing a specific failure mode of the one below: (1) FCFS — establishes the route-blindness floor; (2) nearest-car — establishes the starvation failure under load; (3) collective/LOOK — the honest industry baseline any proposed dispatcher must beat (and, per this report's verified findings, a baseline that small learned policies often do *not* beat outside peak regimes); (4) ETA-cost assignment for groups; (5) destination batching / dynamic zoning, evaluated up-peak where its 10–120% verified gains live [Sorsa et al., 2005]. Publishing a comparison against (1)–(2) only — as parts of the deep-RL literature do — is a verified red flag for overclaiming.

**Constraints that change rankings.** Two constraints verified in this report reorder algorithm rankings when added to a simulator. *Capacity/weight limits with boarding refusals*: once a full car must skip hall calls, route-blind policies pay double (they stop, fail to board, and re-serve the call later), while lookahead policies route around full cars — omitting refusals flatters naive dispatchers. *Immediate vs delayed assignment*: if the simulator locks each call's car at registration (destination-dispatch UX), measured service quality under mixed traffic degrades materially versus delayed assignment [Sorsa, 2019]; an experiment comparing conventional and destination control must hold this variable explicitly, or it will conflate interface constraints with algorithmic quality.

**Reproducibility discipline.** Every quantitative claim verified for this report is a *simulation* result, most self-reported by the algorithm's developers (Sections 2.4, 4.2). The minimum credibility bar the field's own history suggests: fixed, published seeds; multiple independent runs per configuration; per-regime reporting; and baselines implemented from their primary descriptions rather than weakened reconstructions — the MERL-vs-Crites & Barto exchange [Nikovski & Brand, 2003] shows how baseline strength alone can swing a published comparison from "+2.65%" to "surpasses the best known heuristics."

---

## 9. Open problems and research frontiers

1. **Field-measured destination-dispatch gains.** The 10–120% up-peak range is simulated and concentrated in one research group. Independently measured performance in occupied buildings — and the size of the gap to theory — remains publicly undocumented.
2. **The RL deployment gap.** The pipeline from simulation wins to certifiable, real-time, day-one-safe learned dispatchers is unbuilt: no published work verified here addresses online safety, regime robustness (the uniform-traffic loss), or certification. The strongest near-term path mirrors MERL's: exact or learned *value estimation* inside an engineered decision rule.
3. **Complexity frontier.** Seckinger & Koehler's single-car n!-order NP-hardness is the verified anchor; the precise complexity of the *hall-call-assignment* variant with realistic constraints (direction discipline, capacity, immediate assignment) deserves a modern, English-language treatment connecting to the bilevel formulation [open per Ruokokoski et al., 2016 lineage].
4. **Delayed assignment under destination UX.** Sorsa (2019) shows delayed assignment is materially better and destination kiosks structurally forbid it. Interface designs that recover optimizer freedom (provisional assignments, re-direction displays) are an open human-systems problem.
5. **Multi-car shafts.** TWIN/MULTI-class hardware turns dispatching into coupled routing with separation constraints — formal models and public benchmarks are thin to nonexistent in the verified literature.
6. **Weight/capacity-aware dispatching.** Boarding refusals couple assignment to load physics (a full car must not be routed to hall calls it cannot serve); the cost-function treatment of refusal risk is implicit in capacity constraints but unexplored as a first-class objective in the verified sources.

---

## References

Primary verification round labels: (R1)/(R2) = claim(s) survived 3-vote adversarial verification; (R3†) = source fetched and claims extracted, verification interrupted — see `sources.md`.

1. Barney, G. (n.d.). *The History of Lift Traffic Control.* Lift & Escalator Library, paper 00000073. https://liftescalatorlibrary.org/paper_indexing/papers/00000073.pdf (R1)
2. Denning, P. J. (1967). Effects of scheduling on file memory operations. *AFIPS Spring Joint Computer Conference*, 9–21. DOI 10.1145/1465482.1465485; full text: MIT Project MAC Memo-26, https://csg.csail.mit.edu/pubs/memos/Memo-26/Memo-26.pdf (R1)
3. Barney, G., & Al-Sharif, L. (2015). *Elevator Traffic Handbook: Theory and Practice* (2nd ed.). Routledge. DOI 10.4324/9781315723600 (R1)
4. Sorsa, J., Hakonen, H., & Siikonen, M.-L. (2005). Elevator selection with destination control system. *Elevcon 2005 / Elevator Technology 15*; CTBUH copy: https://global.ctbuh.org/resources/papers/download/1050-elevator-selection-with-destination-control-system.pdf (R1)
5. Tyni, T., & Ylinen, J. (2006). Evolutionary bi-objective optimisation in the elevator car routing problem. *European Journal of Operational Research*, 169(3), 960–977. DOI 10.1016/j.ejor.2004.08.027 (R1)
6. Tyni, T., & Ylinen, J. (1999). US Patent 5,907,137: Genetic procedure for allocating landing calls in an elevator group. Granted 1999-05-25; FI priority 973346 (1997-08-15). https://patents.google.com/patent/US5907137A (R1)
7. Sorsa, J., Siikonen, M.-L., & Ehtamo, H. (2009, unpublished manuscript). The elevator dispatching problem. Submitted to *Transportation Science*. https://www.academia.edu/28505639/The_Elevator_Dispatching_Problem (R1)
8. Sorsa, J. (2019). Real-time algorithms for the bilevel double-deck elevator dispatching problem. *EURO Journal on Computational Optimization*, 7(1), 79–122. DOI 10.1007/s13675-018-0108-8 (R1)
9. Ruokokoski, M., Sorsa, J., & Siikonen, M.-L. (2016). Assignment formulation for the elevator dispatching problem with destination control and its performance analysis. *European Journal of Operational Research*, 252(2), 397–406. DOI 10.1016/j.ejor.2016.01.019 (R1)
10. Ming Ho, M., & Robertson, B. (1994). Elevator group supervisory control using fuzzy logic. *Canadian Conference on Electrical and Computer Engineering (CCECE-94)*, vol. 2, 825–828. DOI 10.1109/CCECE.1994.405878 (R1)
11. Siikonen, M.-L. (1997). *Planning and Control Models for Elevators in High-Rise Buildings.* Helsinki University of Technology, Systems Analysis Laboratory, Research Report A68. (R1, corroborating)
12. Gharbi, A. (2024). Exploring heuristic and optimization approaches for elevator group control. *Applied Sciences*, 14(3), 995. DOI 10.3390/app14030995 (R1)
13. Crites, R. H., & Barto, A. G. (1998). Elevator group control using multiple reinforcement learning agents. *Machine Learning*, 33(2–3), 235–262. DOI 10.1023/A:1007518724497 (R2)
14. Nikovski, D., & Brand, M. (2003). Decision-theoretic group elevator scheduling. *13th International Conference on Automated Planning and Scheduling (ICAPS 2003)*, Trento. MERL TR2003-61. https://www.merl.com/publications/docs/TR2003-61.pdf (R2)
15. Nikovski, D., & Brand, M. (2006). US Patent 7,014,015 B2: Method and system for scheduling cars in elevator systems considering existing and future passengers. Granted 2006-03-21. https://patents.google.com/patent/US7014015B2/en (R2)
16. Seckinger, B., & Koehler, J. (1999). Online-Synthese von Aufzugssteuerungen als Planungsproblem. *13. Workshop Planen und Konfigurieren*, Würzburg, 127–134. (NP-hardness attribution verified via [14] and DOI 10.1007/s10696-013-9175-6.) (R2)
17. Wei, Q., Wang, L., Liu, Y., & Polycarpou, M. M. (2020). Optimal elevator group control via deep asynchronous actor-critic learning. *IEEE Transactions on Neural Networks and Learning Systems*, 31(12), 5245–5256. DOI 10.1109/TNNLS.2020.2965208 (R2)
18. Wan, J., Lee, J., & Shin, H. (2024). Traffic pattern-aware elevator dispatching via deep reinforcement learning. *Advanced Engineering Informatics*, 61, 102497. DOI 10.1016/j.aei.2024.102497 (R2)
19. Yavaş, A. (2024). *Reinforcement learning based elevator group control* (M.Sc. thesis). Sabanci University. https://research.sabanciuniv.edu/51782/1/10691227.pdf (R2)
20. KONE Corporation (2014). *KONE Polaris Destination Control System* fact sheet SF2959. https://www.kone.us/Images/KONE-Polaris-Destination-Control-System-Fact-Sheet_tcm25-18770.pdf (R2; manufacturer document)
21. Smith, R. S. (2012). Traffic analysis based on the up peak round trip time method: Why it works and how it can be improved. *2nd Symposium on Lift and Escalator Technologies.* Lift & Escalator Library paper 00000036. (R3†)
22. Al-Sharif, L., et al. (2014). A universal formula for the round trip time. *Building Services Engineering Research & Technology* (SAGE). DOI 10.1177/0143624413481685 (R3†)
23. Siikonen, M.-L. (1993). Elevator traffic simulation. *SIMULATION*, 61(4), 257–267. DOI 10.1177/003754979306100409 (R3†)
24. Fortune, J. / Sorsa, J. et al. — double-deck destination control materials: CTBUH paper 1051, https://global.ctbuh.org/resources/papers/download/1051-double-deck-destination-control-system.pdf; Mitsubishi Shanghai Tower equipment: CTBUH paper 942. (R3†, skyscraper context)
25. Peters Research. Reverse journeys and destination control; Up-peak RTT methodology papers. https://peters-research.com (R3†)
26. CIBSE (current ed.). *Guide D: Transportation Systems in Buildings.* Chartered Institution of Building Services Engineers. (Scope reference; criteria values flagged verification-incomplete.)
27. Teorey, T. J., & Pinkerton, T. B. (1972). A comparative analysis of disk scheduling policies. *Communications of the ACM*, 15(3), 177–184. (R1, corroborating SCAN attribution)

*Refuted during verification and excluded: the claim that fuzzy logic had served only as a supporting component within expert systems before 1994 (1–2 adversarial vote); the "Lewis 4-elevator 10-floor simulator" attribution for Crites & Barto (not confirmed against the paper text).*
