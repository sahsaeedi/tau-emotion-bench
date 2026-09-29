from typing import List

from tracer.prompts.task_preference_common import (
    COMMON_SYSTEM_PROMPT_CORE,
    GROUNDED_PREFERENCE_RULES,
    build_system_prompt,
    build_user_prompt_intro,
)

PREFERENCE_SYSTEM_PROMPT = build_system_prompt(
    "Your task is to REWRITE the following movie theater user instructions into PREFERENCE form.",
    COMMON_SYSTEM_PROMPT_CORE,
    GROUNDED_PREFERENCE_RULES,
    """Movie-specific grounding:
- Use tools such as get_booking_details, get_show_details, list_shows, get_seat_availability, get_movie_details and get_theater_details to turn movie, theater, show and seat IDs into titles, theater names, dates, times and seat locations.
- Use list_shows and get_seat_availability to check how many options match before writing a preference, so the preference still points to the same show and seats.

Customer-facing constraints:
- INCLUDE: the booking_id for any existing booking (the agent cannot find a booking without it), and for a new booking the customer's name, email and phone as given.
- Refer to movies and theaters by name and to shows by date and time; keep seat IDs (e.g. "B4 and B5") whenever a description alone would not identify exactly those seats.
- Keep the ticket type of each seat (adult/child/senior/...) and the delivery method. Request wheelchair seats only if the INSTRUCTIONS do.
- Do not include price totals or refund amounts; the agent computes them.

Preference style by action:
- New bookings: showtime preference (e.g. "an evening show", "the 19:30 show" when several evening shows exist), seat preference (e.g. "seats together in row B", "on the aisle"), and payment preference (e.g. "You prefer to pay with your card ending in 4242", or a gift card when the INSTRUCTIONS use one).
- Seat updates: what is wrong with the current seats and what they prefer instead, keeping the exact target seats.
- Cancellations: why they cancel. Say where the refund goes only if the INSTRUCTIONS do.
- Browsing: what kind of movie or theater they are looking for (genre, date, time of day, location).""",
)

PREFERENCE_USER_PROMPT_INTRO = build_user_prompt_intro(
    "Rewrite the following movie theater user instructions into PREFERENCE form.",
    """Movie checklist:
- Keep the booking_id of every existing booking in the instruction.
- Check shows and seat availability before writing time or seat preferences, and keep exact seat IDs when needed to identify them.
- Include at least one explicit preference (showtime, seats, or payment).
- Do not include computed prices or refund amounts.
- Keep final wording in second-person instruction style that starts with "You are ...".""",
)


def format_preference_user_prompt(story: str, instructions: List[str]) -> str:
    """Build the user prompt (initial observation) for the movie preference agent."""
    story_part = story or ""
    instructions_part = "\n".join(
        f"{i + 1}. {inst}" for i, inst in enumerate(instructions)
    )
    return PREFERENCE_USER_PROMPT_INTRO.format(
        story=story_part,
        instructions=instructions_part,
    )
