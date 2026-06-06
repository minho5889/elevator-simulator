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

## 3. Environment Configuration

Copy the environment template:
```bash
cp .env.example .env
```
Open `.env` and configure your Google AI Studio API key:
```ini
GEMINI_API_KEY=your_actual_key_here
```
*Note: Core tests and heuristic simulations run successfully even if the API key is not configured.*

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
