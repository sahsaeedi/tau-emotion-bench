# Copyright Sierra

"""Critique agent that analyzes failed task attempts and provides feedback."""

from __future__ import annotations

from typing import Any, Dict, List

from tracer.llm_utils import completion_with_retry


def _sanitize_temperature(model: str, temperature: float) -> float:
    """LiteLLM: gpt-5.* models only support temperature=1"""
    if model and model.startswith("gpt-5"):
        return 1.0
    return temperature


CRITIQUE_SYSTEM_PROMPT = """You are an expert task evaluation agent for airline customer service scenarios.

Your job is to analyze a conversation transcript where an AI agent attempted to solve a customer's task but failed.

Analyze the transcript and identify:
1. What information was MISSING from the user's instruction that the agent needed
2. What parameters or details were not provided upfront
3. What clarifications the agent had to ask for (that should have been in the instruction)
4. What tool calls failed due to missing inputs
5. Whether the instruction violated any airline policies

Provide concrete, actionable feedback for improving the instruction.

Focus on:
- Missing IDs (user_id, reservation_id, flight_number, payment_id, etc.)
- Missing dates, locations, or other required parameters
- Ambiguous or unclear requests
- Policy violations (e.g., requesting actions not allowed by airline rules)
- Missing confirmation for destructive actions

Be specific about what needs to be added or changed."""


def _build_critique_prompt(
    instruction: str,
    transcript: List[Dict[str, Any]],
    tool_errors: List[Dict[str, Any]],
) -> str:
    """Build the prompt for the critique agent."""

    # Format transcript for readability
    transcript_text = []
    for msg in transcript:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")

        if role == "user":
            transcript_text.append(f"USER: {content}")
        elif role == "assistant":
            # Only show text content, skip tool calls in display
            if isinstance(content, str):
                transcript_text.append(f"AGENT: {content}")
        elif role == "tool":
            tool_name = msg.get("name", "unknown")
            transcript_text.append(f"TOOL[{tool_name}]: {content}")

    transcript_str = "\n".join(transcript_text)

    # Format tool errors
    errors_str = ""
    if tool_errors:
        errors_str = "\n\nTOOL ERRORS:\n"
        for err in tool_errors:
            tool = err.get("tool", "unknown")
            error = err.get("error", "")
            errors_str += f"- {tool}: {error}\n"

    prompt = f"""ORIGINAL INSTRUCTION:
{instruction}

CONVERSATION TRANSCRIPT:
{transcript_str}
{errors_str}

Analyze why the task failed and provide specific feedback on what needs to be added or changed in the instruction to make it solvable.

Your feedback should be:
- Concrete and actionable
- Specific about missing information
- Clear about what to add to the instruction

Format your response as a clear paragraph of feedback that will be sent back to the task generator."""

    return prompt


class TaskCritiqueAgent:
    """Agent that analyzes failed verification attempts and provides feedback."""

    def __init__(
        self,
        model: str = "gpt-4o",
        provider: str = "openai",
        temperature: float = 0.3,
    ):
        self.model = model
        self.provider = provider
        self.temperature = _sanitize_temperature(model, temperature)

    def critique(
        self,
        instruction: str,
        transcript: List[Dict[str, Any]],
        tool_errors: List[Dict[str, Any]],
        stop_seen: bool,
    ) -> str:
        """Analyze a failed task attempt and provide feedback.

        Args:
            instruction: The original user instruction
            transcript: Full conversation transcript
            tool_errors: List of tool errors that occurred
            stop_seen: Whether the agent completed with ###STOP###

        Returns:
            Feedback string to send to the generator
        """

        # Quick checks for obvious issues
        if not stop_seen and len(tool_errors) == 0:
            return (
                "The agent did not complete the task. The instruction may be too complex, "
                "unclear, or require information not provided. Consider breaking it into "
                "clearer steps or adding more specific details."
            )

        if len(tool_errors) > 0:
            first_error = tool_errors[0]
            error_msg = first_error.get("error", "")

            # Check for missing parameters
            if "missing" in error_msg.lower() or "required" in error_msg.lower():
                return (
                    f"Tool call failed due to missing required information. "
                    f"Error: {error_msg}. "
                    "Add all required parameters explicitly in the instruction with concrete values."
                )

        # Use LLM to analyze the transcript
        try:
            critique_prompt = _build_critique_prompt(
                instruction=instruction,
                transcript=transcript,
                tool_errors=tool_errors,
            )

            messages = [
                {"role": "system", "content": CRITIQUE_SYSTEM_PROMPT},
                {"role": "user", "content": critique_prompt},
            ]

            response = completion_with_retry(
                model=f"{self.provider}/{self.model}",
                messages=messages,
                temperature=self.temperature,
                max_tokens=500,
            )

            feedback = response.choices[0].message.content.strip()
            return feedback

        except Exception as e:
            # Fallback to simple feedback
            return (
                f"Task verification failed. Error during critique: {e}. "
                "Review the instruction to ensure all required information is provided."
            )
