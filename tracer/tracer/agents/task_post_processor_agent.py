# Copyright Sierra

"""Agent that runs after the task generator to process or select generated tasks."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple, Type

from tracer.agents.chat_react_agent import ChatReActAgent
from tracer.envs.tool import Tool
from tracer.llm_utils import empty_usage_record, usage_record_from_solve_result
from tracer.prompts.task_preference_airline import (
    PREFERENCE_SYSTEM_PROMPT as DEFAULT_PREFERENCE_SYSTEM_PROMPT,
)
from tracer.prompts.task_preference_airline import (
    format_preference_user_prompt as default_format_preference_user_prompt,
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


class _PreferenceToolEnv:
    """Minimal env for ReAct-style tool use when rewriting instructions to preference form.
    Same tools and data as task generator; validates final output as JSON with preference_instruction (single combined string).
    """

    def __init__(
        self,
        data_load_func,
        tools: List[Type[Tool]],
        initial_observation: str,
        expected_num_instructions: int,
    ) -> None:
        self.data_load_func = data_load_func
        self.data = data_load_func()
        self.tools_map: Dict[str, Type[Tool]] = {
            tool.get_info()["function"]["name"]: tool for tool in tools
        }
        self.tools_info = [tool.get_info() for tool in tools]
        self.task = Task(
            user_id="preference",
            actions=[],
            instruction=initial_observation,
            outputs=[],
        )
        self.actions: List[Action] = []
        self._initial_observation = initial_observation
        self.expected_num_instructions = expected_num_instructions
        self.final_response: Optional[str] = None

    def reset(self, task_index: Optional[int] = None) -> EnvResetResponse:
        self.data = self.data_load_func()
        self.actions = []
        self.final_response = None
        return EnvResetResponse(
            observation=self._initial_observation,
            info=EnvInfo(task=self.task, source="preference"),
        )

    def _validate_final_output(self, content: str) -> Tuple[bool, str]:
        try:
            data = json.loads(content)
        except Exception as e:
            return False, f"Invalid JSON: {e}"
        if not isinstance(data, dict) or "preference_instruction" not in data:
            return (
                False,
                "JSON must contain key 'preference_instruction' (single combined string)",
            )
        pref = data["preference_instruction"]
        if not isinstance(pref, str):
            return False, "'preference_instruction' must be a string"
        if not pref.strip():
            return False, "'preference_instruction' must be non-empty"
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
                observation = "###DONE###"
                done = True
                info.source = "respond"
            else:
                observation = (
                    "Error: output must be ONLY a JSON object with key 'preference_instruction' "
                    "(one combined string). "
                    f"Validation error: {err}"
                )
                info.source = "respond_invalid"
        elif action.name in self.tools_map:
            try:
                observation = self.tools_map[action.name].invoke(
                    data=self.data, **action.kwargs
                )
            except Exception as e:
                observation = f"Error: {e}"
            info.source = action.name
        else:
            observation = f"Unknown action {action.name}"

        return EnvResponse(observation=observation, reward=0.0, done=done, info=info)


class TaskPostProcessorAgent:
    """Runs after the task generator. Processes or selects from generated task candidates.

    Default behavior: process() passes the candidate through unchanged; process_batch()
    selects the candidate with the highest reward when reward_result is available.
    Override or extend for custom logic (e.g. LLM refinement, filtering, scoring).
    """

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

    def process(
        self,
        candidate: GeneratedTaskCandidate,
        reward_result: Optional[Any] = None,
    ) -> GeneratedTaskCandidate:
        """Process a single candidate (e.g. refine, validate). Default: pass-through."""
        return candidate

    def add_preference_instructions(
        self,
        candidate: GeneratedTaskCandidate,
        data_load_func,
        tools: List[Type[Tool]],
        max_steps: int = 50,
        preference_system_prompt: Optional[str] = None,
        format_preference_user_prompt=None,
    ) -> Tuple[Optional[List[str]], List[Dict[str, Any]], Dict[str, Any]]:
        """Rewrite the candidate's instructions into preference form using the same tools as the generator.

        Uses tools to look up details (e.g. flight time, cabin; or order/product details for retail)
        and produces preference-style instructions when there are options. Does not modify the candidate.

        preference_system_prompt: optional domain-specific system prompt (default: airline).
        format_preference_user_prompt: optional function (story, instructions) -> str (default: airline).

        Returns:
            (preference_instructions list or None, trajectory messages, LLM usage record).
        """
        empty: Tuple[Optional[List[str]], List[Dict[str, Any]], Dict[str, Any]] = (
            None,
            [],
            empty_usage_record(),
        )
        if not candidate.instructions:
            return empty
        if self.model is None or self.provider is None:
            return empty

        system_prompt = (
            preference_system_prompt
            if preference_system_prompt is not None
            else DEFAULT_PREFERENCE_SYSTEM_PROMPT
        )
        format_fn = (
            format_preference_user_prompt
            if format_preference_user_prompt is not None
            else default_format_preference_user_prompt
        )
        initial_observation = format_fn(candidate.story or "", candidate.instructions)

        env = _PreferenceToolEnv(
            data_load_func=data_load_func,
            tools=tools,
            initial_observation=initial_observation,
            expected_num_instructions=len(candidate.instructions),
        )

        wiki = (
            system_prompt
            + "\n\nWhen you are ready to finish, use Action with name='respond' and arguments {\"content\": <JSON>}."
        )

        react_kwargs: Dict[str, Any] = {
            "tools_info": [t.get_info() for t in tools],
            "wiki": wiki,
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
            return empty

        if env.final_response is None:
            return (None, trajectory, usage)

        try:
            data = json.loads(env.final_response)
            combined = data.get("preference_instruction")
            if isinstance(combined, str) and combined.strip():
                # Return as list of one element for backward compatibility (preference_instructions)
                return ([combined.strip()], trajectory, usage)
        except Exception:
            pass
        return (None, trajectory, usage)
