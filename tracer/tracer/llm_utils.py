"""Shared LLM call utilities.

Uses litellm Router with RetryPolicy and cooldowns so all agents automatically
handle rate-limit errors without manual sleep/retry loops.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from litellm import Router
from litellm.router import RetryPolicy

# One Router instance per (full_model_key, api_base).
# Routers are cheap to create but hold retry state, so caching them lets the
# cooldown logic accumulate correctly across calls within a run.
_routers: Dict[Tuple[str, Optional[str]], Router] = {}


def _get_router(full_model: str, api_base: Optional[str]) -> Router:
    key = (full_model, api_base)
    if key not in _routers:
        # Hard per-request timeout. Without it a dropped VPN/proxy connection stays
        # ESTABLISHED with zero bytes and the job waits forever (seen: 6 jobs stalled
        # 30+ min). A normal ReAct step is 10-90 s; 300 s leaves room for a 30k-token
        # context, and TimeoutErrorRetries below retries on a fresh connection.
        litellm_params: Dict[str, Any] = {"model": full_model, "timeout": 300}
        if api_base:
            litellm_params["api_base"] = api_base

        _routers[key] = Router(
            model_list=[
                {
                    "model_name": full_model,
                    "litellm_params": litellm_params,
                }
            ],
            retry_policy=RetryPolicy(
                RateLimitErrorRetries=6,
                InternalServerErrorRetries=3,
                TimeoutErrorRetries=3,
                ServiceUnavailableErrorRetries=3,
            ),
            num_retries=6,
            retry_after=30,  # minimum seconds between retries
            timeout=300,  # Router-level too: the litellm_params timeout alone did
            # not fire on a stalled connection (9 jobs idle 70 min)
            disable_cooldowns=True,  # cooldowns require multiple deployments; with one model they block all calls
        )
    return _routers[key]


def completion_usage_tokens(
    res: Any,
) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    """Extract (prompt_tokens, completion_tokens, total_tokens) from a litellm completion response.

    ``total_tokens`` uses the API value when present, otherwise ``prompt + completion`` when both exist.
    Returns (None, None, None) when ``usage`` is missing or has no usable fields.
    """
    usage = getattr(res, "usage", None)
    if usage is None:
        return (None, None, None)
    if isinstance(usage, dict):
        p = usage.get("prompt_tokens")
        c = usage.get("completion_tokens")
        t = usage.get("total_tokens")
    else:
        p = getattr(usage, "prompt_tokens", None)
        c = getattr(usage, "completion_tokens", None)
        t = getattr(usage, "total_tokens", None)

    def _as_int(x: Any) -> Optional[int]:
        if x is None:
            return None
        try:
            return int(x)
        except (TypeError, ValueError):
            return None

    p, c, t = _as_int(p), _as_int(c), _as_int(t)
    if t is None and p is not None and c is not None:
        t = p + c
    if p is None and c is None and t is None:
        return (None, None, None)
    return (p, c, t)


def empty_usage_record() -> Dict[str, Any]:
    return {"prompt": None, "completion": None, "total": None, "complete": False}


def usage_record_from_solve_result(result: Any) -> Dict[str, Any]:
    return {
        "prompt": result.usage_prompt_tokens,
        "completion": result.usage_completion_tokens,
        "total": result.usage_total_tokens,
        "complete": result.usage_complete,
    }


def completion_with_retry(
    model: str,
    custom_llm_provider: Optional[str] = None,
    api_base: Optional[str] = None,
    **kwargs: Any,
) -> Any:
    """Drop-in replacement for litellm.completion with Router-based retry + cooldown.

    Accepts the same signature as litellm.completion.  When custom_llm_provider is
    given and not already embedded in model, it is prepended (e.g. "openai/gpt-4o").
    """
    if custom_llm_provider and "/" not in model:
        full_model = f"{custom_llm_provider}/{model}"
    else:
        full_model = model

    router = _get_router(full_model, api_base)
    kwargs.setdefault("timeout", 300)  # per-call as well; belt and braces
    return router.completion(model=full_model, **kwargs)
