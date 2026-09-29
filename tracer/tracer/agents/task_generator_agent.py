# Copyright Sierra

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple, Type

from tracer.agents.chat_react_agent import ChatReActAgent
from tracer.envs.tool import Tool
from tracer.llm_utils import usage_record_from_solve_result
from tracer.prompts.task_generator_airline import SYSTEM_PROMPT as AIRLINE_SYSTEM_PROMPT
from tracer.prompts.task_generator_airline import USER_PROMPT as AIRLINE_USER_PROMPT
from tracer.types import (
    RESPOND_ACTION_FIELD_NAME,
    RESPOND_ACTION_NAME,
    Action,
    EnvInfo,
    EnvResetResponse,
    EnvResponse,
    GeneratedTaskCandidate,
    Task,
    TracerAgentOutput,
)


def _sanitize_temperature(model: str, temperature: float) -> float:
    # LiteLLM: gpt-5.* models only support temperature=1
    if model and model.startswith("gpt-5"):
        return 1.0
    return temperature


def _looks_like_invalid_prompt_error(e: Exception) -> bool:
    msg = str(e).lower()
    return "invalid prompt" in msg or "invalid_prompt" in msg or "flagged" in msg


def _sanitize_generator_prompt(p: str) -> str:
    # Avoid wording that may trigger policy filters.
    return (
        p.replace("reverse engineer", "infer")
        .replace("reverse-engineer", "infer")
        .replace("reverse engineering", "inference")
    )


def _normalize_trace_to_turns(trace: Any) -> List[List[Dict[str, Any]]]:
    # Expected: [[TURN1],[TURN2],...], but allow a single TURN too.
    if not isinstance(trace, list) or len(trace) == 0:
        return []
    if all(isinstance(x, list) for x in trace):
        return [
            [n for n in t if isinstance(n, dict)] for t in trace if isinstance(t, list)
        ]
    if all(isinstance(x, dict) for x in trace):
        return [trace]
    return []


def _required_params_by_turn(trace: Any) -> List[List[str]]:
    turns = _normalize_trace_to_turns(trace)
    out: List[List[str]] = []
    for t in turns:
        req: List[str] = []
        seen = set()
        for node in t:
            info = node.get("info") if isinstance(node, dict) else None
            fn = info.get("function") if isinstance(info, dict) else None
            params = fn.get("parameters") if isinstance(fn, dict) else None
            required = params.get("required") if isinstance(params, dict) else None
            if isinstance(required, list):
                for r in required:
                    if isinstance(r, str) and r and r not in seen:
                        seen.add(r)
                        req.append(r)
        out.append(req)
    return out


def _format_requirements_summary(trace: Any) -> str:
    turns = _normalize_trace_to_turns(trace)
    by_turn = _required_params_by_turn(trace)

    summary: List[Dict[str, Any]] = []
    for i, t in enumerate(turns):
        tools: List[str] = []
        for node in t:
            info = node.get("info") if isinstance(node, dict) else None
            fn = info.get("function") if isinstance(info, dict) else None
            name = fn.get("name") if isinstance(fn, dict) else None
            if isinstance(name, str) and name:
                tools.append(name)
        summary.append(
            {
                "turn": i,
                "tools": tools,
                "required_params": by_turn[i] if i < len(by_turn) else [],
            }
        )

    return json.dumps(summary, indent=2)


def _normalize_respond_content(content: Any) -> str:
    """Ensure respond content is a string suitable for JSON validation.

    - If content is already a dict (e.g. from API-parsed JSON), serialize it.
    - If content is a string that wraps Thought/Action around the real JSON,
      extract the inner respond 'content' from the Action block.
    """
    if isinstance(content, dict):
        return json.dumps(content)
    if not isinstance(content, str):
        return str(content)
    s = content.strip()
    # Try parsing as-is (valid TracerAgentOutput JSON)
    try:
        json.loads(s)
        return s
    except Exception:
        pass
    # Try to extract Action block with name=respond and use its arguments.content
    if "Action:" in s:
        start = s.find("Action:")
        brace = s.find("{", start)
        if brace != -1:
            depth = 0
            for i in range(brace, len(s)):
                if s[i] == "{":
                    depth += 1
                elif s[i] == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            action_obj = json.loads(s[brace : i + 1])
                            if (
                                isinstance(action_obj, dict)
                                and action_obj.get("name") == RESPOND_ACTION_NAME
                            ):
                                args = action_obj.get("arguments")
                                if isinstance(args, dict):
                                    inner = args.get(RESPOND_ACTION_FIELD_NAME)
                                elif isinstance(args, str):
                                    try:
                                        args = json.loads(args)
                                        inner = (
                                            args.get(RESPOND_ACTION_FIELD_NAME)
                                            if isinstance(args, dict)
                                            else None
                                        )
                                    except Exception:
                                        inner = None
                                else:
                                    inner = None
                                if inner is not None:
                                    return (
                                        json.dumps(inner)
                                        if isinstance(inner, dict)
                                        else str(inner)
                                    )
                        except Exception:
                            pass
                        break
    return s


class _ReActToolEnv:
    """Minimal env for ReAct-style tool use during task generation.

    - No user simulator
    - One action per step
    - Tool actions call reverse tools against an in-memory dataset
    - respond ends the episode only if output JSON passes validation
    """

    def __init__(
        self,
        data_load_func,
        tools: List[Type[Tool]],
        initial_observation: str,
        trace: Any,
    ) -> None:
        self.data_load_func = data_load_func
        self.data = data_load_func()
        self.tools_map: Dict[str, Type[Tool]] = {
            tool.get_info()["function"]["name"]: tool for tool in tools
        }
        self.tools_info = [tool.get_info() for tool in tools]
        self.wiki = ""
        self.task = Task(
            user_id="generated", actions=[], instruction=initial_observation, outputs=[]
        )
        self.actions = []
        self.tool_history: List[Dict[str, Any]] = []
        self._initial_observation = initial_observation
        self.final_response: Optional[str] = None
        self.trace = trace
        self.expected_num_turns = len(_normalize_trace_to_turns(trace))

    def reset(self, task_index: Optional[int] = None) -> EnvResetResponse:
        self.data = self.data_load_func()
        self.actions = []
        self.tool_history = []
        self.final_response = None
        return EnvResetResponse(
            observation=self._initial_observation,
            info=EnvInfo(task=self.task, source="generator"),
        )

    def _validate_final_output(self, content: str) -> Tuple[bool, str]:
        """Minimal validation.

        We intentionally avoid heuristic/policy/grounding validation here.
        The verifier is responsible for deciding whether the generated task is actually doable.
        """

        try:
            data = json.loads(content)
        except Exception as e:
            return False, f"Invalid JSON: {e}"

        try:
            parsed = TracerAgentOutput.model_validate(data)
        except Exception as e:
            return False, f"JSON does not match schema: {e}"

        if self.expected_num_turns == 0:
            return False, "Trace format invalid: expected a list of TURNs."

        if len(parsed.instructions) != self.expected_num_turns:
            return (
                False,
                f"instructions length {len(parsed.instructions)} must equal number of TURNs {self.expected_num_turns}.",
            )

        return True, ""

    def step(self, action) -> EnvResponse:
        self.actions.append(action)
        done = False
        observation = ""
        info = EnvInfo(task=self.task, source=action.name)

        if action.name == RESPOND_ACTION_NAME:
            raw_content = action.kwargs.get(RESPOND_ACTION_FIELD_NAME, "")
            content = _normalize_respond_content(raw_content)
            ok, err = self._validate_final_output(content)
            if ok:
                self.final_response = content
                observation = "###DONE###"
                done = True
                info.source = "respond"
            else:
                observation = (
                    "Error: invalid final output. Use respond with content set to ONLY a JSON object "
                    "matching TracerAgentOutput: {user_id, instructions, story, actions}. "
                    f"Validation error: {err}"
                )
                done = False
                info.source = "respond_invalid"
        elif action.name in self.tools_map:
            try:
                observation = self.tools_map[action.name].invoke(
                    data=self.data, **action.kwargs
                )
            except Exception as e:
                observation = f"Error: {e}"
            self.tool_history.append(
                {
                    "name": action.name,
                    "kwargs": action.kwargs,
                    "observation": observation,
                }
            )
        else:
            observation = f"Unknown action {action.name}"

        return EnvResponse(observation=observation, reward=0.0, done=done, info=info)


class TraceTaskGeneratorAgent:
    """ReAct-style generator agent (Thought -> Action -> Observation)."""

    def __init__(
        self,
        tools: List[Type[Tool]],
        data_load_func,
        model: str,
        provider: str,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
        temperature: float = 0.2,
        max_steps: int = 200,
        max_parse_attempts: int = 3,
        api_base: Optional[str] = None,
        print_thoughts: bool = False,
    ) -> None:
        self.tools = tools
        self.data_load_func = data_load_func
        self.model = model
        self.provider = provider
        self.temperature = _sanitize_temperature(model, temperature)
        self.max_steps = max_steps
        self.max_parse_attempts = max_parse_attempts
        self.print_thoughts = print_thoughts

        system_prompt_final = (
            system_prompt if system_prompt is not None else AIRLINE_SYSTEM_PROMPT
        )
        user_prompt_final = (
            user_prompt if user_prompt is not None else AIRLINE_USER_PROMPT
        )
        self._user_prompt_template = user_prompt_final

        generator_wiki = (
            system_prompt_final
            + "\n\nWhen you are ready to finish, use Action with name='respond' and arguments {\"content\": <JSON>}."
            + "\nThat JSON MUST match TracerAgentOutput exactly: {user_id, instructions, story, actions}."
            + "\nDo not include any text outside the JSON."
        )

        react_kwargs: Dict[str, Any] = {
            "tools_info": [tool.get_info() for tool in tools],
            "wiki": generator_wiki,
            "model": model,
            "provider": provider,
            "use_reasoning": True,
            "temperature": self.temperature,
        }
        if api_base is not None:
            react_kwargs["api_base"] = api_base
        self._react_agent = ChatReActAgent(**react_kwargs)

    def generate(
        self,
        trace: Any,
        attempt: int = 0,
        verifier_feedback: Optional[str] = None,
    ) -> Tuple[
        GeneratedTaskCandidate,
        List[Dict[str, Any]],
        List[Dict[str, Any]],
        List[Dict[str, Any]],
        Dict[str, Any],
    ]:
        feedback = verifier_feedback or ""
        requirements = _format_requirements_summary(trace)

        user_prompt = self._user_prompt_template.format(
            trace=json.dumps(trace, indent=2), feedback=feedback
        )
        user_prompt += (
            "\n\nREQUIREMENTS_SUMMARY (must satisfy these):\n"
            + requirements
            + "\n\nRemember: instructions[i] must contain ALL required params for TURN i with dataset-grounded values (use reverse tools)."
        )

        sanitized_user_prompt = user_prompt

        env = _ReActToolEnv(
            data_load_func=self.data_load_func,
            tools=self.tools,
            initial_observation=sanitized_user_prompt,
            trace=trace,
        )

        try:
            res = self._react_agent.solve(
                env=env,
                task_index=0,
                max_num_steps=self.max_steps,
                print_thoughts=self.print_thoughts,
            )
        except Exception as e:
            if _looks_like_invalid_prompt_error(e):
                sanitized_user_prompt = _sanitize_generator_prompt(
                    sanitized_user_prompt
                )
                env = _ReActToolEnv(
                    data_load_func=self.data_load_func,
                    tools=self.tools,
                    initial_observation=sanitized_user_prompt,
                    trace=trace,
                )
                res = self._react_agent.solve(
                    env=env,
                    task_index=0,
                    max_num_steps=self.max_steps,
                    print_thoughts=self.print_thoughts,
                )
            else:
                raise

        if env.final_response is None:
            raise ValueError("Generator did not produce a final respond action.")

        candidate = self._parse_candidate(
            env.final_response,
            trace=trace,
            attempt=attempt,
            verifier_feedback=verifier_feedback,
        )
        generator_tool_actions = [
            a.model_dump()
            for a in (getattr(env, "actions", []) or [])
            if a.name != RESPOND_ACTION_NAME
        ]
        generator_tool_history = getattr(env, "tool_history", []) or []
        return (
            candidate,
            res.messages,
            generator_tool_actions,
            generator_tool_history,
            usage_record_from_solve_result(res),
        )

    def _parse_candidate(
        self,
        content: str,
        trace: Any,
        attempt: int,
        verifier_feedback: Optional[str],
    ) -> GeneratedTaskCandidate:
        last_err: Optional[str] = None
        cur = content.strip()

        for _ in range(self.max_parse_attempts):
            try:
                data = json.loads(cur)
                parsed = TracerAgentOutput.model_validate(data)
                actions = [Action.model_validate(a) for a in (parsed.actions or [])]
                return GeneratedTaskCandidate(
                    user_id=parsed.user_id,
                    instructions=parsed.instructions,
                    story=parsed.story,
                    feeling="",
                    action_trace=trace,
                    actions=actions,
                    attempt=attempt,
                    verifier_feedback=verifier_feedback,
                )
            except Exception as e:
                last_err = str(e)
                cur = cur.strip()
                if cur.startswith("```"):
                    cur = cur.strip("`")

        raise ValueError(
            f"Failed to parse generator JSON: {last_err}; content={content[:500]}"
        )
