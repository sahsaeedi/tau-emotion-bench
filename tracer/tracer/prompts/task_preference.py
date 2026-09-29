from typing import List

from tracer.prompts.task_preference_common import (
    COMMON_SYSTEM_PROMPT_CORE,
    build_system_prompt,
    build_user_prompt_intro,
)

PREFERENCE_SYSTEM_PROMPT = build_system_prompt(
    "You are an agent that rewrites user instructions into PREFERENCE form.",
    COMMON_SYSTEM_PROMPT_CORE,
    """Generic grounding guidance:
- Use the same lookup tools as the generator to resolve concrete IDs and attributes before rewriting.
- Convert concrete references into customer-facing preferences whenever meaningful options exist (e.g. time of day, plan tier, size, scheduling window).
- Keep the final response as one coherent preference narrative.""",
)

PREFERENCE_USER_PROMPT_INTRO = build_user_prompt_intro(
    "Rewrite the following user instructions into PREFERENCE form.",
    "Use available tools to ground concrete IDs and attributes before composing the preference narrative in second-person style that starts with 'You are ...'.",
)


def format_preference_user_prompt(story: str, instructions: List[str]) -> str:
    """Build the user prompt (initial observation) for the preference agent."""
    story_part = story or ""
    instructions_part = "\n".join(
        f"{i + 1}. {inst}" for i, inst in enumerate(instructions)
    )
    return PREFERENCE_USER_PROMPT_INTRO.format(
        story=story_part,
        instructions=instructions_part,
    )
