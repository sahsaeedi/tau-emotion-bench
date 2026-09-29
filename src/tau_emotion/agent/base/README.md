# Base Agent Components

This directory contains the foundational building blocks for creating turn-based (half-duplex) conversation participants (agents and users).

## Table of Contents

1. [File Overview](#file-overview)
2. [Protocol Class](#protocol-class)
3. [LLM Configuration](#llm-configuration)
4. [Usage Example](#usage-example)

---

## File Overview

| File | Purpose |
|------|---------|
| `participant.py` | Protocol base class (`HalfDuplexParticipant`) |
| `llm_config.py` | Shared LLM configuration (`LLMConfigMixin`) |

---

## Protocol Class

### `HalfDuplexParticipant[InputMessageType, OutputMessageType, StateType]`

Turn-based communication where participants take turns speaking.

```python
class HalfDuplexParticipant(ABC, Generic[InputMessageType, OutputMessageType, StateType]):
    
    @abstractmethod
    def generate_next_message(
        self, message: InputMessageType, state: StateType
    ) -> tuple[OutputMessageType, StateType]:
        """Generate a complete response to an input message."""
    
    @abstractmethod
    def get_init_state(self, message_history: Optional[list[Message]] = None) -> StateType:
        """Get initial state."""
    
    def stop(self, message=None, state=None) -> None:
        """Stop the participant (cleanup)."""
    
    @classmethod
    def is_stop(cls, message: OutputMessageType) -> bool:
        """Check if message indicates conversation should stop."""
    
    def set_seed(self, seed: int):
        """Set random seed for reproducibility."""
```

**Use for:** Text chat and any turn-based interaction.

---

## LLM Configuration

### `llm_config.py`

Shared LLM configuration for any LLM-powered participant.

```python
class LLMConfigMixin:
    """Used by both agents and user simulators."""
    
    def __init__(self, *args, llm: str, llm_args: Optional[dict] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.llm = llm
        self.llm_args = deepcopy(llm_args) if llm_args is not None else {}
    
    def set_seed(self, seed: int):
        """Set the seed for the LLM."""
        self.llm_args["seed"] = seed
```

---

## Usage Example

### Half-Duplex LLM Agent

```python
from typing import Optional

from tau_emotion.agent.base.llm_config import LLMConfigMixin
from tau_emotion.agent.base_agent import HalfDuplexAgent, ValidAgentInputMessage
from tau_emotion.agent.llm_agent import LLMAgentState
from tau_emotion.data_model.message import (
    AssistantMessage,
    MultiToolMessage,
    SystemMessage,
)
from tau_emotion.environment.tool import Tool
from tau_emotion.utils.llm_utils import generate


class MyHalfDuplexAgent(
    LLMConfigMixin,
    HalfDuplexAgent[LLMAgentState],
):
    def __init__(
        self,
        tools: list[Tool],
        domain_policy: str,
        llm: str,
        llm_args: Optional[dict] = None,
    ):
        super().__init__(
            tools=tools,
            domain_policy=domain_policy,
            llm=llm,
            llm_args=llm_args,
        )

    def get_init_state(self, message_history=None) -> LLMAgentState:
        return LLMAgentState(
            system_messages=[SystemMessage(role="system", content=self.domain_policy)],
            messages=message_history or [],
        )

    def generate_next_message(
        self, message: ValidAgentInputMessage, state: LLMAgentState
    ) -> tuple[AssistantMessage, LLMAgentState]:
        # Add the user's message or the tool results to the history
        if isinstance(message, MultiToolMessage):
            state.messages.extend(message.tool_messages)
        else:
            state.messages.append(message)

        # Call the LLM with the tools it may use
        response = generate(
            model=self.llm,
            tools=self.tools,
            messages=state.system_messages + state.messages,
            **self.llm_args,
        )

        state.messages.append(response)
        return response, state
```

---

## Summary

| Component | Purpose | Key Methods/Fields |
|-----------|---------|-------------------|
| `HalfDuplexParticipant` | Turn-based protocol | `generate_next_message()` |
| `LLMConfigMixin` | LLM configuration | `llm`, `llm_args`, `set_seed()` |

**To create a new participant:**

1. Subclass `HalfDuplexAgent` (or `HalfDuplexUser`)
2. Add `LLMConfigMixin` if the participant calls an LLM (put it before the protocol base)
3. Define a state class
4. Implement `get_init_state()` and `generate_next_message()`
