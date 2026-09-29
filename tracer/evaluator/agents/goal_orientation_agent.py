"""Agent that checks whether a task instruction is goal-oriented (Criterion 1).

Criterion: VIOLATION if the instruction is procedural (underspecified, requires
the agent to elicit information from the user before it can execute anything).
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

from evaluator.prompts.goal_orientation import SYSTEM_PROMPT, format_user_prompt


class _GoalOrientationEnv:
    """Minimal env for the goal-orientation classification pass."""

    def __init__(self, initial_observation: str) -> None:
        self.task = Task(
            user_id="goal_orientation_checker",
            actions=[],
            instruction=initial_observation,
            outputs=[],
        )
        self.actions: List[Action] = []
        self._initial_observation = initial_observation
        self.final_response: Optional[str] = None
        self.is_goal_oriented: Optional[bool] = None
        self.task_type: Optional[str] = None
        self.reason: Optional[str] = None

    def reset(self, task_index: Optional[int] = None) -> EnvResetResponse:
        del task_index  # unused; kept for protocol compatibility
        self.actions = []
        self.final_response = None
        self.is_goal_oriented = None
        self.task_type = None
        self.reason = None
        return EnvResetResponse(
            observation=self._initial_observation,
            info=EnvInfo(task=self.task, source="goal_orientation_checker"),
        )

    def _validate_final_output(self, content: str) -> Tuple[bool, str]:
        try:
            data = json.loads(content)
        except Exception as e:
            return False, f"Invalid JSON: {e}"
        if not isinstance(data, dict):
            return False, "Output must be a JSON object"
        required = {"is_goal_oriented", "task_type", "reason"}
        if set(data.keys()) != required:
            return False, f"JSON must contain exactly these keys: {sorted(required)}"
        if not isinstance(data["is_goal_oriented"], bool):
            return False, "'is_goal_oriented' must be a boolean"
        if data["task_type"] not in {"goal", "procedural"}:
            return False, "'task_type' must be 'goal' or 'procedural'"
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
                self.is_goal_oriented = data["is_goal_oriented"]
                self.task_type = data["task_type"]
                self.reason = data["reason"]
                observation = "###DONE###"
                done = True
                info.source = "respond"
            else:
                observation = (
                    "Error: output must be ONLY a JSON object with 'is_goal_oriented' (boolean), "
                    "'task_type' ('goal' or 'procedural'), and 'reason' (string). "
                    f"Validation error: {err}"
                )
                info.source = "respond_invalid"
        else:
            observation = f"Unknown action {action.name}"

        return EnvResponse(observation=observation, reward=0.0, done=done, info=info)


class GoalOrientationAgent:
    """Classifies whether a task instruction is goal-oriented or procedural."""

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

    def _empty_result(self) -> Dict[str, Any]:
        return {
            "is_goal_oriented": None,
            "task_type": None,
            "reason": "Model not configured or evaluation failed",
            "trajectory": [],
        }

    def check(
        self,
        instruction: str,
        domain: str,
        max_steps: int = 8,
    ) -> Dict[str, Any]:
        """Return goal-orientation verdict for a single instruction."""
        if self.model is None or self.provider is None:
            return self._empty_result()

        initial_observation = format_user_prompt(instruction=instruction, domain=domain)
        env = _GoalOrientationEnv(initial_observation=initial_observation)

        system_prompt = SYSTEM_PROMPT + (
            "\n\nWhen you are ready to finish, use Action with name='respond' and arguments "
            '{"content": <JSON with is_goal_oriented, task_type, reason>}.'
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
            result = self._empty_result()
            result["reason"] = f"LLM evaluation failed: {type(exc).__name__}: {exc}"
            return result

        if (
            env.is_goal_oriented is not None
            and env.task_type is not None
            and env.reason is not None
        ):
            return {
                "is_goal_oriented": env.is_goal_oriented,
                "task_type": env.task_type,
                "reason": env.reason,
                "trajectory": trajectory,
            }

        result = self._empty_result()
        result["trajectory"] = trajectory
        return result
