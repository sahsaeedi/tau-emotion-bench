from typing import List

from tracer.prompts.task_preference_common import (
    COMMON_SYSTEM_PROMPT_CORE,
    GROUNDED_PREFERENCE_RULES,
    build_system_prompt,
    build_user_prompt_intro,
)

PREFERENCE_SYSTEM_PROMPT = build_system_prompt(
    "Your task is to REWRITE the following school user instructions into PREFERENCE form.",
    COMMON_SYSTEM_PROMPT_CORE,
    GROUNDED_PREFERENCE_RULES,
    """School-specific grounding:
- Use tools such as get_student_details, get_registration_details, get_course_details, search_courses and list_courses_by_term to turn course and payment IDs into course codes, titles, meeting days/times and saved cards.
- Use search_courses to check how many courses match before writing a schedule preference, so it still points to the same courses.

Student-facing constraints:
- INCLUDE: the student_id, and the registration_id for any change to an existing registration (the agent must get both from the student), plus the student's email if given.
- Refer to courses by course code and title (e.g. "BIOL-2020 Cell Biology"); add the course ID only when code and title do not identify it in that term.
- Refer to payment methods by brand and last four digits, not payment IDs. When a payment is split across several methods, keep the amount for each.
- Keep the term, grading options and the health insurance choice exactly.

Preference style by action:
- Registration and add/drop: schedule preferences grounded in the course meeting data (e.g. "You prefer morning classes on Tuesdays and Thursdays"), grading preference (e.g. "You prefer pass/fail for electives"), and campus preference.
- Payments and refunds: which saved card they prefer to use.
- Cancellations: why they cancel.
- Course search and meeting status: what they are looking for (department, days, time of day).""",
)

PREFERENCE_USER_PROMPT_INTRO = build_user_prompt_intro(
    "Rewrite the following school user instructions into PREFERENCE form.",
    """School checklist:
- Keep the student_id, and the registration_id for changes, in the instruction.
- Look up courses and check alternatives before writing schedule preferences.
- Name courses by code and title and cards by brand and last four digits.
- Include at least one explicit preference (schedule, grading, or payment).
- Keep final wording in second-person instruction style that starts with "You are ...".""",
)


def format_preference_user_prompt(story: str, instructions: List[str]) -> str:
    """Build the user prompt (initial observation) for the school preference agent."""
    story_part = story or ""
    instructions_part = "\n".join(
        f"{i + 1}. {inst}" for i, inst in enumerate(instructions)
    )
    return PREFERENCE_USER_PROMPT_INTRO.format(
        story=story_part,
        instructions=instructions_part,
    )
