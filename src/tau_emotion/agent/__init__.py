import warnings

from tau_emotion.agent.base.llm_config import LLMConfigMixin
from tau_emotion.agent.base.participant import HalfDuplexParticipant
from tau_emotion.agent.base_agent import (
    HalfDuplexAgent,
    ValidAgentInputMessage,
)
from tau_emotion.agent.llm_agent import (
    LLMAgent,
    LLMAgentState,
    LLMGTAgent,
    LLMSoloAgent,
)

# =============================================================================
# DEPRECATION ALIASES
# =============================================================================
# These aliases maintain backward compatibility with code using old names.
# They will emit DeprecationWarning when used.


def __getattr__(name: str):
    """Module-level __getattr__ for deprecation warnings."""
    deprecated_aliases = {
        "BaseConversationParticipant": ("HalfDuplexParticipant", HalfDuplexParticipant),
        "BaseAgent": ("HalfDuplexAgent", HalfDuplexAgent),
        "LocalAgent": ("HalfDuplexAgent", HalfDuplexAgent),
    }

    if name in deprecated_aliases:
        new_name, new_class = deprecated_aliases[name]
        warnings.warn(
            f"{name} is deprecated, use {new_name} instead",
            DeprecationWarning,
            stacklevel=2,
        )
        return new_class

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# Direct aliases for static analysis tools (these don't trigger warnings on import)
BaseConversationParticipant = HalfDuplexParticipant
BaseAgent = HalfDuplexAgent
LocalAgent = HalfDuplexAgent


__all__ = [
    # Generic base class
    "HalfDuplexParticipant",
    # LLM configuration mixin
    "LLMConfigMixin",
    # Agent-specific base class
    "HalfDuplexAgent",
    "ValidAgentInputMessage",
    # LLM Agents
    "LLMAgent",
    "LLMAgentState",
    "LLMGTAgent",
    "LLMSoloAgent",
    # Deprecated aliases (kept for backward compatibility)
    "BaseConversationParticipant",
    "BaseAgent",
    "LocalAgent",
]
