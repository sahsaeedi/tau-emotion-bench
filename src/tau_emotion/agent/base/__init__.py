"""
Base agent components.

This module exports the foundational building blocks for creating
turn-based (half-duplex) conversation participants.
"""

# LLM configuration mixin
from tau_emotion.agent.base.llm_config import LLMConfigMixin

# Protocol base class
from tau_emotion.agent.base.participant import HalfDuplexParticipant

__all__ = [
    # Protocol base class
    "HalfDuplexParticipant",
    # LLM configuration
    "LLMConfigMixin",
]
