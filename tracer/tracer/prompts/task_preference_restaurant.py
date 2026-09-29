from typing import List

from tracer.prompts.task_preference_common import (
    COMMON_SYSTEM_PROMPT_CORE,
    GROUNDED_PREFERENCE_RULES,
    build_system_prompt,
    build_user_prompt_intro,
)

PREFERENCE_SYSTEM_PROMPT = build_system_prompt(
    "Your task is to REWRITE the following restaurant user instructions into PREFERENCE form.",
    COMMON_SYSTEM_PROMPT_CORE,
    GROUNDED_PREFERENCE_RULES,
    """Restaurant-specific grounding:
- Use tools such as get_patron_details, get_ticket_details, get_dish_details and list_all_dishes to turn ticket, plate and instrument references into dishes, plate options (e.g. spice level, portion), service mode and saved cards.

Patron-facing constraints:
- INCLUDE: the patron's email address as given (or name + postal code if that is how the INSTRUCTIONS identify them), and the reason for contacting.
- Keep the ticket reference unless the patron's other tickets make a description (dishes, delivery vs dine-in) unambiguous.
- Refer to payment instruments by issuer and last four digits (e.g. "your DBS Bank card ending in 2422"), not by instrument_ref.
- Keep every value a change needs: the full new dropoff address, the table zone, number and seat count, and the exact tip amount.

Preference style by action:
- Plate changes: what they prefer instead, in customer terms (e.g. "You prefer the mild version over the medium one", "a larger portion"), which must map to exactly the target plate of the same dish.
- Payment changes and tips: which saved card they prefer to use and why.
- Table changes: seating preference (e.g. "You prefer a table on the patio for four").
- Dropoff changes: where they prefer the delivery to go and why.
- Cancellations: why they cancel.""",
)

PREFERENCE_USER_PROMPT_INTRO = build_user_prompt_intro(
    "Rewrite the following restaurant user instructions into PREFERENCE form.",
    """Restaurant checklist:
- Keep the patron's email address in the instruction.
- Look up plates and instruments before writing preferences; refer to cards by issuer and last four digits.
- Keep full addresses, table details and tip amounts exactly.
- Include at least one explicit preference (plate option, card, or seating).
- Keep final wording in second-person instruction style that starts with "You are ...".""",
)


def format_preference_user_prompt(story: str, instructions: List[str]) -> str:
    """Build the user prompt (initial observation) for the restaurant preference agent."""
    story_part = story or ""
    instructions_part = "\n".join(
        f"{i + 1}. {inst}" for i, inst in enumerate(instructions)
    )
    return PREFERENCE_USER_PROMPT_INTRO.format(
        story=story_part,
        instructions=instructions_part,
    )
