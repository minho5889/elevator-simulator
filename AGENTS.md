# Agent Instructions: Elevator Simulator Project

This file contains persistent, cross-session instructions and guidelines for any AI agent (Antigravity or subagent) collaborating on this repository.

---

## 1. Diagram Generation Rules
* **No ASCII Art:** Never use plain text ASCII art to represent architecture, logic flows, or state transitions.
* **Always use Mermaid:** Always use syntax-highlighted **Mermaid** blocks (` ```mermaid `) for any diagrams, graphs, flowcharts, or UML models.

---

## 2. Core Architecture Rules
* **Decoupled Mechanics:** Keep the deterministic simulation core (`src/elevatorsim/core/`) completely separated from the policy logic (`src/elevatorsim/policy/`). Do not import models, agents, or client APIs into the core package.
* **Test Isolation:** Ensure unit tests in `tests/test_core.py` run 100% offline with zero model mocking or API dependencies.
* **Two-Phase Agent Flow:** Maintain the two-phase dispatcher sequence in `src/elevatorsim/policy/agentic.py`:
  1. Phase 1: Tool execution to observe simulator state.
  2. Phase 2: Structured output mapping using `agent.structured_output` with history carried forward.

---

## 3. Dependency Controls
* Always pin `strands-agents == 1.42.0` and `google-genai >= 2.0.0` in `pyproject.toml` to guarantee compatibility with Gemini 3.5 Flash's strict `FunctionResponse` rules. Commit `uv.lock`.
