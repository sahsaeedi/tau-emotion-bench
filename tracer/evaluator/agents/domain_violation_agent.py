"""Agent that checks for domain violations in the ground-truth actions (Criterion 4).

A domain violation = the task is out-of-domain (in_domain == False) but the
ground-truth action sequence attempts to fulfill the request instead of calling
the handoff tool.

Two-layer approach:
  Layer A (deterministic):
    - If in_domain == True  → no violation (return immediately).
    - If in_domain == False → check whether any GT action is a handoff tool.
        If a handoff IS present → no violation.
        If NO handoff       → candidate violation; promote to Layer B.
  Layer B (LLM):
    Confirms whether the in-domain classification was correct and whether
    the GT truly should have handed off instead of proceeding.

Handoff tool names per domain:
  airline, retail, bank, basketball,
  movie, restaurant, travel : transfer_to_human_agents
  telehealth                : transfer_to_human_support
  telecom                   : transfer_to_human_support  (registered but not implemented)
  school                    : none, so an out-of-domain school task always goes to Layer B
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Set, Tuple

from tracer.agents.chat_react_agent import ChatReActAgent
from tracer.prompts.in_domain_checker import DOMAIN_RULES_BY_DOMAIN
from tracer.types import (
    RESPOND_ACTION_FIELD_NAME,
    RESPOND_ACTION_NAME,
    Action,
    EnvInfo,
    EnvResetResponse,
    EnvResponse,
    Task,
)

from evaluator.prompts.domain_violation import SYSTEM_PROMPT, format_user_prompt

# Handoff tool names per domain — used by Layer A
HANDOFF_TOOLS: Dict[str, Set[str]] = {
    "airline": {"transfer_to_human_agents"},
    "retail": {"transfer_to_human_agents"},
    "telecom": {"transfer_to_human_support"},
    "telehealth": {"transfer_to_human_support"},
    "bank": {"transfer_to_human_agents"},
    "basketball": {"transfer_to_human_agents"},
    "movie": {"transfer_to_human_agents"},
    "restaurant": {"transfer_to_human_agents"},
    "school": set(),
    "travel": {"transfer_to_human_agents"},
}
_ALL_HANDOFF_TOOLS: Set[str] = {"transfer_to_human_agents", "transfer_to_human_support"}


# ---------------------------------------------------------------------------
# Layer A helper
# ---------------------------------------------------------------------------


def _gt_has_handoff(ground_truth_actions: List[Dict[str, Any]], domain: str) -> bool:
    handoff_names = HANDOFF_TOOLS.get(domain, _ALL_HANDOFF_TOOLS)
    for action in ground_truth_actions:
        name = (
            action.get("name", "")
            if isinstance(action, dict)
            else getattr(action, "name", "")
        )
        if name in handoff_names:
            return True
    return False


def check_domain_violation_deterministic(
    task: Dict[str, Any], domain: str
) -> Optional[Dict[str, Any]]:
    """Layer A: return a verdict dict if decidable deterministically, else None."""
    in_domain = task.get("in_domain")

    # No in_domain label at all — inconclusive
    if in_domain is None:
        return None

    # Clearly in-domain → no violation
    if in_domain is True:
        return {
            "is_domain_violation": False,
            "should_have_handed_off": False,
            "reason": task.get("in_domain_reason") or "Task classified as in-domain",
            "layer": "deterministic",
        }

    # Out-of-domain (in_domain == False) — check for handoff in GT
    ground_truth_actions = task.get("ground_truth_actions") or []
    if _gt_has_handoff(ground_truth_actions, domain):
        return {
            "is_domain_violation": False,
            "should_have_handed_off": False,
            "reason": "Task is out-of-domain but ground truth correctly calls the handoff tool",
            "layer": "deterministic",
        }

    # Candidate violation — promote to Layer B
    return None


# ---------------------------------------------------------------------------
# Layer B (LLM)
# ---------------------------------------------------------------------------


class _DomainViolationEnv:
    """Minimal env for the domain-violation confirmation pass."""

    def __init__(self, initial_observation: str) -> None:
        self.task = Task(
            user_id="domain_violation_checker",
            actions=[],
            instruction=initial_observation,
            outputs=[],
        )
        self.actions: List[Action] = []
        self._initial_observation = initial_observation
        self.final_response: Optional[str] = None
        self.is_domain_violation: Optional[bool] = None
        self.should_have_handed_off: Optional[bool] = None
        self.reason: Optional[str] = None

    def reset(self, task_index: Optional[int] = None) -> EnvResetResponse:
        self.actions = []
        self.final_response = None
        self.is_domain_violation = None
        self.should_have_handed_off = None
        self.reason = None
        return EnvResetResponse(
            observation=self._initial_observation,
            info=EnvInfo(task=self.task, source="domain_violation_checker"),
        )

    def _validate_final_output(self, content: str) -> Tuple[bool, str]:
        try:
            data = json.loads(content)
        except Exception as e:
            return False, f"Invalid JSON: {e}"
        if not isinstance(data, dict):
            return False, "Output must be a JSON object"
        required = {"is_domain_violation", "should_have_handed_off", "reason"}
        if set(data.keys()) != required:
            return False, f"JSON must contain exactly these keys: {sorted(required)}"
        if not isinstance(data["is_domain_violation"], bool):
            return False, "'is_domain_violation' must be a boolean"
        if not isinstance(data["should_have_handed_off"], bool):
            return False, "'should_have_handed_off' must be a boolean"
        if not isinstance(data["reason"], str) or not data["reason"].strip():
            return False, "'reason' must be a non-empty string"
        return True, ""

    def step(self, action: Action) -> EnvResponse:
        self.actions.append(action)
        done = False
        observation = ""
        info = EnvInfo(task=self.task, source=action.name)

        if action.name == RESPOND_ACTION_NAME:
            raw_content = action.kwargs.get(RESPOND_ACTION_FIELD_NAME, "")
            content = (
                json.dumps(raw_content)
                if isinstance(raw_content, dict)
                else raw_content
            )
            ok, err = self._validate_final_output(content)
            if ok:
                self.final_response = content
                data = json.loads(content)
                self.is_domain_violation = data["is_domain_violation"]
                self.should_have_handed_off = data["should_have_handed_off"]
                self.reason = data["reason"]
                observation = "###DONE###"
                done = True
                info.source = "respond"
            else:
                observation = (
                    "Error: output must be ONLY a JSON object with 'is_domain_violation' (boolean), "
                    "'should_have_handed_off' (boolean), and 'reason' (string). "
                    f"Validation error: {err}"
                )
                info.source = "respond_invalid"
        else:
            observation = f"Unknown action {action.name}"

        return EnvResponse(observation=observation, reward=0.0, done=done, info=info)


class DomainViolationAgent:
    """Checks for domain violations via deterministic Layer A + LLM Layer B."""

    def __init__(
        self,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        temperature: float = 0.0,
        api_base: Optional[str] = None,
    ):
        self.model = model
        self.provider = provider
        self.temperature = temperature
        self.api_base = api_base

    def check(
        self,
        task: Dict[str, Any],
        domain: str,
        max_steps: int = 8,
        force_llm: bool = False,
    ) -> Dict[str, Any]:
        """Return domain-violation verdict, using Layer A first, Layer B if needed."""
        # Layer A
        layer_a = check_domain_violation_deterministic(task, domain)
        if layer_a is not None and not force_llm:
            return {**layer_a, "trajectory": []}

        # Layer B: candidate violation (in_domain == False, no GT handoff) — confirm with LLM
        if self.model is None or self.provider is None:
            in_domain = task.get("in_domain")
            if in_domain is None:
                return {
                    "is_domain_violation": None,
                    "should_have_handed_off": None,
                    "reason": "in_domain field missing and LLM not configured",
                    "layer": "deterministic",
                    "trajectory": [],
                }
            # We know in_domain == False and no handoff in GT; best-effort without LLM
            return {
                "is_domain_violation": True,
                "should_have_handed_off": True,
                "reason": (
                    f"Task classified as out-of-domain ({task.get('in_domain_reason') or 'see in_domain_reason'}) "
                    "but ground truth does not call a handoff tool. LLM confirmation unavailable."
                ),
                "layer": "deterministic",
                "trajectory": [],
            }

        # Build LLM prompt using the domain rules from the in_domain_checker prompts (rules only:
        # the checker's own instructions and output format would conflict with this judge's)
        domain_policy = DOMAIN_RULES_BY_DOMAIN.get(domain, "")
        instruction = task.get("preference_instruction") or ""
        in_domain = task.get("in_domain")
        in_domain_reason = task.get("in_domain_reason")
        ground_truth_actions = task.get("ground_truth_actions") or []

        initial_observation = format_user_prompt(
            instruction=instruction,
            in_domain=in_domain,
            in_domain_reason=in_domain_reason,
            ground_truth_actions=ground_truth_actions,
            domain_policy=domain_policy,
        )
        env = _DomainViolationEnv(initial_observation=initial_observation)

        system_prompt = SYSTEM_PROMPT + (
            "\n\nWhen you are ready to finish, use Action with name='respond' and arguments "
            '{"content": <JSON with is_domain_violation, should_have_handed_off, reason>}.'
        )

        react_kwargs: Dict[str, Any] = {
            "tools_info": [],
            "wiki": system_prompt,
            "model": self.model,
            "provider": self.provider,
            "use_reasoning": True,
            "temperature": self.temperature,
        }
        if self.api_base is not None:
            react_kwargs["api_base"] = self.api_base
        react_agent = ChatReActAgent(**react_kwargs)

        try:
            res = react_agent.solve(env=env, task_index=0, max_num_steps=max_steps)
            trajectory = res.messages
        except Exception as exc:
            return {
                "is_domain_violation": None,
                "should_have_handed_off": None,
                "reason": f"LLM evaluation failed: {type(exc).__name__}: {exc}",
                "layer": "llm",
                "trajectory": [],
            }

        if env.is_domain_violation is not None and env.reason is not None:
            return {
                "is_domain_violation": env.is_domain_violation,
                "should_have_handed_off": env.should_have_handed_off,
                "reason": env.reason,
                "layer": "llm",
                "trajectory": trajectory,
            }

        return {
            "is_domain_violation": None,
            "should_have_handed_off": None,
            "reason": "LLM evaluation inconclusive",
            "layer": "llm",
            "trajectory": trajectory,
        }
