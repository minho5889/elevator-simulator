# Sources Log — Elevator Dispatching Algorithms Research

Every source consulted during the research for `elevator-dispatch-algorithms.md`, with a one-line credibility assessment. Research was performed in two adversarially-verified rounds (2026-06-10); claims required surviving a 3-vote refutation panel.

## Round 1 — Foundations, group control, destination dispatch, formulations

| Source | Type | Credibility assessment |
|---|---|---|
| Barney, G., "The History of Lift Traffic Control", Lift & Escalator Library paper 00000073 (liftescalatorlibrary.org/paper_indexing/papers/00000073.pdf) | Technical paper | **Primary/authoritative** — by the CIBSE Guide D editor who personally supervised dos Santos's 1974 work; the definitive lineage account for destination dispatch history |
| Denning, P.J., "Effects of Scheduling on File Memory Operations", AFIPS SJCC 1967 (doi 10.1145/1465482.1465485; full text: MIT Project MAC Memo-26) | Peer-reviewed conference paper | **Primary** — the foundational SCAN source; full 49-page text obtained and verified; contains zero mentions of "elevator" or "lift" |
| Barney, G. & Al-Sharif, L., "Elevator Traffic Handbook: Theory and Practice", 2nd ed., Routledge 2015 (DOI 10.4324/9781315723600) | Textbook | **Primary/cornerstone** — bibliographic metadata verified via CrossRef; the standard reference for RTT design method and control taxonomy |
| Sorsa, Hakonen & Siikonen, "Elevator Selection with Destination Control System", Elevcon Peking 2005 (CTBUH-hosted PDF) | Elevcon proceedings | **Primary** — full PDF text-extracted; source of the 10–120% DCS up-peak gains and the worked 8-car RTT example; KONE-authored simulation figures |
| Tyni & Ylinen, "Evolutionary bi-objective optimisation in the elevator car routing problem", EJOR 169(3):960–977, 2006 (DOI 10.1016/j.ejor.2004.08.027) | Peer-reviewed journal | **Primary** — verified via CrossRef + Semantic Scholar; the mature KONE GA formulation (wait time + energy) |
| US Patent 5,907,137 (Tyni & Ylinen, Kone Corp., granted 1999-05-25, FI priority 973346 of 1997-08-15) | Patent | **Primary** — full text verified against USPTO and two mirrors; gene-bank memoization for real-time GA dispatch |
| Sorsa, Siikonen & Ehtamo, "The Elevator Dispatching Problem" (KONE/Helsinki Univ. of Technology manuscript, submitted to Transportation Science 2009) | Unpublished manuscript | **Primary but unpublished** — source of bilevel formulation narrative, sub-500 ms budgets, GA-vs-ESP +15%; self-evaluated by the GA's developers; treat quantitative claims as [single source] |
| Sorsa, J., "Real-time algorithms for the bilevel double-deck elevator dispatching problem", EURO J. Computational Optimization 7(1):79–122, 2019 (DOI 10.1007/s13675-018-0108-8) | Peer-reviewed journal | **Primary** — abstract verified against Springer record; bilevel GA + delayed assignment results |
| Ruokokoski, Sorsa & Siikonen, EJOR 252(2):397–406, 2016 (DOI 10.1016/j.ejor.2016.01.019) | Peer-reviewed journal | **Primary** — corroborates bilevel formulation and immediate/delayed assignment framework |
| Ming Ho & Robertson, "Elevator group supervisory control using fuzzy logic", CCECE-94 (DOI 10.1109/CCECE.1994.405878) | Peer-reviewed conference | **Primary** — bibliographic record confirmed via Crossref + Semantic Scholar; conservative anchor date for fuzzy EGCS; author affiliation unverifiable |
| Gharbi, A., Applied Sciences 14(3):995, 2024 (mdpi.com/2076-3417/14/3/995) | Peer-reviewed journal (MDPI) | **Acceptable, mid-tier** — single-author simulation study; GA vs SA vs heuristics; used as corroboration only |
| Siikonen, M-L., Helsinki University of Technology research report A68, 1997 | Academic research report | **Primary** — corroborates traffic-pattern capacity ratios (down-peak 1.4–1.9× up-peak) |
| Gerstenmeyer & Peters (Peters Research) destination control papers | Industry research | **Primary** — independent (non-KONE) corroboration that DD benefits concentrate in up-peak |
| Teorey & Pinkerton, CACM 1972 (disk scheduling survey) | Peer-reviewed journal | **Primary** — corroborates SCAN attribution to Denning 1967 |
| elevatorworld.com, "The History of Operatorless Elevators / Traffic Control Systems, Part Two" | Trade journal | **Acceptable** — Elevator World technical article (allowed source class); used for collective-control history corroboration |
| KONE Polaris Destination Control System fact sheet (kone.us PDF) | Manufacturer document | **Acceptable with care** — manufacturer technical fact sheet; used for system capabilities, not performance claims |
| sweets.construction.com Schindler PDF (Miconic/destination technical document) | Manufacturer document | **Acceptable with care** — technical content used for system description only |
| dunbarandboardman.blogspot.com on Joris Schroeder | Blog | **REJECTED for citation** — prohibited source class; used only as a pointer; no claim in the report rests on it |
| Crites & Barto, "Improving Elevator Performance Using Reinforcement Learning", NeurIPS 1995 proceedings | Peer-reviewed conference | **Primary** — fetched in round 1; claims verified in round 2 |
| Crites & Barto, "Elevator Group Control Using Multiple Reinforcement Learning Agents", Machine Learning 33:235–262, 1998 (Springer, DOI 10.1023/A:1007518724497) | Peer-reviewed journal | **Primary** — the seminal RL-for-elevators journal version |
| Nikovski & Brand (MERL), "Decision-Theoretic Group Elevator Scheduling" | Peer-reviewed conference (ICAPS 2003) | **Primary** — strongest industrial ML-adjacent dispatching work (Mitsubishi Electric Research Labs) |
| ieeexplore.ieee.org/document/8998335 (deep-RL elevator group control) | Peer-reviewed (IEEE) | **Primary** — post-2018 deep RL lineage |
| arxiv.org/abs/2507.00011 (RL elevator study) | Preprint | **Acceptable as preprint** — used for lineage, flagged as not peer-reviewed |
| peters-research.com, "Traffic Analysis Based on the Up-Peak Round Trip Time Method" | Industry research paper | **Primary** — Peters Research is the author of Elevate; authoritative on RTT methodology |
| CIBSE Guide D product page (cibse.org) | Standards body | **Primary** — bibliographic/scope reference for Guide D |
| sciencedirect.com/science/article/abs/pii/S2352710218307125 (J. Building Engineering) | Peer-reviewed journal | **Primary** — skyscraper vertical transportation analysis |
| sciencedirect.com/science/article/abs/pii/S219244062100112X | Peer-reviewed journal | **Primary** — supertall building elevator metrics |

## Round 2 — RL lineage, complexity, manufacturer reality check

| Source | Type | Credibility assessment |
|---|---|---|
| Crites & Barto, Machine Learning 33(2–3):235–262, 1998 (DOI 10.1023/A:1007518724497; Springer + UMass ScholarWorks + DBLP + ACM DL) | Peer-reviewed journal | **Primary/seminal** — bibliography verified field-for-field across four independent records |
| Wei, Wang, Liu & Polycarpou, IEEE TNNLS 31(12):5245–5256, 2020 (DOI 10.1109/TNNLS.2020.2965208) | Peer-reviewed journal | **Primary** — A3C deep-RL elevator group control; simulation-only, verified via PubMed + IEEE Xplore |
| Wan, Lee & Shin, Advanced Engineering Informatics 61:102497, 2024 (DOI 10.1016/j.aei.2024.102497; KAIST author copy) | Peer-reviewed journal | **Primary** — D3QN SMDP dispatching; abstract verified verbatim; own simulator, no deployment |
| Yavaş, M.Sc. thesis, Sabanci University, 2024 (research.sabanciuniv.edu/51782) | M.Sc. thesis | **Acceptable** — full PDF verified (Table 5.3 figures exact); single data point, supervised thesis |
| Nikovski & Brand, "Decision-Theoretic Group Elevator Scheduling", MERL TR2003-61, ICAPS 2003 (merl.com/publications/docs/TR2003-61.pdf) | Industrial lab paper, peer-reviewed venue | **Primary** — full PDF verified; the venue is ICAPS 2003 (not IJCAI/AAAI as sometimes cited); self-reported simulation results |
| US Patent 7,014,015 B2 (Nikovski & Brand, Mitsubishi Electric Research Labs, granted 2006-03-21) | Patent | **Primary** — Google Patents record verified; decision-theoretic (non-RL) dispatching IP |
| Seckinger & Koehler 1999, "Online-Synthese von Aufzugssteuerungen als Planungsproblem", 13. Workshop Planen und Konfigurieren, Würzburg, pp. 127–134 | Workshop paper (German) | **Primary for NP-hardness, indirectly verified** — proof attribution confirmed via two independent citing peer-reviewed sources (MERL TR2003-61; DOI 10.1007/s10696-013-9175-6); original German text not directly inspected |
| KONE Polaris Destination Control fact sheet SF2959 (©2014) | Manufacturer document | **Acceptable with care** — feature list (GA/fuzzy/multi-objective) verified verbatim; the 20–100% capacity figure is manufacturer-claimed, no methodology disclosed |
| Ruokokoski, Sorsa, Siikonen EJOR 2016 (Aalto public PDF) | Peer-reviewed journal | **Primary** — corroborates formulation/complexity discussion |
| DOI 10.1007/s10696-013-9175-6 (Flexible Services and Manufacturing J.) | Peer-reviewed journal | **Primary** — independent corroboration of Seckinger & Koehler NP-hardness attribution |
| DOI 10.1007/s10878-013-9620-1 (J. Combinatorial Optimization) | Peer-reviewed journal | **Primary** — elevator scheduling complexity context |
| dblp.org Crites bibliography | Bibliographic database | **Secondary** — used for citation verification only |

## Round 3 — CIBSE metrics, skyscraper systems, commercial DD systems and weaknesses

**Verification status: INTERRUPTED.** All 25 extracted claims show 0–0 adversarial votes because every verifier agent hit an API session limit mid-run — the claims were *not refuted on the merits*. Sources below were fetched and claims extracted; report citations from this round are flagged **[verification incomplete]** and confined to textbook-standard content.

| Source | Type | Credibility assessment |
|---|---|---|
| Smith, R.S. (ThyssenKrupp), "Traffic Analysis based on the Up Peak Round Trip Time method", 2nd Symposium on Lift and Escalator Technologies, 2012 (Lift & Escalator Library paper 00000036) | Symposium paper | **Primary** — note attribution correction caught during extraction: this paper is by Rory Smith, NOT Al-Sharif & Peters as a search-result title suggested; it cites Barney (2003) and Strakosch (1998) for the RTT formulas |
| "A universal formula for the round trip time" (BSERT, SAGE, DOI 10.1177/0143624413481685) | Peer-reviewed journal | **Primary** — generalizes classical RTT beyond its restrictive assumptions |
| Siikonen, M-L., "Elevator traffic simulation", SIMULATION 61(4), 1993 (DOI 10.1177/003754979306100409) | Peer-reviewed journal | **Primary** — KONE Building Traffic Simulator validation lineage |
| CTBUH paper 1051, "Double-deck destination control system" | CTBUH technical paper | **Primary** — fetched; claims not verified before interruption |
| CTBUH paper 942, "Mitsubishi Elevator Equipment in Shanghai Tower" | CTBUH technical paper | **Primary** — fetched; building specs not verified before interruption |
| CTBUH paper 2388, "Elevator Designs for the Kingdom Tower" | CTBUH technical paper | **Primary** — fetched; not verified before interruption |
| Sorsa/Fortune, "Multiple objectives and system constraints in double-deck elevator dispatching" (academia.edu copy) | Conference/industry paper | **Primary** — fetched; not verified before interruption |
| ScienceDirect S0377221724003503 (EJOR 2024 review touching multi-car/ropeless systems) | Peer-reviewed journal | **Primary** — fetched; not verified before interruption |
| Peters Research, "Reverse journeys and destination control" | Industry research | **Primary** — the right source for DD non-compliance; not verified before interruption |
| Elevator World, "Is Destination Dispatch User-Friendly?" | Trade journal | **Acceptable** — DD usability/perception discussion; not verified before interruption |
| Elevator World, "Fundamentals of Traffic Analysis" | Trade journal | **Acceptable** — CIBSE criteria summary; not verified before interruption |
| ResearchGate copy of "ThyssenKrupp's TWIN lift system part one" | ResearchGate mirror | **Rejected by fetcher as unreliable** — no claims extracted |

## Verification methodology

Three rounds, ~317 subagent calls total. Pipeline per round: 5 search angles → parallel web search → URL-dedup → fetch ~25 sources → extract falsifiable claims (~120/round) → 3-vote adversarial verification of top 25 (each verifier prompted to refute against the primary source) → synthesis. Survival record: round 1 — 24/25 confirmed, 1 refuted; round 2 — 25/25 confirmed; round 3 — 0/25 completed (rate-limit interruption). One claim was killed on the merits across all rounds (pre-1994 fuzzy-logic-as-component lineage) and is excluded from the report.
