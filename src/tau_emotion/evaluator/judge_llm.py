"""
The LLM used by the conversation review judges (review, user-only review,
auth classification, hallucination check).

Defaults to DEFAULT_LLM_EVAL_USER_SIMULATOR. The review CLI calls
set_judge_llm() to use another model, e.g. a bare model name on the hosted
OpenAI-compatible endpoint (OPENAI_API_BASE), or an explicit api_base.
"""

from typing import Any, Optional

from tau_emotion.config import DEFAULT_LLM_EVAL_USER_SIMULATOR
from tau_emotion.data_model.message import AssistantMessage, UserMessage
from tau_emotion.utils.llm_utils import generate

_judge_model: str = DEFAULT_LLM_EVAL_USER_SIMULATOR
_judge_llm_args: dict[str, Any] = {}


def set_judge_llm(model: Optional[str] = None, llm_args: Optional[dict] = None):
    """Set the model and extra LLM args (api_base, api_key, temperature, ...)."""
    global _judge_model, _judge_llm_args
    if model is not None:
        _judge_model = model
    if llm_args is not None:
        _judge_llm_args = dict(llm_args)


def get_judge_model() -> str:
    return _judge_model


def judge_generate(
    model: Optional[str] = None, **kwargs: Any
) -> UserMessage | AssistantMessage:
    """generate() with the judge model and LLM args filled in."""
    return generate(model=model or _judge_model, **{**_judge_llm_args, **kwargs})
