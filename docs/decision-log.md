# Architecture Decision Log

This log documents key architectural decisions made during the design and development of the Elevator Simulator learning project.

---

## Decision 1: Separation of Deterministic Core and Agentic Policy

* **Context:** The simulation must support benchmarking of different dispatching logics (heuristics vs. LLMs).
* **Proposed Option:** Decouple physical physics/state updates (floors, car speed, passenger boardings) from the routing policy.
* **Alternative Rejected:** Run the entire simulation inside the LLM context (e.g. asking the agent to keep track of floors, passenger waiting times, and calculate physical steps directly in its prompt).
* **Rationale for Choice:**
  * LLMs are slow, expensive, and poor at executing step-by-step arithmetic loops.
  * Separating physics keeps the core 100% testable offline with no network/API requirements.
  * This structure enables direct A/B testing of alternative policies (LOOK baseline vs. Strands Agent) on identical scenarios.

---

## Decision 2: Fixed-Tick Event Loop for Tier 0

* **Context:** Choosing the time-stepping mechanism for the simulation engine.
* **Proposed Option:** Linear time-stepped loop (`current_time += 1`).
* **Alternative Rejected:** Discrete-event simulation using `SimPy`.
* **Rationale for Choice:**
  * A simple fixed-tick loop is extremely transparent, making logs easy to inspect and debug.
  * `SimPy` adds unnecessary async conceptual load for a "walking skeleton" (Tier 0).
  * *Upgrade path:* We defer SimPy to Tier 2 when multi-car coordination requires event-driven scheduling.

---

## Decision 3: Two-Phase LLM Invocation (Observe & Decide)

* **Context:** Structuring how the agent interacts with Strands tools and outputs structured Pydantic schemas on Google Gemini.
* **Proposed Option:** Two-phase execution:
  1. *Phase 1:* Invoke agent with tools enabled to read building state.
  2. *Phase 2:* Invoke `agent.structured_output(DispatchDecision, prompt)` to output the Pydantic schema using the accumulated message history.
* **Alternative Rejected:** A single prompt requesting the model to call tools *and* return JSON/structured schema in the same request.
* **Rationale for Choice:**
  * Mixing tool calling and structured output constraints in a single turn triggers API errors or bypasses tool executions on Gemini 3.5 Flash.
  * Decoupling the observation (tool-calling phase) from the decision (schema-formatting phase) makes the agentic loop highly stable.

---

## Decision 4: Gemini 3.5 Flash as Default Model

* **Context:** Selecting the default reasoning backend.
* **Proposed Option:** `gemini-3.5-flash`
* **Alternative Rejected:** `gemini-1.5-flash` (Deprecated) or `gemini-2.5-flash` (Older).
* **Rationale for Choice:**
  * `gemini-1.5-flash` is deprecated.
  * `gemini-3.5-flash` is generally available (GA), fast, cost-effective, and optimized for tool calling and structured outputs.
  * *Note on Non-Determinism:* Gemini 3.5 Flash deprecated sampling parameters (`temperature`, `top_p`), meaning we cannot set `temperature=0.0`. This introduces non-determinism, which further validates our LOOK baseline and trace-saving design.

---

## Decision 5: LOOK-Style Heuristic Baseline

* **Context:** Selecting a baseline algorithm.
* **Proposed Option:** LOOK algorithm (service requests in current direction, reverse direction when no requests remain in that direction).
* **Alternative Rejected:** First-Come, First-Served (FCFS) dispatcher.
* **Rationale for Choice:**
  * FCFS is extremely inefficient and not representative of real-world elevator baselines.
  * LOOK is standard, easy to implement, and serves as a highly competitive benchmark against the agentic dispatcher.
