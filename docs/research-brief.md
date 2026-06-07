# Research Brief: Strands Agents SDK & Gemini Integration

This document outlines the verified findings from Phase 0 of the Elevator Simulator project, referencing live documentation and API updates as of June 2026.

---

## 1. Strands SDK & Orchestration Primitives

### Installation
The core SDK and community-supported tools can be installed via PyPI:
```bash
pip install strands-agents strands-agents-tools
```
To run with Gemini support, use the recommended installation extra:
```bash
pip install "strands-agents[gemini]"
```

### Primitives Comparison
Strands organizes multi-agent logic into four distinct primitives. Based on the [Strands Agents Architecture Reference](https://strandsagents.com), the primitives map to application needs as follows:

1. **Agents-as-Tools (Hierarchical):**
   * *Mechanism:* A supervisor agent delegates tasks to specialized sub-agents exposed as standard Python tools.
   * *When it fits:* When a single "manager" coordinates multiple subordinates (e.g., a central dispatcher managing individual cars).
2. **Swarm (Model-Driven Handoff):**
   * *Mechanism:* Peer agents pass execution control and a shared context to one another dynamically and autonomously based on the current context.
   * *When it fits:* Exploratory or collaborative tasks where the routing is model-driven and emerges dynamically.
3. **Graph (Deterministic / Conditional Topology):**
   * *Mechanism:* The developer defines a structured state machine with fixed nodes and edges. The transition paths are conditional/deterministic, but agents populate the node actions.
   * *When it fits:* Processes requiring explicit flow-charts, conditional recovery, or human-in-the-loop gates.
4. **Workflow (Sequential Pipeline):**
   * *Mechanism:* A deterministic DAG that executes agents in a predefined, linear dependency chain.
   * *When it fits:* Repeatable, rigid automation pipelines.

---

## 2. Gemini 3.5 Flash Migration & Parameter Setup

According to the [Google Gemini 3.5 Migration Guide](https://ai.google.dev/gemini-api/docs/gemini-3-5-migration), several parameters have been updated for the Gemini 3.x API family:

### ⚠️ Deprecation of Sampling Parameters & Non-Determinism
* **No `temperature`, `top_p`, or `top_k`:** Google has removed support for these sampling parameters on `gemini-3.5-flash`. The model manages its own sampling parameters.
* **Side Effect (Non-Determinism):** Because we lose `temperature` as a determinism knob, and because `gemini-3.5-flash` runs with "thought-preservation" enabled by default, **agent dispatch decisions are non-reproducible**. 
* **Mitigation:** This behavior is expected and serves as the primary rationale for building a `HeuristicDispatcher` baseline and capturing recorded simulation traces. We will document this in `design.md`.

### Thinking Configurations
* **`thinking_budget` is Deprecated:** It is replaced by the `thinking_level` string enum.
* **Levels:** `minimal`, `low`, `medium` (default), and `high`.
* **Decision for Tier 0 & Tier 1:** For a simple 1-car, 5-floor dispatching problem, active reasoning is unnecessary and adds latency/token costs. We configure `"thinking_level": "minimal"` inside the `"thinking_config"` block to save on API overhead.

### Model Initialization Example
```python
from strands.models.gemini import GeminiModel

model = GeminiModel(
    client_args={"api_key": os.getenv("GEMINI_API_KEY")},
    model_id="gemini-3.5-flash",
    params={
        "thinking_config": {
            "thinking_level": "minimal"
        }
    }
)
```

---

## 3. Dependency Pinning & FunctionResponse Requirements

### The FunctionResponse `id` and `name` Requirement
Gemini 3.5 Flash enforces that all `FunctionResponse` parts sent back to the model contain both the unique tool invocation `id` and the matching function `name`. If either is missing, the API throws a `400 INVALID_ARGUMENT` error.

### Binding Constraints & Pinning Strategy
Because Strands wraps Google's `google-genai` SDK, the compatibility constraints actually live in the underlying Google SDK layer. The 3.5-flash migration changes require `google-genai>=2.0.0` to function properly. Pinning `strands-agents` alone does not guarantee that a new-enough transitive dependency will be resolved.

To ensure exact reproducibility and correct compatibility:
1. **PyProject.toml Pins:** We will explicitly pin both `strands-agents == 1.42.0` (latest release) and `google-genai>=2.0.0` in the dependencies block of `pyproject.toml`.
2. **Lockfile:** We will commit the `uv.lock` file to freeze resolved versions.
3. **Verification Command:** After scaffolding the environment, we will verify the active version of `google-genai` by running:
   ```bash
   uv pip show google-genai
   ```
   We will ensure the output confirms a version `>= 2.0.0`.

---

## 4. Two-Phase Tool Calling + Structured Output Implementation

### The Challenge
Combining tool calling (to read simulation state) with structured schema output (Pydantic validation) in a single LLM request can cause failures on some model backends, resulting in validation errors or missing tool usage.

### The Two-Phase Sequence
To ensure absolute reliability, the agent interaction is implemented in a **two-phase sequence**:
1. **Phase 1: Tool Call / State Gathering.** The agent is invoked as a standard call:
   ```python
   agent("Inspect the current simulation state using the provided tools.")
   ```
   The model makes tool calls to read the simulator state (`get_elevator_state()`, etc.), and the environment returns the tool execution results. The agent outputs a text-based analysis of the situation.
2. **Phase 2: Structured Output Response.** We query the agent for the final decision using the official Strands API method:
   ```python
   decision = agent.structured_output(DispatchDecision, "Decide the next action based on the state gathered.")
   ```
   Because the Strands `Agent` maintains the message history across calls, Phase 2 automatically carries forward the tool results from Phase 1 and outputs a validated Pydantic model (`DispatchDecision`).

---

## 5. Local LLM Integration: Gemma 4 via Ollama

To support developer workflows without API key constraints, we validated and wired in local model support using the Strands Ollama model provider.

### Gemma 4 Specifications
* **Release Date:** 2026-04-02
* **Model Varieties:** E2B, E4B, 26B-MoE, 31B-Dense
* **License:** Apache-2.0 open-weights license
* **Capabilities:** Native support for function calling and structured outputs (Pydantic validation).
* **Provider Wrapper:** Supported natively in Strands via `from strands.models.ollama import OllamaModel`.

### Local Validation Probe & Performance
* **Model ID:** `gemma4:e4b` (~9.6GB) running via native Ollama server.
* **Environment:** Tested on Apple Silicon (M4/16GB).
* **Inference Latency:** ~17 seconds per inference tick.
* **Core Advantages:**
  * **Quota Resilient:** Bypasses Gemini's 20 requests/day free quota.
  * **Bypasses Pacing Sleeps:** No 26-second rate limit sleeps are required, speeding up simulations.
  * **100% Reproducible:** Supports explicit seed pinning (`options={"seed": seed}`) and `temperature=0`, which the Gemini 3.5 Flash cloud path cannot do.

---

## 6. Deep Links & Reference Sources
* **Gemini 3.5 Migration Guide:** [ai.google.dev/gemini-api/docs/gemini-3-5-migration](https://ai.google.dev/gemini-api/docs/gemini-3-5-migration)
* **Gemini Model Parameters & Reference:** [ai.google.dev/gemini-api/docs/models/gemini](https://ai.google.dev/gemini-api/docs/models/gemini)
* **Strands SDK Repository:** [github.com/strands-agents/sdk-python](https://github.com/strands-agents/sdk-python)
* **Strands Ollama Provider Source:** [github.com/strands-agents/sdk-python/blob/main/src/strands/models/ollama.py](https://github.com/strands-agents/sdk-python/blob/main/src/strands/models/ollama.py)
