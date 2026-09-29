"""Agent that checks whether a task instruction follows the template (Criterion 2).

Criterion: VIOLATION if the instruction does NOT have both a tool-calling task
AND a user preference. Violations are only definitive on the preference-rewritten
instruction (`preference_instruction`); the per-raw-instruction pass is informational.
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

from evaluator.prompts.template_checker import SYSTEM_PROMPT, format_user_prompt


class _TemplateCheckerEnv:
    """Minimal env for the template-check pass."""

    def __init__(self, initial_observation: str) -> None:
        self.task = Task(
            user_id="template_checker",
            actions=[],
            instruction=initial_observation,
            outputs=[],
        )
        self.actions: List[Action] = []
        self._initial_observation = initial_observation
        self.final_response: Optional[str] = None
        self.has_tool_calling_task: Optional[bool] = None
        self.tool_calling_task_summary: Optional[str] = None
        self.has_preference: Optional[bool] = None
        self.preference_summary: Optional[str] = None
        self.follows_template: Optional[bool] = None
        self.reason: Optional[str] = None

    def reset(self, task_index: Optional[int] = None) -> EnvResetResponse:
        self.actions = []
        self.final_response = None
        self.has_tool_calling_task = None
        self.tool_calling_task_summary = None
        self.has_preference = None
        self.preference_summary = None
        self.follows_template = None
        self.reason = None
        return EnvResetResponse(
            observation=self._initial_observation,
            info=EnvInfo(task=self.task, source="template_checker"),
        )

    def _validate_final_output(self, content: str) -> Tuple[bool, str]:
        try:
            data = json.loads(content)
        except Exception as e:
            return False, f"Invalid JSON: {e}"
        if not isinstance(data, dict):
            return False, "Output must be a JSON object"
        required = {
            "has_tool_calling_task",
            "tool_calling_task_summary",
            "has_preference",
            "preference_summary",
            "follows_template",
            "reason",
        }
        if set(data.keys()) != required:
            return False, f"JSON must contain exactly these keys: {sorted(required)}"
        if not isinstance(data["has_tool_calling_task"], bool):
            return False, "'has_tool_calling_task' must be a boolean"
        if not isinstance(data["tool_calling_task_summary"], str):
            return False, "'tool_calling_task_summary' must be a string"
        if not isinstance(data["has_preference"], bool):
            return False, "'has_preference' must be a boolean"
        if not isinstance(data["preference_summary"], str):
            return False, "'preference_summary' must be a string"
        if not isinstance(data["follows_template"], bool):
            return False, "'follows_template' must be a boolean"
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
                self.has_tool_calling_task = data["has_tool_calling_task"]
                self.tool_calling_task_summary = data["tool_calling_task_summary"]
                self.has_preference = data["has_preference"]
                self.preference_summary = data["preference_summary"]
                self.follows_template = data["follows_template"]
                self.reason = data["reason"]
                observation = "###DONE###"
                done = True
                info.source = "respond"
            else:
                observation = (
                    "Error: output must be ONLY a JSON object with 'has_tool_calling_task' (boolean), "
                    "'tool_calling_task_summary' (string), 'has_preference' (boolean), "
                    "'preference_summary' (string), 'follows_template' (boolean), and 'reason' (string). "
                    f"Validation error: {err}"
                )
                info.source = "respond_invalid"
        else:
            observation = f"Unknown action {action.name}"

        return EnvResponse(observation=observation, reward=0.0, done=done, info=info)


class TemplateCheckerAgent:
    """Checks whether a task instruction follows the (tool-calling task + preference) template."""

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
            "has_tool_calling_task": None,
            "tool_calling_task_summary": None,
            "has_preference": None,
            "preference_summary": None,
            "follows_template": None,
            "reason": "Model not configured or evaluation failed",
            "trajectory": [],
        }

    def check(
        self,
        instruction: str,
        domain: str,
        is_preference_pass: bool = False,
        max_steps: int = 8,
    ) -> Dict[str, Any]:
        """Return template-check verdict for a single instruction."""
        if self.model is None or self.provider is None:
            return self._empty_result()

        initial_observation = format_user_prompt(
            instruction=instruction,
            domain=domain,
            is_preference_pass=is_preference_pass,
        )
        env = _TemplateCheckerEnv(initial_observation=initial_observation)

        system_prompt = SYSTEM_PROMPT + (
            "\n\nWhen you are ready to finish, use Action with name='respond' and arguments "
            '{"content": <JSON with has_tool_calling_task, tool_calling_task_summary, '
            "has_preference, preference_summary, follows_template, reason>}."
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

        if env.follows_template is not None and env.reason is not None:
            return {
                "has_tool_calling_task": env.has_tool_calling_task,
                "tool_calling_task_summary": env.tool_calling_task_summary,
                "has_preference": env.has_preference,
                "preference_summary": env.preference_summary,
                "follows_template": env.follows_template,
                "reason": env.reason,
                "trajectory": trajectory,
            }

        result = self._empty_result()
        result["trajectory"] = trajectory
        return result
