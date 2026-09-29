from typing import List

from tracer.prompts.task_preference_common import (
    COMMON_SYSTEM_PROMPT_CORE,
    GROUNDED_PREFERENCE_RULES,
    build_system_prompt,
    build_user_prompt_intro,
)

PREFERENCE_SYSTEM_PROMPT = build_system_prompt(
    "Your task is to REWRITE the following travel agency user instructions into PREFERENCE form.",
    COMMON_SYSTEM_PROMPT_CORE,
    GROUNDED_PREFERENCE_RULES,
    """Travel-specific grounding:
- Use tools such as get_traveler_details, get_booking_details, get_package_details, search_packages, get_agent_details and list_all_destinations to turn package, booking, agent and payment IDs into destinations, package names, departure dates, add-ons and saved cards.
- Use get_package_details and search_packages to check how many departures or packages match before writing a date or package preference, so it still points to the same one.

Traveler-facing constraints:
- INCLUDE: the traveler_id (the agent must get it from the traveler), and the booking_id when the traveler has more than one booking.
- Refer to packages by name and destination and to payment methods by brand and last four digits, not payment IDs. When a payment is split across several methods, keep the amount for each.
- Keep exact departure dates, traveler names and dates of birth being changed, rooming, add-ons and the insurance tier.
- Do not include computed totals or price differences; the agent computes them.

Preference style by action:
- Booking: destination and trip style, departure date, rooming preference (e.g. "You prefer twin beds"), add-ons they want, insurance tier, and payment preference.
- Date changes: why they need to move and which departure they prefer.
- Add-on changes: which activities they prefer and why.
- Agent meetings: preferred agent and time of day.
- Cancellations: why they cancel, and which card the refund goes to only if the INSTRUCTIONS say.""",
)

PREFERENCE_USER_PROMPT_INTRO = build_user_prompt_intro(
    "Rewrite the following travel agency user instructions into PREFERENCE form.",
    """Travel checklist:
- Keep the traveler_id, and the booking_id when needed, in the instruction.
- Look up packages, departures and add-ons before writing preferences.
- Name packages by name/destination and cards by brand and last four digits; keep exact dates.
- Include at least one explicit preference (rooming, add-ons, dates, or payment).
- Keep final wording in second-person instruction style that starts with "You are ...".""",
)


def format_preference_user_prompt(story: str, instructions: List[str]) -> str:
    """Build the user prompt (initial observation) for the travel preference agent."""
    story_part = story or ""
    instructions_part = "\n".join(
        f"{i + 1}. {inst}" for i, inst in enumerate(instructions)
    )
    return PREFERENCE_USER_PROMPT_INTRO.format(
        story=story_part,
        instructions=instructions_part,
    )
