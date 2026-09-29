# Prompts for the standalone feeling-generation pass (no tools, no domain wiki).

from __future__ import annotations

from typing import List

FEELING_SYSTEM_PROMPT = """You describe how the customer or patient feels and how they come across in conversation.

You are given only:
- a short domain label (for light context),
- the user identifier,
- a story,
- and the list of user instructions (what they want).

You do NOT have tools. Do not invent facts, IDs, or events that are not clearly implied by the story and instructions. Stay consistent with that text.

Write a single string value for the key "feeling":
- Use 2 or 3 full sentences (about 2–3 lines when printed).
- Be concrete and descriptive: mood, urgency, tone, and how they might phrase things.
- Second person is fine (e.g. "You feel ..." or "You come across as..." depending on domain).

When finished, respond using Action name='respond' with arguments {"content": <JSON object>} where the JSON object has exactly one key: "feeling" (a non-empty string). No other keys."""


def format_feeling_user_prompt(
    domain: str,
    user_id: str,
    story: str,
    instructions: List[str],
) -> str:
    inst_block = "\n".join(f"  {i + 1}. {line}" for i, line in enumerate(instructions))
    return f"""Domain: {domain}

User id: {user_id}

Story:
{story}

Instructions (one per turn):
{inst_block}

Return ONLY a JSON object with the single key "feeling", via the required respond action."""
