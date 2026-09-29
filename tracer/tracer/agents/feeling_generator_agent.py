"""LLM pass that produces `feeling` from story + instructions only (no tools)."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from tracer.agents.chat_react_agent import ChatReActAgent
from tracer.llm_utils import empty_usage_record, usage_record_from_solve_result
from tracer.prompts.feeling_generator import (
    FEELING_SYSTEM_PROMPT,
    format_feeling_user_prompt,
)
from tracer.types import (
    RESPOND_ACTION_FIELD_NAME,
    RESPOND_ACTION_NAME,
    Action,
    EnvInfo,
    EnvResetResponse,
    EnvResponse,
    GeneratedTaskCandidate,
    Task,
)


def _sanitize_temperature(model: Optional[str], temperature: float) -> float:
    if model and model.startswith("gpt-5"):
        return 1.0
    return temperature


class _FeelingGenEnv:
    def __init__(self, initial_observation: str) -> None:
        self.task = Task(
            user_id="feeling_generator",
            actions=[],
            instruction=initial_observation,
            outputs=[],
        )
        self.actions: List[Action] = []
        self._initial_observation = initial_observation
        self.final_response: Optional[str] = None
        self.feeling: Optional[str] = None

    def reset(self, task_index: Optional[int] = None) -> EnvResetResponse:
        self.actions = []
        self.final_response = None
        self.feeling = None
        return EnvResetResponse(
            observation=self._initial_observation,
            info=EnvInfo(task=self.task, source="feeling_generator"),
        )

    def _validate_final_output(self, content: str) -> Tuple[bool, str]:
        try:
            data = json.loads(content)
        except Exception as e:
            return False, f"Invalid JSON: {e}"
        if not isinstance(data, dict):
            return False, "Output must be a JSON object"
        if set(data.keys()) != {"feeling"}:
            return False, "JSON must contain only the key 'feeling'"
        if not isinstance(data["feeling"], str) or not data["feeling"].strip():
            return False, "'feeling' must be a non-empty string"
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
                self.feeling = json.loads(content)["feeling"].strip()
                observation = "###DONE###"
                done = True
                info.source = "respond"
            else:
                observation = (
                    "Error: output must be ONLY a JSON object with a single key 'feeling' (non-empty string). "
                    f"Validation error: {err}"
                )
                info.source = "respond_invalid"
        else:
            observation = f"Unknown action {action.name}"

        return EnvResponse(observation=observation, reward=0.0, done=done, info=info)


class FeelingGeneratorAgent:
    """Runs after task generation; fills `candidate.feeling` with a separate model temperature."""

    def __init__(
        self,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        temperature: float = 0.9,
        api_base: Optional[str] = None,
    ) -> None:
        self.model = model
        self.provider = provider
        self.temperature = _sanitize_temperature(model, temperature)
        self.api_base = api_base

    def generate_feeling(
        self,
        domain: str,
        candidate: GeneratedTaskCandidate,
        max_steps: int = 12,
    ) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
        if self.model is None or self.provider is None:
            return "", [], empty_usage_record()

        initial_observation = format_feeling_user_prompt(
            domain=domain,
            user_id=candidate.user_id,
            story=candidate.story or "",
            instructions=candidate.instructions or [],
        )
        env = _FeelingGenEnv(initial_observation=initial_observation)
        system_prompt = FEELING_SYSTEM_PROMPT + (
            "\n\nWhen you are ready to finish, use Action with name='respond' and arguments "
            '{"content": <JSON object with only key "feeling">}.'
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
            usage = usage_record_from_solve_result(res)
        except Exception:
            return "", [], empty_usage_record()

        if env.feeling is not None:
            return env.feeling, trajectory, usage
        return "", trajectory, usage
