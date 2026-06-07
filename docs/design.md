# Design Documentation: Elevator Simulator

This document details the architectural design, time modeling, and separation of concerns implemented in the Elevator Simulator learning build.

---

## 1. Decoupled Architecture

The simulator is explicitly separated into two independent layers connected by a clean interface boundary:

1. **Deterministic Core:**
   * Contains physical structures (`Car`, `Building`), state models (`Passenger`), and time orchestration (`Simulation`).
   * Written in pure, dependency-free Python (no LLM, no Strands, no third-party libraries beyond SimPy).
   * Fully unit-testable offline with zero model dependencies or mock wrappers.
   * **Tier 2 upgrade:** supports multi-car banks (1-6 cars) with per-car stepping in `simulation.py`.
2. **Policy Dispatcher Seam:**
   * Defined by the `Dispatcher` and `GroupDispatcher` Protocols in `src/elevatorsim/policy/base.py`.
   * Single-car: `dispatch(simulation) -> int | None` (legacy Tier 0/1).
   * Multi-car: `dispatch_group(simulation) -> Dict[str, int | None]` (Tier 2+).
   * Enables seamless swapping between heuristic and LLM-backed Strands dispatchers.

```mermaid
flowchart TD
    subgraph Core ["CORE LAYER (Deterministic Core)"]
        direction LR
        Simulation["Simulation"] --> Building["Building"]
        Simulation --> CarBank["Car Bank (1..6)"]
        CarBank --> Car1["Car C1"]
        CarBank --> Car2["Car C2"]
        CarBank --> CarN["Car C_N"]
        Building --> Passenger["Passenger"]
    end

    subgraph Protocols ["policy/base.py"]
        direction TB
        Legacy["Dispatcher Protocol<br>dispatch(sim) → int"]
        Group["GroupDispatcher Protocol<br>dispatch_group(sim) → Dict"]
    end

    Heuristic["HeuristicDispatcher<br>(LOOK single-car)"]
    GroupHeuristic["GroupHeuristicDispatcher<br>(Nearest-idle-car LOOK)"]
    Agent["DispatcherAgent<br>(Strands Agent)"]

    subgraph Models ["strands.models"]
        Gemini["GeminiModel<br>(Cloud Gemini 3.5 Flash)"]
        Ollama["OllamaModel<br>(Local Gemma 4 E4B)"]
    end

    Core -.->|queries state| Protocols
    Legacy ==> Heuristic
    Legacy ==> Agent
    Group ==> GroupHeuristic
    Group ==> Agent
    Agent --> Models

    classDef core fill:#e1f5fe,stroke:#039be5,stroke-width:2px,color:#000;
    classDef interface fill:#fff3e0,stroke:#ffb74d,stroke-width:2px,color:#000;
    classDef impl fill:#f3e5f5,stroke:#ba68c8,stroke-width:2px,color:#000;

    class Core,Simulation,Building,CarBank,Car1,Car2,CarN,Passenger core;
    class Protocols,Legacy,Group interface;
    class Heuristic,GroupHeuristic,Agent impl;
```

---

## 2. Time, Event, and Reproduction Models

### Multi-Car Tick Engine (Tier 2)
The simulation engine runs a **per-car fixed-tick loop** where each `step()` call advances all cars in the bank by one tick:
* Each car moves exactly 1 floor per tick (independent of other cars).
* Doors stay open for exactly 2 ticks per car.
* All cars are stepped sequentially within a single `step()` call.
* **No discrete-event framework:** the engine is plain fixed-tick Python with no SimPy/discrete-event dependency. This keeps the loop transparent and, crucially, aligned with the per-tick WebSocket streaming protocol and recorded preset caches. Variable travel speeds (Tier 3) are planned as fractional position accumulation within this same loop rather than an event-driven rewrite — see `docs/decision-log.md` Decision 2.
* **Group dispatch:** After all cars are stepped, the dispatcher is queried once per tick. `GroupDispatcher.dispatch_group()` returns assignments for all idle cars simultaneously.

### Stochastic Traffic Generation (Tier 1)
To model realistic building usage, passenger arrivals are generated stochastically using the `TrafficGenerator` module:
* **Arrival Rate:** Determines the probability (0.0 to 1.0) of a passenger spawning at any given simulation tick.
* **Profiles:** Supports three pre-defined traffic distribution patterns:
  * `UNIFORM`: Passengers spawn on any floor, heading to any other floor with uniform probability.
  * `DOWN_PEAK` (Morning rush): Passengers spawn on upper floors (1 to 4) heading to the lobby (floor 0).
  * `UP_PEAK` (Evening rush): Passengers spawn at the lobby (floor 0) heading to upper floors (1 to 4).
* The generator is invoked by the `Simulation` during its tick step and utilizes the central `RNG` for deterministic behavior.

### Domain Events (Logging & Metrics Only)
All state changes emit rich domain events (e.g. `PassengerSpawned`, `CallRegistered`, `CarArrived`, `DoorOpened`, `PassengerBoarded`, `PassengerDeboarded`, `DoorClosed`, `CarMoved`, `CarDispatched`) defined in `events.py`.
* **`CarDispatched` (Tier 2):** Emitted when the group dispatcher assigns a car to a target floor.
* **Important:** These events are used **strictly** for logging, terminal tracing, and metrics collection (`metrics.py`). 
* They do **not** trigger or schedule actions inside the simulation engine. This keeps the time stepping simple and robust.
* All events carry a `car_id` field, enabling the frontend to track per-car state in multi-car mode.

### Reproducibility & Seeded RNG
* **Seeded RNG:** `config.py` exports a central `RNG` instance (`random.Random(seed)`). Any stochastic logic must use this central generator to ensure that runs remain deterministic.
* **A/B Fairness:** The runner re-seeds the central RNG and completely resets the simulation objects before both the heuristic and agentic runs. This guarantees both dispatchers face the exact same scenario for an apples-to-apples performance comparison.

---

## 3. Rate Limits & API Quotas

To ensure reliability and respect Google AI Studio Free Tier limits (which impose strict rate limits and daily quotas), the project incorporates several protection strategies:

* **Rate-Limiting Sleeps:** In `DispatcherAgent` when using the cloud `gemini` provider, we insert a 13-second wait (`time.sleep(13)`) before the initial state observation tool call, and another 13-second wait before calling `.structured_output()`. This 26-second delay per tick prevents hitting Google's 15 Requests Per Minute (RPM) limits.
* **Local Provider Bypass:** When `LLM_PROVIDER` is set to `gemma`, all rate-limiting sleeps are bypassed. Since the model runs locally via Ollama, there is no RPM limit, allowing fast tick iterations (governed purely by local GPU/CPU compute latency).
* **Offline Baseline Mode (Quota Resilience):** The Heuristic LOOK baseline dispatcher operates 100% offline without requiring a `GEMINI_API_KEY`.
* **Skipping Live Runs:** If the `GEMINI_API_KEY` is not detected in the environment or `.env` file, and `LLM_PROVIDER` is not set to `gemma`, the runners (`run_tier0.py` and `run_tier1.py`) skip the agentic run and gracefully output the heuristic baseline results, preventing runtime crashes.
* **Quota Exhaustion Handling:** In `run_tier1.py`, the agentic execution is wrapped in a `try-except` block. If a quota exhaustion limit is reached, it catches the exception and logs a clean, informative error message instructing the developer how to resolve the issue (e.g. by enabling pay-as-you-go billing).
* **Conserving Daily Quotas:** The default duration for evaluation runs is capped at 50 ticks to conserve API calls. A `--full` command-line flag is available to scale the run up to 150 ticks for paid tiers.

---

## 4. Agentic Design & Model Providers

### Two-Phase Tool Calling + Structured Output
Gemini 3.5 Flash and Gemma 4 require tool outputs to be mapped with both `id` and `name` attributes inside `FunctionResponse`. To ensure high reliability, the `DispatcherAgent` executes a two-phase flow:
1. **Phase 1 (Observe):** The agent runs tools (`get_elevator_state`, `get_floor_calls` or `get_all_cars_state`, `get_floor_calls`) and writes an analysis of the building status.
2. **Phase 2 (Decide):** The agent calls `.structured_output(DispatchDecision, prompt)` or `.structured_output(GroupDispatchDecision, prompt)` which carries forward the history from Phase 1 and returns the validated Pydantic decision.

### Model Providers
* **GeminiModel (`gemini`)**: Connects to the cloud-hosted Gemini 3.5 Flash. Requires internet access and a `GEMINI_API_KEY`.
* **OllamaModel (`gemma`)**: Connects to a local Ollama server running the Gemma 4 E4B model. Does not require an API key or internet access.

### Non-Determinism vs. Local Reproducibility
* **Cloud Non-Determinism:** Google deprecated sampling parameters (`temperature`, `top_p`) on Gemini 3.5 Flash, and thinking is active by default. Because we cannot force `temperature=0` and thinking history introduces variability, cloud-based agentic decisions are non-deterministic.
* **Local Reproducibility:** By contrast, the local `OllamaModel` supports explicit configuration of `temperature=0` and seed pinning (`options={"seed": seed}`). This completely restores reproducible A/B testing: executing the same seed scenario twice yields identical agentic dispatch decisions.
* **Robustness & Retries:** Small local models like Gemma 4 occasionally return malformed structures or fail Pydantic validation. To guarantee runtime robustness, the structured output phase in both single-car and multi-car dispatchers wraps `.structured_output()` in a 2-attempt retry block.

---

## 5. Scaling Path (Tiers 0-3)

The project is structured to easily scale across tiers:

* **Tier 0 (Walking Skeleton) [Completed]:** 1 car, 5 floors, scripted passengers, LOOK vs. Agentic Dispatcher.
* **Tier 1 (Stochastic Traffic) [Completed]:** Introduce stochastic passenger spawns using the seeded `RNG` and custom traffic profiles (`UNIFORM`, `UP_PEAK`, `DOWN_PEAK`).
* **Tier 2 (Multi-Car Bank) [Completed]:** Upgraded to an elevator bank (1-6 configurable cars) with `GroupDispatcher` protocol and nearest-idle-car LOOK group scheduling. Both the heuristic and agentic dispatchers implement group dispatch. Frontend renders multi-shaft car tracks. Full backward compatibility with single-car mode and preset caches.
* **Tier 3 (Skyscraper) [Partially Completed]:** Expose a standard FastMCP server (`src/elevatorsim/mcp/server.py`) for remote configuration, time-stepping, status query, passenger spawning, and performance telemetry comparison. Planned: Swarm and Workflow orchestration across hierarchical building controllers; variable car speeds modeled via fractional position accumulation in the existing tick loop (no SimPy).

---

## 6. Web Application & Real-Time Simulation (WebSockets)

To enable side-by-side comparative visualization and interactive control, the system includes a web application layered on top of the simulator package.

### Architecture overview
* **FastAPI Server (`src/elevatorsim/web/server.py`):** Acts as the simulation server. It hosts REST endpoints for preset caching and API-key checking, and a WebSocket path for live interactive sessions.
* **Vite React Frontend (`src/elevatorsim/web/frontend/`):** Implements a dark-themed glassmorphism dashboard that renders the physical shafts, passenger queues, telemetry metrics, and comparison charts.

### Real-Time WebSockets Engine
When a custom interactive session starts, the frontend opens a persistent WebSocket connection to `/api/ws/simulate`:
1. **Synchronized Dual Instantiation:** The backend spins up separate `Simulation` instances for both LOOK and Gemini dispatchers, using identical seeds and traffic profiles.
2. **Synchronized User Actions:** When the user clicks the UI canvas to spawn a passenger manually, the request is broadcast over the WebSocket. The backend instantiates matching passenger entities and schedules them in both simulators, preserving A/B benchmarking fairness.
3. **Pacing & Worker Thread Isolation:** Because the Gemini dispatcher utilizes a synchronous 26-second rate-limiting delay, calling it directly would block the FastAPI async event loop. To prevent this, the backend executes simulation ticks in separate OS-level threads using `asyncio.to_thread`.
4. **Pull-Based stepping loop:** To handle Gemini latency seamlessly, the frontend runs a pull-based stepping loop. Instead of blindly ticking on a fixed interval, the frontend only triggers the next simulation tick after receiving the state update for the current tick from the server, displaying a visual "Gemini is thinking..." load mask during active agent turns.

