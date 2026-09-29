from typing import List

from tracer.prompts.task_preference_common import (
    COMMON_SYSTEM_PROMPT_CORE,
    build_system_prompt,
    build_user_prompt_intro,
)

PREFERENCE_SYSTEM_PROMPT = build_system_prompt(
    "Your task is to REWRITE the following telehealth user instructions into PREFERENCE form.",
    COMMON_SYSTEM_PROMPT_CORE,
    """Telehealth-specific grounding:
- Use tools such as get_appointment_details, get_provider_details, check_provider_appointment_slot, get_medical_record, get_patient_details_complete, list_medication_suppliers, and check_drug_interactions.
- Ground preferences in appointment/provider/medication/device facts from tools.
- For scheduling/rescheduling asks, only express preferred times that align with actual provider availability.

Patient-facing constraints:
- INCLUDE: authenticated patient email identity, patient identity, appointment references, provider names/specialties, medication/device descriptions, and high-level billing preference wording.
- If payment method context is present (copay/billing setup), express it as an explicit preference (e.g. "You prefer to pay by ...").
- DO NOT include exact copay amounts, voucher IDs, internal payment IDs, insurance authorization numbers, or other internal record identifiers.
- Keep wording patient-facing: DO NOT present backend/system checks as facts the patient already knows.

Preference style by action:
- Scheduling: express date/day and provider/modality preferences first, then include time-of-day windows only if needed.
- For reschedule flows, prefer wording like "You prefer the appointment on <date/day> ..." instead of anchoring on exact timestamps unless exact time is explicitly required by the instruction.
- If a same-day fallback is relevant, phrase it as a secondary preference (e.g. "You prefer next day, but would accept same day in the afternoon").
- Prefer relative date phrasing for patient-facing preferences (e.g. "today", "next day", "tomorrow", "in 3 days"), not explicit calendar dates.
- Do not state provider availability as direct patient knowledge (avoid wording like "it aligns with Dr. X availability"). Instead use patient-facing preference rationale (e.g. "because it works better for your schedule").
- Regimen changes: dosing/formulation/supplier preferences with patient-appropriate rationale.
- Telemetry/devices: comfort and usability preferences grounded in context.""",
)

PREFERENCE_USER_PROMPT_INTRO = build_user_prompt_intro(
    "Rewrite the following telehealth user instructions into PREFERENCE form.",
    """Telehealth checklist:
- Look up appointment/provider/medication/device details before writing preferences.
- Keep the authenticated patient email identity present in patient-facing form.
- For new or moved visit times, align wording to bookable windows from provider schedule/slot checks.
- For scheduling preferences, lead with date/day preference language and optionally add a time window; avoid over-fixating on exact clock times unless explicitly required.
- When both preferred and fallback options are present, express them as ranked preferences (preferred date first, fallback date/time second).
- Use relative-day wording in the final preference instruction (e.g. "today", "next day", "in 3 days") and avoid explicit month/day/year dates unless the source explicitly requires exact calendar wording.
- For reschedule wording, DO NOT use explicit calendar timestamp chains like "from YYYY-MM-DD HH:MM to YYYY-MM-DD HH:MM" unless strictly required by source instructions.
- DO NOT use system-facing claims like "this slot is available" in final wording; keep rationale in customer voice (schedule convenience, continuity, preference).
- If later asks change direction, keep chronology explicit with transition language instead of contradiction framing.
- Keep final wording in second-person instruction style that starts with "You are ...".
- Keep output patient-facing and omit internal billing/auth identifiers or exact prices.
- When billing is relevant, include a direct payment-method preference sentence in patient-facing language.""",
)


def format_preference_user_prompt(story: str, instructions: List[str]) -> str:
    """Build the user prompt (initial observation) for the telehealth preference agent."""
    story_part = story or ""
    instructions_part = "\n".join(
        f"{i + 1}. {inst}" for i, inst in enumerate(instructions)
    )
    return PREFERENCE_USER_PROMPT_INTRO.format(
        story=story_part,
        instructions=instructions_part,
    )
