"""Agent that checks whether a generated task is valid, in-domain, and solvable.

The ground-truth actions are replayed first on the environment. A final LLM pass then
classifies the task from that execution summary without calling any tools.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from tracer.agents.chat_react_agent import ChatReActAgent
from tracer.llm_utils import empty_usage_record, usage_record_from_solve_result
from tracer.prompts.in_domain_checker import (
    SYSTEM_PROMPTS_BY_DOMAIN,
    format_in_domain_checker_user_prompt,
)
from tracer.types import (
    RESPOND_ACTION_FIELD_NAME,
    RESPOND_ACTION_NAME,
    Action,
    EnvInfo,
    EnvResetResponse,
    EnvResponse,
    Task,
)


def _observation_indicates_error(
    domain: str, tool_name: str, observation: Any
) -> Tuple[bool, Optional[str]]:
    if observation is None:
        return True, "No observation returned"
    if not isinstance(observation, str):
        return False, None

    text = observation.strip()
    if not text:
        return False, None
    if text.startswith("Error:"):
        return True, text

    lower = text.lower()
    if domain == "telecom":
        telecom_error_markers = (
            "unknown issue",
            "customer not found",
            "service not found",
            "device not found",
            "billing information found",
            "no customer found",
            "invalid action",
            "amount must be a number",
            "not have service",
            "already has service",
        )
        if any(marker in lower for marker in telecom_error_markers):
            return True, text

    if domain == "telehealth":
        telehealth_error_markers = (
            "no patient found",
            "not found.",
            "not found:",
            "cannot cancel",
            "cannot reschedule",
            "invalid date format",
            "does not work on",
            "is not available at",
            "already has an appointment scheduled",
            "no providers found",
            "no appointments found",
            "no medical records found",
        )
        if any(marker in lower for marker in telehealth_error_markers):
            return True, text

    return False, None


def _normalize_actions(
    ground_truth_actions: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    actions_for_prompt: List[Dict[str, Any]] = []
    for action in ground_truth_actions:
        if isinstance(action, dict):
            actions_for_prompt.append(
                {
                    "name": action.get("name", action.get("tool", "")),
                    "kwargs": action.get("kwargs", action.get("arguments", {})),
                }
            )
        else:
            actions_for_prompt.append(
                {
                    "name": getattr(action, "name", ""),
                    "kwargs": getattr(action, "kwargs", {}),
                }
            )
    return actions_for_prompt


def _replay_ground_truth_actions(
    domain: str, env, ground_truth_actions: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    replay: List[Dict[str, Any]] = []
    env.reset(task_index=0)

    for idx, action_dict in enumerate(_normalize_actions(ground_truth_actions)):
        name = action_dict.get("name", "")
        kwargs = action_dict.get("kwargs", {})
        before_hash = env.get_data_hash()
        error: Optional[str] = None
        observation: Optional[str] = None

        if name not in getattr(env, "tools_map", {}):
            error = f"Unknown action {name}"
            after_hash = before_hash
        else:
            try:
                observation = env.tools_map[name].invoke(data=env.data, **kwargs)
                is_error, detected_error = _observation_indicates_error(
                    domain, name, observation
                )
                if is_error:
                    error = detected_error
                # Tool-specific exception: in telehealth, missing telemetry uploads can be an expected outcome.
                if (
                    domain == "telehealth"
                    and name == "get_telemetry_upload"
                    and isinstance(observation, str)
                    and observation.strip()
                    .lower()
                    .startswith("no telemetry upload found")
                ):
                    error = None
                if (
                    domain == "telehealth"
                    and name == "list_telemetry_uploads"
                    and isinstance(observation, str)
                    and observation.strip()
                    .lower()
                    .startswith("no telemetry uploads found")
                ):
                    error = None
            except Exception as exc:
                error = f"Error: {exc}"
                observation = error
            after_hash = env.get_data_hash()

        replay.append(
            {
                "step": idx,
                "name": name,
                "kwargs": kwargs,
                "data_changed": before_hash != after_hash,
                "error": error,
                "observation": observation,
            }
        )

    return replay


def _empty_analysis() -> Dict[str, Any]:
    return {
        "solvable": None,
        "not_solvable": None,
        "solvable_reason": None,
        "difficulty": None,
        "difficulty_reason": None,
        "in_domain": None,
        "in_domain_reason": None,
        "trajectory": [],
        "action_replay": [],
        "llm_usage": empty_usage_record(),
    }


def _has_replay_errors(action_replay: List[Dict[str, Any]]) -> bool:
    return any(bool(step.get("error")) for step in action_replay)


class _InDomainCheckerEnv:
    """Minimal env for the final classification pass."""

    def __init__(
        self,
        initial_observation: str,
    ) -> None:
        self.task = Task(
            user_id="in_domain_checker",
            actions=[],
            instruction=initial_observation,
            outputs=[],
        )
        self.actions: List[Action] = []
        self._initial_observation = initial_observation
        self.final_response: Optional[str] = None
        self.in_domain: Optional[bool] = None
        self.in_domain_reason: Optional[str] = None
        self.solvable: Optional[bool] = None
        self.not_solvable: Optional[str] = None
        self.solvable_reason: Optional[str] = None
        self.difficulty: Optional[str] = None
        self.difficulty_reason: Optional[str] = None

    def reset(self, task_index: Optional[int] = None) -> EnvResetResponse:
        self.actions = []
        self.final_response = None
        self.in_domain = None
        self.in_domain_reason = None
        self.solvable = None
        self.not_solvable = None
        self.solvable_reason = None
        self.difficulty = None
        self.difficulty_reason = None
        return EnvResetResponse(
            observation=self._initial_observation,
            info=EnvInfo(task=self.task, source="in_domain_checker"),
        )

    def _validate_final_output(self, content: str) -> Tuple[bool, str]:
        try:
            data = json.loads(content)
        except Exception as e:
            return False, f"Invalid JSON: {e}"
        if not isinstance(data, dict):
            return False, "Output must be a JSON object"
        if set(data.keys()) != {
            "in_domain",
            "in_domain_reason",
            "solvable",
            "not_solvable",
            "solvable_reason",
            "difficulty",
            "difficulty_reason",
        }:
            return (
                False,
                "JSON must contain only 'in_domain', 'in_domain_reason', 'solvable', 'not_solvable', 'solvable_reason', 'difficulty', and 'difficulty_reason'",
            )
        if not isinstance(data["in_domain"], bool):
            return False, "'in_domain' must be a boolean"
        if (
            not isinstance(data["in_domain_reason"], str)
            or not data["in_domain_reason"].strip()
        ):
            return False, "'in_domain_reason' must be a non-empty string"
        if not isinstance(data["solvable"], bool):
            return False, "'solvable' must be a boolean"
        if data["not_solvable"] is not None and data["not_solvable"] not in {
            "out_doamin",
            "malformed",
        }:
            return False, "'not_solvable' must be null, 'out_doamin', or 'malformed'"
        if (
            not isinstance(data["solvable_reason"], str)
            or not data["solvable_reason"].strip()
        ):
            return False, "'solvable_reason' must be a non-empty string"
        if data["difficulty"] not in {"easy", "medium", "hard"}:
            return False, "'difficulty' must be one of 'easy', 'medium', or 'hard'"
        if (
            not isinstance(data["difficulty_reason"], str)
            or not data["difficulty_reason"].strip()
        ):
            return False, "'difficulty_reason' must be a non-empty string"
        if data["solvable"] and data["not_solvable"] is not None:
            return False, "'not_solvable' must be null when 'solvable' is true"
        if (not data["solvable"]) and data["not_solvable"] is None:
            return False, "'not_solvable' must be set when 'solvable' is false"
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
                self.in_domain = data["in_domain"]
                self.in_domain_reason = data["in_domain_reason"]
                self.solvable = data["solvable"]
                self.not_solvable = data["not_solvable"]
                self.solvable_reason = data["solvable_reason"]
                self.difficulty = data["difficulty"]
                self.difficulty_reason = data["difficulty_reason"]
                observation = "###DONE###"
                done = True
                info.source = "respond"
            else:
                observation = (
                    "Error: output must be ONLY a JSON object with 'in_domain' (boolean), "
                    "'in_domain_reason' (string), 'solvable' (boolean), "
                    "'not_solvable' (null/'out_doamin'/'malformed'), "
                    "'solvable_reason' (string), 'difficulty' ('easy'/'medium'/'hard'), "
                    "and 'difficulty_reason' (string). "
                    f"Validation error: {err}"
                )
                info.source = "respond_invalid"
        else:
            observation = f"Unknown action {action.name}"

        return EnvResponse(observation=observation, reward=0.0, done=done, info=info)


class InDomainCheckerAgent:
    """Runs after the task generator and preference agent."""

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

    def check_in_domain(
        self,
        domain: str,
        env,
        instruction: str,
        ground_truth_actions: List[Dict[str, Any]],
        preferred_output: Optional[List[str]] = None,
        num_instructions: Optional[int] = None,
        max_steps: int = 12,
    ) -> Dict[str, Any]:
        """Replay the task actions, then classify the task from that summary."""
        del num_instructions  # kept for backward compatibility with older callers
        empty = _empty_analysis()
        if self.model is None or self.provider is None:
            return empty
        if domain not in SYSTEM_PROMPTS_BY_DOMAIN:
            return empty

        preferred = preferred_output if preferred_output is not None else []
        action_replay = _replay_ground_truth_actions(domain, env, ground_truth_actions)

        initial_observation = format_in_domain_checker_user_prompt(
            instruction=instruction,
            action_replay=action_replay,
            preferred_output=preferred,
        )

        env = _InDomainCheckerEnv(
            initial_observation=initial_observation,
        )

        system_prompt = SYSTEM_PROMPTS_BY_DOMAIN[domain] + (
            "\n\nWhen you are ready to finish, use Action with name='respond' and arguments "
            + '{"content": <JSON with in_domain, in_domain_reason, solvable, not_solvable, solvable_reason, difficulty, difficulty_reason>}.'
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
            llm_usage = usage_record_from_solve_result(res)
        except Exception:
            out = _empty_analysis()
            out["action_replay"] = action_replay
            return out

        if (
            env.in_domain is not None
            and env.in_domain_reason is not None
            and env.solvable is not None
            and env.solvable_reason is not None
            and env.difficulty is not None
            and env.difficulty_reason is not None
        ):
            # Deterministic solvability guardrail:
            # if any replayed ground-truth step errored, force solvable=false.
            replay_has_error = _has_replay_errors(action_replay)
            solvable = env.solvable
            not_solvable = env.not_solvable
            solvable_reason = env.solvable_reason
            if replay_has_error:
                solvable = False
                if not_solvable is None:
                    not_solvable = "malformed"
                if solvable_reason:
                    solvable_reason = (
                        f"{solvable_reason} "
                        "[Deterministic override: replay contains tool execution errors.]"
                    )
                else:
                    solvable_reason = (
                        "Deterministic override: replay contains tool execution errors."
                    )

            return {
                "in_domain": env.in_domain,
                "in_domain_reason": env.in_domain_reason,
                "solvable": solvable,
                "not_solvable": not_solvable,
                "solvable_reason": solvable_reason,
                "difficulty": env.difficulty,
                "difficulty_reason": env.difficulty_reason,
                "trajectory": trajectory,
                "action_replay": action_replay,
                "llm_usage": llm_usage,
            }

        out = _empty_analysis()
        out["trajectory"] = trajectory
        out["action_replay"] = action_replay
        out["llm_usage"] = llm_usage
        return out
