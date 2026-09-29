from typing import List

from tracer.prompts.task_preference_common import (
    COMMON_SYSTEM_PROMPT_CORE,
    GROUNDED_PREFERENCE_RULES,
    build_system_prompt,
    build_user_prompt_intro,
)

PREFERENCE_SYSTEM_PROMPT = build_system_prompt(
    "Your task is to REWRITE the following basketball user instructions into PREFERENCE form.",
    COMMON_SYSTEM_PROMPT_CORE,
    GROUNDED_PREFERENCE_RULES,
    """Basketball-specific grounding:
- Use tools such as get_player_details, get_club_details, get_club_schedule, get_game_details and list_all_clubs to turn club and game IDs into names, opponents and dates.

Player-facing constraints:
- INCLUDE: the player's email address as given (or full name + ZIP code if that is how the INSTRUCTIONS identify them), and the reason for contacting.
- Refer to clubs by name and to games by opponent and date, not by internal IDs, when that identifies them uniquely; keep the ID only when it does not.
- Keep every value a write needs: the full new address, the requested game status, and each scoring event's player, points and type.
- NEVER state the answer to an information request (points totals, rosters, records, scores, box scores, schedules): the player is asking because they do not know it.

Preference style by action:
- Information requests: what the player wants to know and how they would like it (e.g. "You only care about your own points, not the team total", "You would rather get just the final score than the full box score", "You prefer the list of clubs in your league only").
- Address changes: the new address as their preferred mailing address and why they are moving.
- Game status and scoring events: the requested change, stated as the player's decision, with a short grounded reason.""",
)

PREFERENCE_USER_PROMPT_INTRO = build_user_prompt_intro(
    "Rewrite the following basketball user instructions into PREFERENCE form.",
    """Basketball checklist:
- Keep the player's email address (or full name + ZIP) in the instruction.
- Use club names and game opponents/dates instead of internal IDs when they are unique.
- Do not state points, rosters, records or scores the player is asking for.
- Include at least one explicit preference (for example which information they care about and how they want it).
- Keep final wording in second-person instruction style that starts with "You are ...".""",
)


def format_preference_user_prompt(story: str, instructions: List[str]) -> str:
    """Build the user prompt (initial observation) for the basketball preference agent."""
    story_part = story or ""
    instructions_part = "\n".join(
        f"{i + 1}. {inst}" for i, inst in enumerate(instructions)
    )
    return PREFERENCE_USER_PROMPT_INTRO.format(
        story=story_part,
        instructions=instructions_part,
    )
