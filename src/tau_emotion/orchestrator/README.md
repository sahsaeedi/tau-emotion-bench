# Orchestrator Module

This module provides the orchestrator that manages simulations between agents, users, and environments.

## Overview

| Orchestrator | Communication Mode | Tool Execution | Participant Interface | Primary Use Case |
|--------------|-------------------|----------------|----------------------|------------------|
| `Orchestrator` | Half-duplex (turn-based) | Synchronous | `generate_next_message()` | Standard benchmarking |

---

## 1. Orchestrator (Half-Duplex)

The standard orchestrator for turn-based communication.

### Communication Pattern

```
Agent ──message──> User ──message──> Agent ──tool_call──> Environment ──result──> Agent
```

Each participant takes turns sending complete messages. Only one party "speaks" at a time.

### Participant Interface

```python
class MyAgent(HalfDuplexAgent):
    def generate_next_message(
        self, 
        message: ValidAgentInputMessage, 
        state: AgentState
    ) -> tuple[AssistantMessage, AgentState]:
        """Generate a complete response to the incoming message."""
        ...
```

### Tool Execution

- **Synchronous**: Tool calls block until complete
- **Immediate**: Results returned in the same step

### Trajectory Structure

```python
trajectory: list[Message]  # Flat list of messages
```

### Compatible Classes

| Role | Classes |
|------|---------|
| Agent | `LLMAgent`, `LLMGTAgent`, `LLMSoloAgent` |
| User | `UserSimulator`, `DummyUser` |

### Usage

```python
from tau_emotion.orchestrator.orchestrator import Orchestrator

orchestrator = Orchestrator(
    domain="airline",
    agent=LLMAgent(tools=tools, domain_policy=policy, llm="gpt-4"),
    user=UserSimulator(llm="gpt-4", instructions=instructions, tools=user_tools),
    environment=environment,
    task=task,
    max_steps=100,
    seed=42,
)
result = orchestrator.run()
```
