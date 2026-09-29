"""Prompts for the solvability evaluator — Layer B (LLM fallback).

Layer B is only invoked when the existing `solvable` field is absent/null
and the `task_checker_action_replay` has no detectable errors, so the
deterministic layer could not produce a verdict.

The agent receives the instruction, ground-truth action list, and a
replay summary (if available) and decides whether the task is solvable.
"""

import json
from typing import Any, Dict, List, Optional

SYSTEM_PROMPT = """You are an evaluator that checks whether a generated customer-support task can be solved using the provided ground-truth action sequence.

You are given:
1. The task instruction.
2. The ground-truth action list (tool name + arguments).
3. A replay summary of those actions in the environment (if available).

Your job:
- Determine whether the ground-truth action sequence can plausibly complete the task.
- A task is SOLVABLE if all the tool calls in the ground-truth sequence are coherent, the required input parameters appear to be valid (no obvious placeholders, impossible values, or missing identifiers), and the sequence as a whole would accomplish the stated goal.
- A task is NOT SOLVABLE if: essential parameters are missing or clearly invalid; the action sequence does not match the stated goal; or the replay shows errors that indicate the task cannot be completed as stated.
- If the replay is unavailable, base your judgment solely on the instruction and action list.
- Return ONLY the JSON object below — no extra text.

Response JSON (required keys only):
- solvable (boolean): true if the task can be solved by the ground-truth actions
- reason (string): short (1–3 sentence) explanation

Do not output any other keys. Respond with valid JSON only."""


def format_user_prompt(
    instruction: str,
    ground_truth_actions: List[Dict[str, Any]],
    action_replay: Optional[List[Dict[str, Any]]] = None,
) -> str:
    parts = [f"Instruction:\n{instruction}"]
    parts.append(
        "\nGround-truth actions:\n" + json.dumps(ground_truth_actions, indent=2)
    )
    if action_replay:
        parts.append("\nReplay summary:\n" + json.dumps(action_replay, indent=2))
    return "\n".join(parts)
