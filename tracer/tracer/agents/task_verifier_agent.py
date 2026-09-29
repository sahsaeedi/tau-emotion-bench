# Copyright Sierra

"""Simple task verifier - just attempts to solve the task."""

from __future__ import annotations

from typing import Any, Dict, List

from tracer.agents.tool_calling_agent import ToolCallingAgent
from tracer.envs.base import Env
from tracer.envs.user import InstructionUserSimulationEnv
from tracer.types import (
    RESPOND_ACTION_NAME,
    Action,
    VerificationReport,
)


def _sanitize_temperature(model: str, temperature: float) -> float:
    """LiteLLM: gpt-5.* models only support temperature=1"""
    if model and model.startswith("gpt-5"):
        return 1.0
    return temperature


def _stop_seen(messages: List[Dict[str, Any]]) -> bool:
    """Check if ###STOP### appears in the transcript."""
    for m in messages:
        if (
            m.get("role") == "user"
            and isinstance(m.get("content"), str)
            and "###STOP###" in m["content"]
        ):
            return True
    return False


class TaskVerifierAgent:
    """Simple verifier that attempts to solve a task and reports results."""

    def __init__(
        self,
        model: str,
        provider: str,
        temperature: float = 0.0,
        max_steps: int = 30,
    ) -> None:
        self.model = model
        self.provider = provider
        self.temperature = _sanitize_temperature(model, temperature)
        self.max_steps = max_steps

    def verify(self, env: Env) -> VerificationReport:
        """Attempt to solve the task in the environment.

        Args:
            env: The task environment

        Returns:
            VerificationReport with results and transcript
        """

        # Build wiki instructions for multi-turn tasks
        wiki = env.wiki
        if isinstance(getattr(env, "user", None), InstructionUserSimulationEnv):
            wiki = (
                wiki
                + "\n\nImportant: you will receive multiple TURN instructions sequentially. "
                + "After completing the current turn, respond with EXACTLY 'NEXT_INSTRUCTION' to get the next turn. "
                + "After the final turn is complete, respond with '###STOP###' on its own line."
            )

        # Create the tool-calling agent
        agent = ToolCallingAgent(
            tools_info=getattr(env, "tools_info", []) or [],
            wiki=wiki,
            model=self.model,
            provider=self.provider,
            temperature=self.temperature,
        )

        tool_errors: List[Dict[str, Any]] = []
        unknown_actions: List[Dict[str, Any]] = []

        # Attempt to solve the task
        try:
            res = agent.solve(env=env, task_index=0, max_num_steps=self.max_steps)
        except Exception as e:
            return VerificationReport(
                solved=False,
                termination_reason="exception",
                stop_seen=False,
                max_steps_hit=False,
                tool_errors=[{"error": str(e)}],
                unknown_actions=[],
                critique=f"Verifier crashed: {e}",
                transcript=[],
                actions=[],
            )

        # Analyze the results
        stop_seen = _stop_seen(res.messages)
        max_steps_hit = not stop_seen

        # Collect tool errors from transcript
        for m in res.messages:
            if m.get("role") == "tool":
                content = m.get("content")
                if isinstance(content, str) and content.startswith("Error:"):
                    tool_errors.append({"tool": m.get("name"), "error": content})

        # Check for unknown actions (tools not in env)
        for a in getattr(env, "actions", []) or []:
            if a.name == RESPOND_ACTION_NAME:
                continue
            if hasattr(env, "tools_map") and a.name not in env.tools_map:
                unknown_actions.append({"name": a.name, "kwargs": a.kwargs})

        # Get actions taken (excluding respond)
        actions_taken: List[Action] = [
            a
            for a in (getattr(env, "actions", []) or [])
            if a.name != RESPOND_ACTION_NAME
        ]

        # Task is solved if:
        # - Agent finished with ###STOP###
        # - No tool errors occurred
        # - No unknown actions were attempted
        # - At least one tool action was taken
        solved = (
            stop_seen
            and len(tool_errors) == 0
            and len(unknown_actions) == 0
            and len(actions_taken) > 0
        )

        termination_reason = "stop_reached" if stop_seen else "max_steps"

        # Simple critique (detailed critique will be done by CritiqueAgent)
        if solved:
            critique = "Task solved successfully."
        else:
            critique = f"Task not solved (reason={termination_reason})"

        return VerificationReport(
            solved=solved,
            termination_reason=termination_reason,
            stop_seen=stop_seen,
            max_steps_hit=max_steps_hit,
            tool_errors=tool_errors,
            unknown_actions=unknown_actions,
            critique=critique,
            transcript=res.messages,
            actions=actions_taken,
        )
