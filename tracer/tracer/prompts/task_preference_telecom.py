from typing import List

from tracer.prompts.task_preference_common import (
    COMMON_SYSTEM_PROMPT_CORE,
    build_system_prompt,
    build_user_prompt_intro,
)

PREFERENCE_SYSTEM_PROMPT = build_system_prompt(
    "Your task is to REWRITE the following user instructions into PREFERENCE form.",
    COMMON_SYSTEM_PROMPT_CORE,
    """Telecom-specific grounding:
- Use tools such as get_customer_details, get_service_details, and get_billing_details to ground service names, billing preferences, device context, and issue state.
- Use grounded details to express customer intent around troubleshooting, service choices, and billing settings.

Customer-facing constraints:
- INCLUDE: authenticated customer email identity, customer_id (if naturally present), human-readable service names, device names, ticket/issue references, billing preferences.
- If billing/payment method context exists, include explicit payment preference phrasing (e.g. "You prefer to pay by ...", "You prefer autopay with ...").
- DO NOT include raw service_ids/plan_ids/device_ids, internal system IDs, or raw tool/procedural troubleshooting text.
- When troubleshooting appears, express the customer's need and situation rather than listing backend steps.

Preference rationale requirements:
- For each major ask, include a short grounded why-clause.
- If a device is mentioned, state why that device context matters to the user outcome.
- If a plan/service/billing preference is mentioned, state why that option is preferred (fit, control, usage pattern, reliability need), grounded in STORY/INSTRUCTIONS/tool data.
- Keep rationales factual and concise; do not invent unrelated backstory.

Preference style by action:
- Service/plan changes: express ranked preferences (primary option first, fallback second) with concise grounded reasons.
- Billing changes: express explicit preferences for auto-pay, paperless billing, and billing cycle in customer-facing wording.
- Device changes: express manufacturer/brand preference first (for example Apple, Samsung, Google), then model preference.
- For device alternatives, include ranked fallback phrasing (for example "You prefer <brand/model>, but would accept <brand/model>").

Language and formatting constraints:
- If multiple viable options exist, present them as ranked preferences: preferred option first, acceptable fallback second.
- Keep chronology future-intent (for example "You want... Later, you would like..."), not past-completed narration.
- Do not output backend field names or raw identifiers such as service_id, plan_id, device_id, manufacturer, category, or model.
- Convert tool/catalog facts into natural language only.

Example: "You are john_smith_1234. The iPhone 15 Pro has battery issues, so you would like troubleshooting because the phone dies before the end of the day. After that, you would like a support ticket for the device issue and escalation to high priority since the phone is needed for work." """,
)

PREFERENCE_USER_PROMPT_INTRO = build_user_prompt_intro(
    "Rewrite the following user instructions into PREFERENCE form.",
    """Telecom checklist:
- Ground device/service/billing details with tools before rewriting.
- Keep the authenticated customer email identity present in customer-facing form.
- Use customer terms for plans/services (never raw IDs).
- For troubleshooting asks, keep output as user preference/situation, not step-by-step tool output.
- Add a short grounded reason for each major ask, especially for device context and plan/billing preferences.
- If later asks change direction, keep chronology explicit with transition language and avoid contradiction phrasing.
- If the request involves adding/changing devices, include one explicit manufacturer/brand preference sentence before model-level preference.
- For plan/service and billing asks, use ranked preference wording: preferred option first, fallback option second when applicable.
- Do not include backend field names or raw IDs (service_id, device_id, plan_id); keep only customer-facing language.
- Keep final wording in second-person instruction style that starts with "You are ...".
- Keep all wording customer-facing and avoid backend/internal identifier leakage.
- When billing choices are part of the request, include a direct payment-method preference sentence.""",
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
