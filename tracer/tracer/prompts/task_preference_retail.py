from typing import List

from tracer.prompts.task_preference_common import (
    COMMON_SYSTEM_PROMPT_CORE,
    build_system_prompt,
    build_user_prompt_intro,
)

PREFERENCE_SYSTEM_PROMPT = build_system_prompt(
    "Your task is to REWRITE the following user instructions into PREFERENCE form.",
    COMMON_SYSTEM_PROMPT_CORE,
    """Retail-specific grounding:
- Use tools such as get_order_details and get_product_details to derive customer-relevant attributes (name, color, size, material, shipping context).
- Use looked-up details to express preferences accurately (fit, style, exchange/return intent, payment/address preferences).

Customer-facing constraints:
- INCLUDE: authenticated user email (user_id/email), product/order descriptions in customer language, reason for contacting, payment-type preference, and address phrasing customers naturally use.
- When payment context exists, include explicit payment preference wording (e.g. "You prefer to pay by ...", "You prefer the refund back to ...").
- DO NOT include raw order_id/product_id/item_id/payment_id or exact totals/refund dollar amounts.
- When referring to an order, use partial natural cues grounded in tool data (items, city, status), not internal codes.

Preference style by action:
- Exchange/return: what did not work and what is preferred.
- For exchanges, prefer comparative phrasing (e.g. "prefer X over Y", "prefer smaller/bigger", "prefer more elegant over sporty") instead of catalog-style replacement specs.
- For size or capacity changes, explicitly express the preference delta in customer units (e.g. 500ml instead of 750ml, 2L instead of 1L).
- Payment change: customer-safe phrasing (e.g. card ending in X, gift card used) only when supported.
- Shipping/address: natural address references without internal identifiers.
- Product identification style: write like a real customer who may not know product names/technical details; describe what they want using preference cues (use case, color/style, fit/size, material, budget band, intended recipient) so the product can still be uniquely identified from grounded context.""",
)

PREFERENCE_USER_PROMPT_INTRO = build_user_prompt_intro(
    "Rewrite the following user instructions into PREFERENCE form.",
    """Retail checklist:
- Look up order/product attributes before writing preferences.
- Describe orders indirectly with grounded partial cues, not #W-style identifiers.
- Keep the authenticated email identity present in customer-facing form.
- If later asks change direction (e.g. modify then cancel), keep them in chronological sequence with transition language.
- Keep final wording in second-person instruction style that starts with "You are ...".
- Keep pricing/refund wording high-level and customer-facing only.
- If payment method information is available, include a direct payment-method preference sentence in customer-facing language.
- When product knowledge is limited, prefer customer-like preference cues over catalog terminology, but include enough grounded attributes to identify the product reliably.
- For exchange requests, lead with user preference intent ("prefer X over Y") and keep target attributes concise; include only the minimum grounded details needed to identify the correct replacement.""",
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
