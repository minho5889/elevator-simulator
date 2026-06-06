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
