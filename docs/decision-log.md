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

---

## Decision 6: Rate Limiting and Quota Management for API Interactions

* **Context:** Free Tier Google AI Studio API limits restrict developers to 15 RPM (Requests Per Minute) and small daily limits. Running simulations step-by-step can easily trigger HTTP 429 rate limit exceptions.
* **Proposed Option:** Introduce a mandatory 13-second rate-limiting delay between LLM calls (first state observation and final decision) to pace calls to under 5 RPM. Additionally, skip live runs if the `GEMINI_API_KEY` is not found, default simulation runs to a short 50-tick count with an optional `--full` flag for 150-ticks, and catch quota exhaustion errors gracefully to avoid breaking the CLI runner.
* **Alternative Rejected:** Run full-speed steps or require a paid plan for basic execution.
* **Rationale for Choice:**
  * Ensures that anyone can run the walking skeleton offline via the LOOK baseline or run a short comparison without quota failures.
  * Paces requests safely below the free tier limit, preventing aborted simulation runs.

---

## Decision 7: Stochastic Passenger Generation Profiles (Tier 1)

* **Context:** Evaluating policies using only deterministic scripted passenger sequences is prone to overfitting and does not model real-world peaks (morning rush, evening rush).
* **Proposed Option:** Implement a `TrafficGenerator` module inside the simulator core, parameterized by an arrival rate and profile shapes (`UNIFORM`, `DOWN_PEAK` morning rush, and `UP_PEAK` evening rush).
* **Alternative Rejected:** Hardcoding scripting logic or putting spawning rules inside the policy/agent layer.
* **Rationale for Choice:**
  * Preserves the decoupling between the deterministic core and the policy layer.
  * Allows evaluating dispatchers on standard traffic patterns to measure average wait/transit times under heavier loads.

---

## Decision 8: Side-by-Side Playback Cache & Local Storage Settings (Tier 1 Web App)

* **Context:** Daily API limits restrict Gemini Free Tier keys to 20 requests/day, making live runs expensive and prohibitive for casual A/B testing of the LOOK vs. Agentic dispatchers.
* **Proposed Option:** Build a preset scenario cache that pre-records simulation runs (seed 42, standard traffic profiles) and stores them as static JSON assets. Allow the user to input their own `GEMINI_API_KEY` (saved securely in local browser storage) for custom live runs.
* **Rationale for Choice:**
  * Preset scenarios load instantly and play back with zero API calls.
  * Local storage keeps the API key secure and prevents the backend server from exposing or sharing keys.

---

## Decision 9: Persistent WebSockets & Background Threading for Real-Time Interactive Simulator

* **Context:** Exposing real-time interactive simulation capabilities (clicking floors to spawn passengers, pausing/resuming, and stepping tick-by-tick) requires immediate, bi-directional communication between the client and the simulator instance.
* **Proposed Option:** Use a persistent WebSockets connection (`/api/ws/simulate`) to maintain dual simulation instances side-by-side in-memory on the backend. Because the agentic simulation step is synchronous and contains long rate-limiting delays (26 seconds per tick), run the simulation steps inside worker threads using `asyncio.to_thread` to prevent blocking the FastAPI event loop.
* **Rationale for Choice:**
  * WebSockets allow instantaneous updates and event broadcasts.
  * Synchronized inputs are easily cloned and scheduled in both LOOK and Gemini simulation queues.
  * Background threading ensures other API requests and concurrent WebSocket sessions remain active and responsive during agent thinking states.

