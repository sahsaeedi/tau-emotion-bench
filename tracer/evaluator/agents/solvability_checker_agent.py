"""Agent that checks whether a task is solvable by its ground-truth actions (Criterion 3).

Two-layer approach:
  Layer A (deterministic): reads the existing `solvable` and
    `task_checker_action_replay` fields from the task JSON. Produces a
    verdict immediately if the information is present.
  Layer B (LLM): only invoked when Layer A is inconclusive (e.g. both
    `solvable` is null and no replay errors are detected). Uses a
    ChatReActAgent to re-verify solvability from the instruction and the
    ground-truth action list.

Violation: any of (a) solvable == False, (b) a replay error is present,
           (c) Layer-B verdict is false.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from tracer.agents.chat_react_agent import ChatReActAgent
from tracer.types import (
    RESPOND_ACTION_FIELD_NAME,
    RESPOND_ACTION_NAME,
    Action,
    EnvInfo,
    EnvResetResponse,
    EnvResponse,
    Task,
)

from evaluator.prompts.solvability_checker import SYSTEM_PROMPT, format_user_prompt

# ---------------------------------------------------------------------------
# Layer A helpers
# ---------------------------------------------------------------------------


def _has_replay_error(replay: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """Return (True, reason) if any replay step has a non-null error."""
    for step in replay:
        err = step.get("error")
        if err is not None and str(err).strip():
            name = step.get("name", "?")
            return True, f"Step {step.get('step', '?')} ({name}) error: {err}"
    return False, ""


def check_solvability_deterministic(task: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Layer A: return a verdict dict if we can decide deterministically, else None."""
    solvable = task.get("solvable")
    replay = task.get("task_checker_action_replay") or []
    has_error, error_reason = _has_replay_error(replay)

    if has_error:
        not_solvable = task.get("not_solvable")
        reason = error_reason
        if task.get("solvable_reason"):
            reason = task["solvable_reason"] + " | Replay error: " + error_reason
        return {
            "solvable": False,
            "reason": reason,
            "not_solvable": not_solvable,
            "layer": "deterministic",
        }

    if solvable is True:
        return {
            "solvable": True,
            "reason": task.get("solvable_reason")
            or "Marked solvable with no replay errors",
            "not_solvable": None,
            "layer": "deterministic",
        }

    if solvable is False:
        return {
            "solvable": False,
            "reason": task.get("solvable_reason") or "Marked not solvable",
            "not_solvable": task.get("not_solvable"),
            "layer": "deterministic",
        }

    # solvable is None/missing and no replay errors — inconclusive
    return None


# ---------------------------------------------------------------------------
# Layer B (LLM)
# ---------------------------------------------------------------------------


class _SolvabilityCheckerEnv:
    """Minimal env for the LLM solvability-check pass."""

    def __init__(self, initial_observation: str) -> None:
        self.task = Task(
            user_id="solvability_checker",
            actions=[],
            instruction=initial_observation,
            outputs=[],
        )
        self.actions: List[Action] = []
        self._initial_observation = initial_observation
        self.final_response: Optional[str] = None
        self.solvable: Optional[bool] = None
        self.reason: Optional[str] = None

    def reset(self, task_index: Optional[int] = None) -> EnvResetResponse:
        self.actions = []
        self.final_response = None
        self.solvable = None
        self.reason = None
        return EnvResetResponse(
            observation=self._initial_observation,
            info=EnvInfo(task=self.task, source="solvability_checker"),
        )

    def _validate_final_output(self, content: str) -> Tuple[bool, str]:
        try:
            data = json.loads(content)
        except Exception as e:
            return False, f"Invalid JSON: {e}"
        if not isinstance(data, dict):
            return False, "Output must be a JSON object"
        if set(data.keys()) != {"solvable", "reason"}:
            return False, "JSON must contain exactly 'solvable' and 'reason'"
        if not isinstance(data["solvable"], bool):
            return False, "'solvable' must be a boolean"
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
                self.solvable = data["solvable"]
                self.reason = data["reason"]
                observation = "###DONE###"
                done = True
                info.source = "respond"
            else:
                observation = (
                    "Error: output must be ONLY a JSON object with 'solvable' (boolean) "
                    f"and 'reason' (string). Validation error: {err}"
                )
                info.source = "respond_invalid"
        else:
            observation = f"Unknown action {action.name}"

        return EnvResponse(observation=observation, reward=0.0, done=done, info=info)


class SolvabilityCheckerAgent:
    """Checks task solvability via deterministic Layer A, with LLM Layer B fallback."""

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
        max_steps: int = 8,
        force_llm: bool = False,
    ) -> Dict[str, Any]:
        """Return solvability verdict, using deterministic Layer A first, LLM Layer B if needed."""
        # Layer A
        layer_a = check_solvability_deterministic(task)
        if layer_a is not None and not force_llm:
            return {**layer_a, "trajectory": []}

        # Layer B: inconclusive — try LLM
        if self.model is None or self.provider is None:
            return {
                "solvable": None,
                "reason": "Inconclusive (solvable field missing, no replay errors) — LLM not configured",
                "not_solvable": None,
                "layer": "deterministic",
                "trajectory": [],
            }

        instruction = task.get("preference_instruction") or ""
        ground_truth_actions = task.get("ground_truth_actions") or []
        replay = task.get("task_checker_action_replay") or []

        initial_observation = format_user_prompt(
            instruction=instruction,
            ground_truth_actions=ground_truth_actions,
            action_replay=replay if replay else None,
        )
        env = _SolvabilityCheckerEnv(initial_observation=initial_observation)

        system_prompt = SYSTEM_PROMPT + (
            "\n\nWhen you are ready to finish, use Action with name='respond' and arguments "
            '{"content": <JSON with solvable, reason>}.'
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
                "solvable": None,
                "reason": f"LLM evaluation failed: {type(exc).__name__}: {exc}",
                "not_solvable": None,
                "layer": "llm",
                "trajectory": [],
            }

        if env.solvable is not None and env.reason is not None:
            return {
                "solvable": env.solvable,
                "reason": env.reason,
                "not_solvable": None,
                "layer": "llm",
                "trajectory": trajectory,
            }

        return {
            "solvable": None,
            "reason": "LLM evaluation inconclusive",
            "not_solvable": None,
            "layer": "llm",
            "trajectory": trajectory,
        }
