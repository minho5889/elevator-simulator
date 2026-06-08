# Elevator Simulator — Strands Multi-Agent Learning Build

A discrete-event elevator simulator built to demonstrate AWS Strands Agent SDK orchestration patterns and baseline heuristic policy comparisons using Google Gemini.

This repository implements **Phase 0 & Phase 1 (Tier 0 Walking Skeleton)**.

---

## 1. Project Architecture

The codebase is divided into two decoupled layers:
1. **Deterministic Core (`src/elevatorsim/core/`):** Fixed-tick physics engine, passenger waitlists, elevator movement, door timers, event emission, and metrics collection. Has zero LLM dependencies and is 100% testable offline.
2. **Policy Layer (`src/elevatorsim/policy/`):** Exposes a clean `Dispatcher` interface. Implements both a local LOOK heuristic baseline (`HeuristicDispatcher`) and a Strands Agentic dispatcher (`DispatcherAgent`) using `gemini-3.5-flash`.

---

## 2. Prerequisites & Installation

* **Runtime:** Python 3.12+ (Python 3.13.1 is verified active in this workspace)
* **Package Manager:** `uv` (installed via Homebrew)

To install dependencies and build the project, run:
```bash
uv sync
```
This commands creates the local virtual environment `.venv` and generates the lockfile `uv.lock`.

### Post-Install Verification
Confirm the underlying `google-genai` SDK is at version `2.0.0` or higher (required for Gemini 3.5 Flash parameter compatibility):
```bash
uv pip show google-genai
```

---

## 3. Environment Configuration & Model Providers

Copy the environment template:
```bash
cp .env.example .env
```

We support three LLM provider modes via the `LLM_PROVIDER` environment variable:
1. **`gemini` (Cloud - Default)**: Connects to Google AI Studio. Requires `GEMINI_API_KEY`.
2. **`gemma` (Local)**: Connects to a local Ollama instance running `gemma4:e4b`. No API key needed, unlimited free queries, zero rate limits, and 100% reproducible.
3. **`mock`**: Runs in an offline, mock heuristic fallback mode. Requires `MOCK_GEMINI=true` or API key set to `"mock"`.

*Note: Core tests and heuristic simulations run successfully even if no API key is configured.*

### Local Ollama Setup (macOS)
1. **Install Ollama**: Install via brew cask (do NOT use the CLI formula because it lacks the backend `llama-server` binary):
   ```bash
   brew install --cask ollama
   ```
   *(Downloading the app directly from [ollama.com](https://ollama.com) also works.)*
2. **Download Model**: Pull the Gemma 4 E4B model (~9.6GB):
   ```bash
   ollama pull gemma4:e4b
   ```
3. **Start Server**: Ensure the Ollama service is running:
   ```bash
   ollama serve
   ```
4. **Configure Environment**: Set the following in your `.env` file:
   ```ini
   LLM_PROVIDER=gemma
   OLLAMA_HOST=http://localhost:11434
   OLLAMA_MODEL_ID=gemma4:e4b
   ```
   *Warning: Do not containerize Ollama via Docker on macOS. Docker Desktop's Linux VM has no Metal GPU acceleration on macOS, resulting in CPU-only mode which is extremely slow.*

---

## 4. Execution Commands

### Run A/B Performance Comparison
To run the A/B simulation comparing the LOOK heuristic against the Strands Agent on the same scenario and seed:
```bash
uv run python -m elevatorsim.runners.run_tier0
```

### Run Unit Tests
* **Core Offline Tests (requires no keys or internet):**
  ```bash
  uv run pytest tests/test_core.py
  ```
* **Agent Smoke Test (skips automatically if `GEMINI_API_KEY` is not set):**
  ```bash
  uv run pytest tests/test_agents_smoke.py
  ```

---

## 5. Learning Resources (Docs)
* **Design & Architecture:** Check [docs/design.md](file:///Users/minholee/Projects/elevator-simulator/docs/design.md) for time models and coupling boundaries.
* **Decision Log:** See [docs/decision-log.md](file:///Users/minholee/Projects/elevator-simulator/docs/decision-log.md) for technical choices and alternatives rejected.
* **Strands SDK Guide:** Study [docs/learning-log.md](file:///Users/minholee/Projects/elevator-simulator/docs/learning-log.md) for a map of Agent, Tool, and Structured Output concepts in the codebase.
* **Phase 0 Research Brief:** Read [docs/research-brief.md](file:///Users/minholee/Projects/elevator-simulator/docs/research-brief.md) for live Gemini 3.5 Flash specifications.

---

## 6. Web Dashboard, API & Concurrency-Safe Routing

The web app launches a FastAPI server (`src/elevatorsim/web/server.py`) and a React dashboard (`src/elevatorsim/web/frontend/`). 

### Concurrency-Safe Provider Overrides
To support multi-user environments and parallel sessions, LLM configurations are scoped entirely to the individual request or WebSocket connection. The backend instantiates `DispatcherAgent` with client-provided parameters:
- `llm_provider`: Specifies the LLM engine to use (`gemini`, `gemma`, or `mock`).
- `api_key`: Optional client-side Google Gemini key override.
- `ollama_host`: Optional client-side Ollama server URL.
- `ollama_model_id`: Optional client-side Ollama model ID.

These parameters are threaded directly to the `DispatcherAgent` and model factories, avoiding global process environment modifications and guaranteeing complete concurrency safety.

### Deterministic Stall-Guard
To safeguard against empty or incomplete model generations (especially with smaller local models like Gemma 4), the agentic dispatcher implements a **Deterministic Stall-Guard**. If `structured_output` succeeds but returns an empty list or leaves a car idle that has onboard passengers or outstanding hall calls, the stall-guard intercepts and assigns the car a destination using the LOOK heuristic. This prevents passenger delivery stalls and guarantees forward progress.
