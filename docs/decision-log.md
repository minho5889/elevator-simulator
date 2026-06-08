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

## Decision 2: Fixed-Tick Event Loop (All Tiers)

* **Context:** Choosing the time-stepping mechanism for the simulation engine.
* **Proposed Option:** Linear time-stepped loop (`current_time += 1`), stepping every car once per tick.
* **Alternative Rejected:** Discrete-event simulation using `SimPy`.
* **Rationale for Choice:**
  * A simple fixed-tick loop is extremely transparent, making logs easy to inspect and debug.
  * It aligns naturally with the per-tick WebSocket streaming protocol and the recorded preset caches; a discrete-event engine that *jumps* to the next event time would skip the intermediate frames the frontend animates.
  * Multi-car coordination (Tier 2) was implemented by simply iterating over all cars within each tick — no event scheduling required.
  * *Tier 3 note:* variable car speeds / express elevators are planned as **fractional position accumulation** inside this same loop (e.g. a car advances 0.5 floor/tick), which stays deterministic and cache-compatible. We therefore do **not** plan to adopt SimPy in any tier; the dependency was removed.

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
  * *Note on Non-Determinism:* Gemini 3.5 Flash deprecated sampling parameters (`temperature`, `top_p`), meaning we cannot set `temperature=0.0` for cloud runs. This introduces non-determinism for cloud-based runs. Determinism and reproducibility are now achieved locally via the offline Gemma 4 local provider (see Decision 12).

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
* **Proposed Option:** Introduce a mandatory 13-second rate-limiting delay between LLM calls (first state observation and final decision) to pace calls to under 5 RPM when running in cloud `gemini` mode. Bypass this delay when using the local `gemma` provider or `mock` mode. Additionally, skip live runs if the `GEMINI_API_KEY` is not found and `LLM_PROVIDER` is not `gemma`, default simulation runs to a short 50-tick count with an optional `--full` flag for 150-ticks, and catch quota exhaustion errors gracefully.
* **Alternative Rejected:** Run full-speed steps or require a paid plan for basic execution.
* **Rationale for Choice:**
  * Ensures that anyone can run the walking skeleton offline via the LOOK baseline or local Gemma 4 without rate limit delays or quota failures.
  * Paces cloud requests safely below the free tier limit, preventing aborted simulation runs.

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

---

## Decision 10: Multi-Car Per-Car Stepping with GroupDispatcher Protocol (Tier 2)

* **Context:** Upgrading from a single elevator car to a configurable bank (1-6 cars) requires coordinated dispatching and independent car stepping.
* **Proposed Option:** Maintain the existing tick-based `step()` API but iterate over all cars per tick. Introduce a new `GroupDispatcher` protocol with `dispatch_group(sim) -> Dict[str, int | None]` that assigns targets to all idle cars in a single call. The legacy single-car `Dispatcher` protocol is supported via a compatibility shim that temporarily swaps `sim.car` for each idle car.
* **Alternative Rejected:** Full SimPy process-per-car architecture with `yield` semantics.
* **Rationale for Choice:**
  * The per-car tick loop preserves full backward compatibility with single-car mode, existing preset caches, and the WebSocket tick protocol.
  * `GroupDispatcher` enables true group scheduling (nearest-idle-car) without breaking the `Dispatcher` interface.
  * A full SimPy process-per-car architecture was rejected (see Decision 2): non-integer timing is better handled by fractional position accumulation in the tick loop, and event-jumping would conflict with per-tick visualization.
  * The `GroupHeuristicDispatcher` implements both protocols, making it a drop-in replacement for either mode.

---

## Decision 11: FastMCP Server Integration (Tier 3)

* **Context:** Exposing simulator control, event emissions, and metrics programmatically to external tooling, agents, or client applications.
* **Proposed Option:** Expose a standard Model Context Protocol (MCP) server using the Python `FastMCP` framework (`src/elevatorsim/mcp/server.py`). Expose tools to configure simulations (`init_simulation`), step time (`step_simulation`), query state (`get_status`), query metrics (`get_metrics`), and manually spawn passengers (`spawn_passenger`).
* **Alternative Rejected:** Writing custom REST/JSON-RPC protocols or custom tool-definition templates.
* **Rationale for Choice:**
  - `FastMCP` standardizes tool definitions and communications out-of-the-box using stdio.
  - LLM agents (like Gemini or Claude) can natively connect to this server as an MCP client and execute simulation steps or query benchmarks.
  - Aligns with the Tier 3 roadmap of building swarm building controllers programmatically.

---

## Decision 12: Local LLM Provider Integration via Ollama / Gemma 4

* **Context:** Free-tier Gemini quota limits (~20 requests/day) and 26-second pacing delays make extensive offline agentic runs tedious and restrict testing scale.
* **Proposed Option:** Support a native local-LLM path using the Strands `OllamaModel` running a locally-hosted Gemma 4 (`gemma4:e4b`) server via Ollama.
* **Alternative Rejected:** Containerizing Ollama on macOS.
* **Rationale for Choice:**
  * **Unlimited & Offline:** Bypasses Gemini API key requirements and daily quotas, running 100% offline.
  * **Zero Pacing Sleep:** Bypasses the 26-second rate-limiting delays required for the Google AI Studio free tier.
  * **Reproducible Decisions:** Unlike cloud Gemini, Ollama allows temperature=0 and seed pinning (`options={"seed": seed}`), restoring fully reproducible A/B agentic runs.
  * **Mac Native (Cask vs Formula):** Must use native macOS Ollama (via cask or ollama.com), not the standard brew formula (which lacks the `llama-server` backend and causes runtime crashes).
  * **No Docker on Mac:** Containerizing Ollama on macOS is rejected. Docker Desktop's Linux VM has no access to Mac Metal GPU acceleration, causing it to run on CPU-only which makes inference painfully slow (taking minutes instead of seconds).

---

## Decision 13: Concurrency-Safe LLM Parameter Threading & Deterministic Stall-Guard

* **Context:**
  * The backend web server needs to handle multiple client sessions or concurrent simulation requests with different LLM configurations (Gemini, Gemma, or Mock) without letting them interfere with each other.
  * The agentic policy dispatcher can intermittently generate empty assignments or fail structured Turn schema validation (especially with smaller local models like Gemma 4).
* **Proposed Option:**
  * Eliminate global environment modifications (`override_llm_config`) in the FastAPI web server. Thread the requested LLM configuration parameters (`provider`, `api_key`, `ollama_host`, `ollama_model_id`) directly to `get_model()`, `DispatcherAgent` constructor, and update methods.
  * Implement a deterministic fallback (Stall-Guard) in `DispatcherAgent.dispatch_group` that assigns destinations using the LOOK heuristic if the LLM produces valid but empty decisions for cars carrying passengers or when hall calls are outstanding.
* **Alternative Rejected:**
  * Mutating `os.environ` on each request using global locks (causes execution bottlenecks and doesn't solve WebSocket streaming overlaps).
  * Leaving empty structured outputs unmitigated (causes cars to stall permanently mid-run).
* **Rationale for Choice:**
  * **Thread-Safety:** Passing parameters directly to class instances and factories ensures complete memory isolation across concurrent tasks.
  * **Robustness:** The deterministic stall-guard guarantees forward progress of the elevator cars, preventing prompt/reasoning failures from causing permanent passenger delivery stalls.


