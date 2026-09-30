# Copyright Sierra

import json
from typing import Any, Dict, List, Optional, Tuple

from tracer.agents.base import Agent
from tracer.envs.base import Env
from tracer.llm_utils import (
    REACT_MAX_TOKENS,
    completion_usage_tokens,
    completion_with_retry,
)
from tracer.types import (
    RESPOND_ACTION_FIELD_NAME,
    RESPOND_ACTION_NAME,
    Action,
    SolveResult,
)


class ChatReActAgent(Agent):
    def __init__(
        self,
        tools_info: List[Dict[str, Any]],
        wiki: str,
        model: str,
        provider: str,
        use_reasoning: bool = True,
        temperature: float = 0.0,
        api_base: Optional[str] = None,
        max_tokens: Optional[int] = REACT_MAX_TOKENS,
    ) -> None:
        print(
            f"Initializing ChatReActAgent with model={model}, provider={provider}, use_reasoning={use_reasoning}, temperature={temperature}, api_base={api_base}"
        )
        instruction = REACT_INSTRUCTION if use_reasoning else ACT_INSTRUCTION
        self.prompt = (
            wiki + "\n#Available tools\n" + json.dumps(tools_info) + instruction
        )
        self.model = model
        self.provider = provider
        self.temperature = temperature
        self.use_reasoning = use_reasoning
        self.tools_info = tools_info
        self.api_base = api_base
        self.max_tokens = max_tokens

    def _extract_first_action(
        self, content: str
    ) -> Optional[Tuple[Dict[str, Any], int]]:
        """Best-effort extraction of the first valid Action JSON object from a ReAct-style message.

        Returns (action_dict, end_index) where end_index is the end position (exclusive)
        of the extracted JSON object in the original content. This lets us normalize the
        logged assistant message to the *single* step that will actually be executed.

        Handles cases where the model emits multiple Action blocks or adds extra text.
        """
        if "Action:" not in content:
            return None

        search_from = 0
        while True:
            action_idx = content.find("Action:", search_from)
            if action_idx == -1:
                return None

            start = content.find("{", action_idx)
            if start == -1:
                search_from = action_idx + len("Action:")
                continue

            depth = 0
            end: Optional[int] = None
            for j in range(start, len(content)):
                ch = content[j]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = j + 1
                        break

            if end is None:
                search_from = action_idx + len("Action:")
                continue

            candidate = content[start:end].strip()
            try:
                parsed = json.loads(candidate)
            except Exception:
                search_from = action_idx + len("Action:")
                continue

            if isinstance(parsed, dict):
                return parsed, end

            search_from = action_idx + len("Action:")

    def generate_next_step(
        self, messages: List[Dict[str, Any]]
    ) -> Tuple[
        Dict[str, Any], Action, float, Optional[int], Optional[int], Optional[int], bool
    ]:
        extra: Dict[str, Any] = {}
        if self.max_tokens:
            # A truncated reply still yields its first complete Action below.
            extra["max_tokens"] = self.max_tokens
        res = completion_with_retry(
            model=self.model,
            custom_llm_provider=self.provider,
            api_base=self.api_base,
            messages=messages,
            temperature=self.temperature,
            **extra,
        )
        message = res.choices[0].message
        content = message.content or ""

        cost = (getattr(res, "_hidden_params", None) or {}).get("response_cost") or 0.0
        p_use, c_use, t_use = completion_usage_tokens(res)
        step_usage_complete = t_use is not None

        def _finish(
            message_dict: Dict[str, Any], action: Action
        ) -> Tuple[
            Dict[str, Any],
            Action,
            float,
            Optional[int],
            Optional[int],
            Optional[int],
            bool,
        ]:
            return message_dict, action, cost, p_use, c_use, t_use, step_usage_complete

        action_info = self._extract_first_action(content) or self._extract_bare_action(
            content
        )
        if not action_info:
            action = Action(
                name=RESPOND_ACTION_NAME,
                kwargs={RESPOND_ACTION_FIELD_NAME: content.strip()},
            )
            return _finish(message.model_dump(), action)

        action_parsed, action_end = action_info
        # Normalize the logged content to the first executed Thought/Action block.
        message_dict = message.model_dump()
        message_dict["content"] = content[:action_end].strip()

        name = action_parsed.get("name")
        arguments = action_parsed.get("arguments")
        if not isinstance(name, str):
            action = Action(
                name=RESPOND_ACTION_NAME,
                kwargs={RESPOND_ACTION_FIELD_NAME: content.strip()},
            )
            return _finish(message_dict, action)
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except Exception:
                arguments = {}
        if not isinstance(arguments, dict):
            action = Action(
                name=RESPOND_ACTION_NAME,
                kwargs={RESPOND_ACTION_FIELD_NAME: content.strip()},
            )
            return _finish(message_dict, action)

        # Ensure respond content is always a string (APIs may return parsed dict)
        if name == RESPOND_ACTION_NAME and RESPOND_ACTION_FIELD_NAME in arguments:
            raw = arguments[RESPOND_ACTION_FIELD_NAME]
            if isinstance(raw, dict):
                arguments = {**arguments, RESPOND_ACTION_FIELD_NAME: json.dumps(raw)}

        action = Action(name=name, kwargs=arguments)
        return _finish(message_dict, action)

    @staticmethod
    def _extract_bare_action(content: str) -> Optional[Tuple[Dict[str, Any], int]]:
        """An action written without the "Action:" marker: the whole message is one JSON object
        with a string "name" and an "arguments" field (models often answer this way)."""
        text = content.strip()
        if not text.startswith("{"):
            return None
        try:
            parsed = json.loads(text)
        except Exception:
            return None
        if (
            isinstance(parsed, dict)
            and isinstance(parsed.get("name"), str)
            and "arguments" in parsed
        ):
            return parsed, len(content)
        return None

    def _extract_thought(self, content: str) -> Optional[str]:
        """Extract the Thought line(s) from ReAct-style content (between Thought: and Action:)."""
        if "Thought:" not in content or "Action:" not in content:
            return None
        start = content.find("Thought:") + len("Thought:")
        end = content.find("Action:", start)
        if end == -1:
            return None
        return content[start:end].strip() or None

    def solve(
        self,
        env: Env,
        task_index: Optional[int] = None,
        max_num_steps: int = 30,
        print_thoughts: bool = False,
    ) -> SolveResult:
        response = env.reset(task_index=task_index)
        reward = 0.0
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.prompt},
            {"role": "user", "content": response.observation},
        ]
        total_cost = 0.0
        sum_prompt = 0
        sum_completion = 0
        sum_total = 0
        usage_complete = True
        info = {}
        for step in range(max_num_steps):
            message, action, cost, p_u, c_u, t_u, step_ok = self.generate_next_step(
                messages
            )
            if not step_ok:
                usage_complete = False
            if p_u is not None:
                sum_prompt += p_u
            if c_u is not None:
                sum_completion += c_u
            if t_u is not None:
                sum_total += t_u
            if print_thoughts:
                content = (message.get("content") or "").strip()
                thought = self._extract_thought(content)
                if thought:
                    print(f"[Step {step + 1}] Thought: {thought}")
                if action.name == "think":
                    think_text = action.kwargs.get("thought", "")
                    if think_text:
                        print(f"[Step {step + 1}] Think tool: {think_text}")
            response = env.step(action)
            obs = response.observation
            # Always-on compact progress line: a task takes many LLM steps and the
            # output file is written only per trace, so this is the only way to see
            # what a run is doing before it finishes (tail the per-domain log).
            _kw = json.dumps(action.kwargs, ensure_ascii=False)
            print(
                f"[Step {step + 1}] {action.name}({_kw[:160]}{'...' if len(_kw) > 160 else ''})"
                f" -> {str(obs)[:160].replace(chr(10), ' ')}{'...' if len(str(obs)) > 160 else ''}"
            )
            reward = response.reward
            info = {**info, **response.info.model_dump()}
            if action.name != RESPOND_ACTION_NAME:
                obs = "API output: " + obs
            messages.extend(
                [
                    message,
                    {"role": "user", "content": obs},
                ]
            )
            total_cost += cost
            if response.done:
                break
        return SolveResult(
            messages=messages,
            reward=reward,
            info=info,
            total_cost=total_cost,
            usage_prompt_tokens=sum_prompt if usage_complete else None,
            usage_completion_tokens=sum_completion if usage_complete else None,
            usage_total_tokens=sum_total if usage_complete else None,
            usage_complete=usage_complete,
        )


REACT_INSTRUCTION = f"""
# Instruction
You need to act as an agent that use the above tools to help the user according to the above policy.

At each step, your generation should have exactly the following format:
Thought:
<A single line of reasoning to process the context and inform the decision making. Do not include extra lines.>
Action:
{{"name": <The name of the action>, "arguments": <The arguments to the action in json format>}}

The Action will be parsed, so it must be valid JSON.

You should not use made-up or placeholder arguments.

For example, if the user says "I want to know the current weather of San Francisco", and there is such a tool available
{{
    "type": "function",
    "function": {{
        "name": "get_current_weather",
        "description": "Get the current weather",
        "parameters": {{
            "type": "object",
            "properties": {{
                "location": {{
                    "type": "string",
                    "description": "The city and state, e.g. San Francisco, CA",
                }},
                "format": {{
                    "type": "string",
                    "enum": ["celsius", "fahrenheit"],
                    "description": "The temperature unit to use. Infer this from the users location.",
                }},
            }},
            "required": ["location", "format"],
        }},
    }}
}}

Your response can be like this:
Thought:
Since the user asks for the weather of San Francisco in USA, the unit should be in fahrenheit. I can query get_current_weather to get the weather.
Action:
{{"name": "get_current_weather", "arguments": {{"location": "San Francisco, CA", "format": "fahrenheit"}}}}

And if the tool returns "70F", your response can be:
Thought:
I can answer the user now.
Action:
{{"name": {RESPOND_ACTION_NAME}, "arguments": {{"{RESPOND_ACTION_FIELD_NAME}": "The current weather of San Francisco is 70F."}}}}

Try to be helpful and always follow the policy.
"""


ACT_INSTRUCTION = f"""
# Instruction
You need to act as an agent that use the above tools to help the user according to the above policy.

At each step, your generation should have exactly the following format:

Action:
{{"name": <The name of the action>, "arguments": <The arguments to the action in json format>}}

You should not use made-up or placeholder arguments.

The Action will be parsed, so it must be valid JSON.

For example, if the user says "I want to know the current weather of San Francisco", and there is such a tool available
```json
{{
    "type": "function",
    "function": {{
        "name": "get_current_weather",
        "description": "Get the current weather",
        "parameters": {{
            "type": "object",
            "properties": {{
                "location": {{
                    "type": "string",
                    "description": "The city and state, e.g. San Francisco, CA",
                }},
                "format": {{
                    "type": "string",
                    "enum": ["celsius", "fahrenheit"],
                    "description": "The temperature unit to use. Infer this from the users location.",
                }},
            }},
            "required": ["location", "format"],
        }},
    }}
}}
```

Your response can be like this:
Action:
{{"name": "get_current_weather", "arguments": {{"location": "San Francisco, CA", "format": "fahrenheit"}}}}

And if the tool returns "70F", your response can be:
Action:
{{"name": {RESPOND_ACTION_NAME}, "arguments": {{"{RESPOND_ACTION_FIELD_NAME}": "The current weather of San Francisco is 70F."}}}}

Try to be helpful and always follow the policy. Always make sure you generate valid JSON only.
"""
