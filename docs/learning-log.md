# Strands Multi-Agent Learning Log

This log is seeded for tracking your mastery of the Strands Agents SDK and agentic design patterns.

---

## 1. Core Strands SDK Primitives in this Project

### A. The `Agent` Class
* **Concept:** A model-driven agent coordinator that manages conversation history, system prompt context, and registers available tools.
* **Where it lives in Code:**
  * [src/elevatorsim/policy/agentic.py](file:///Users/minholee/Projects/elevator-simulator/src/elevatorsim/policy/agentic.py#L38-L47): Instantiated as `Agent(model=self.model, tools=[...], system_prompt=...)`.
* **Key Learning:** The `Agent` acts as an orchestrator. It does not dictate flow deterministically; rather, it uses the model's reasoning loop to decide when to call tools and how to handle the prompt.

### B. The `@tool` Decorator
* **Concept:** Exposes raw Python functions as structured JSON schemas to the model. The SDK handles schema parsing, invocation, and returning the output to the model context.
* **Where it lives in Code:**
  * [src/elevatorsim/tools/sim_tools.py](file:///Users/minholee/Projects/elevator-simulator/src/elevatorsim/tools/sim_tools.py): Exposes `get_elevator_state` and `get_floor_calls`.
* **Key Learning:** Tools must be side-effect free relative to the agent's context. In our design, they read state using a global thread-local context pointer (`_active_simulation`) which is set and cleared during the dispatch cycle.

### C. Structured Output (`structured_output` method)
* **Concept:** Forces the LLM to format its response matching a Pydantic schema class, validating the output before returning it to the user.
* **Where it lives in Code:**
  * [src/elevatorsim/policy/agentic.py](file:///Users/minholee/Projects/elevator-simulator/src/elevatorsim/policy/agentic.py#L55-L58): Calls `agent.structured_output(DispatchDecision, prompt)`.
  * [src/elevatorsim/policy/schemas.py](file:///Users/minholee/Projects/elevator-simulator/src/elevatorsim/policy/schemas.py): Defines `DispatchDecision` inheriting from `pydantic.BaseModel` with a validator checking floor boundaries.
* **Key Learning:** Using the official method `agent.structured_output(Schema, prompt)` guarantees history preservation across calls, enabling reliable multi-step flows.

### D. Conversation State/History Persistence
* **Concept:** The `Agent` maintains the message list of the chat session.
* **Where it lives in Code:**
  * [src/elevatorsim/policy/agentic.py](file:///Users/minholee/Projects/elevator-simulator/src/elevatorsim/policy/agentic.py#L52-L58): We first call `agent("Observe state...")` to let it execute tools. Then we call `agent.structured_output(...)`. The second call automatically carries forward the tools' outputs from the history.
* **Key Learning:** This two-phase sequence avoids mixing tool-execution steps and output-schema formatting constraints in a single API call, resolving common issues on Gemini 3.5 Flash.

---

## 2. Gemini 3.5 Flash Integration Lessons

### A. Deprecated Parameter Behaviors
* **Sampling Parameters:** Configuring `temperature`, `top_p`, or `top_k` on `gemini-3.5-flash` results in API schema errors. The model controls its own sampling configuration.
* **Non-Determinism:** The combination of deprecated temperature control and default-active thought preservation means agent decisions are inherently non-reproducible. Evaluation must rely on statistical comparison over multiple seeds against a deterministic LOOK baseline.
* **Thinking Level Configuration:** While thinking is active by default, the `thinking_level` parameter can be configured to `"minimal"` inside the `thinking_config` parameter dictionary. This is crucial for simple routing tasks to minimize execution latency and token usage.

### B. Strands Structured Output & Tool Call Requirements
* **FunctionResponse ID and Name:** Gemini 3.5 Flash requires all tool execution responses to contain both the tool's execution `id` and the function `name`. Omitting either causes an immediate `400 INVALID_ARGUMENT` error. The underlying Python SDK `google-genai >= 2.0.0` is required to ensure these fields are populated correctly.
* **Two-Phase Separation:** Combining tool calling and structured formatting constraints in a single step often fails. Splitting it into a text-based tool execution turn (Phase 1) followed by a schema validation request (Phase 2) ensures that the model accesses the correct tool-gathered context before outputting structured JSON.

---

## 3. Rate-Limiting & Quota Lessons
* **Google AI Studio Free Tier Pace:** Free tier keys are strictly limited to 15 RPM. A single simulator tick requiring a two-phase dispatch flow consumes 2 requests. 
* **Safe Delay Pacing:** Sleeping for 13 seconds between API calls inside `DispatcherAgent` effectively restricts the rate to under 5 RPM, providing a comfortable buffer against 429 errors.
* **Resilience Patterns:** Incorporating a fallback LOOK heuristic, checking for `GEMINI_API_KEY` before starting agent runs, and catching quota limit exceptions prevents local pipeline failures and enables continuous development.

---

## 4. Model Provider Swapping & Local Offline Execution

### A. Factory Pattern for Provider Abstraction
* **Concept:** Instead of hardcoding model construction or provider imports inside policy/agent classes, use a central factory (`get_model()`) inside a configuration module.
* **Where it lives in Code:**
  * [src/elevatorsim/config.py](file:///Users/minholee/Projects/elevator-simulator/src/elevatorsim/config.py): The `get_model()` factory resolves `LLM_PROVIDER` and returns either a `GeminiModel` (cloud) or an `OllamaModel` (local).
  * [src/elevatorsim/policy/agentic.py](file:///Users/minholee/Projects/elevator-simulator/src/elevatorsim/policy/agentic.py): Simply calls `self.model = get_model()`, leaving the dispatcher logic completely unchanged.
* **Key Learning:** The dispatcher agent only interacts with the generic model interface. Swapping from cloud-based API endpoints to a locally-run LLM requires zero changes to the orchestration workflow, prompt structure, or tool calling loops.

### B. Local Model Robustness (Structured Output Retries)
* **Concept:** Small local models (e.g. Gemma 4 E4B) are faster and free from API rate limits, but occasionally produce invalid formatting or fail Pydantic validation compared to larger cloud models.
* **Where it lives in Code:**
  * [src/elevatorsim/policy/agentic.py](file:///Users/minholee/Projects/elevator-simulator/src/elevatorsim/policy/agentic.py): Retries the `structured_output()` call up to 2 times upon encountering validation/parsing exceptions.
* **Key Learning:** Adding lightweight retry logic around the structured output phase significantly improves the execution stability of agent runs when powered by local models, without affecting the simulator's deterministic physics loop.
