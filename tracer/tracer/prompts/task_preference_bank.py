from typing import List

from tracer.prompts.task_preference_common import (
    COMMON_SYSTEM_PROMPT_CORE,
    GROUNDED_PREFERENCE_RULES,
    build_system_prompt,
    build_user_prompt_intro,
)

PREFERENCE_SYSTEM_PROMPT = build_system_prompt(
    "Your task is to REWRITE the following bank user instructions into PREFERENCE form.",
    COMMON_SYSTEM_PROMPT_CORE,
    GROUNDED_PREFERENCE_RULES,
    """Bank-specific grounding:
- Use tools such as get_client_details, list_client_accounts, get_account_details, get_card_details, list_client_beneficiaries, get_beneficiary_details and get_loan_details to confirm account types, card types, currencies, beneficiary names and loan types.

Client-facing constraints:
- INCLUDE: the client's email address exactly as given (the agent authenticates by email only), and the reason for contacting.
- Look up every account, card, beneficiary and loan ID in the INSTRUCTIONS (get_account_details, get_card_details, get_beneficiary_details, get_loan_details). Refer to it by what the lookup returns (e.g. "your checking account ending in 7412", "your debit card ending in 2741", the beneficiary's name, the loan type). If a lookup fails, keep the ID exactly as given; never guess last four digits.
- Keep the exact amount and currency of every transfer and loan payment, and the transfer method or verification method when the INSTRUCTIONS name one.

Preference style by action:
- Transfers and loan payments: which of the client's accounts they prefer to pay from (e.g. "You prefer to pay loans from your checking account rather than your savings").
- Freezing/unfreezing: what should be frozen and why, and whether they prefer to freeze only the card or also the account, exactly as the INSTRUCTIONS ask.
- Beneficiaries: the beneficiary's name and how the client prefers it to be verified or used.
- Information requests: what the client wants to check and how they would like it presented (e.g. only the most recent transactions, only one account).""",
)

PREFERENCE_USER_PROMPT_INTRO = build_user_prompt_intro(
    "Rewrite the following bank user instructions into PREFERENCE form.",
    """Bank checklist:
- Keep the client's email address in the instruction.
- Name accounts and cards by type and last four digits; keep exact amounts and currencies.
- Do not state balances, transactions or other details the client is asking the agent to look up.
- Include at least one explicit preference (for example the account they prefer to pay from).
- Keep final wording in second-person instruction style that starts with "You are ...".""",
)


def format_preference_user_prompt(story: str, instructions: List[str]) -> str:
    """Build the user prompt (initial observation) for the bank preference agent."""
    story_part = story or ""
    instructions_part = "\n".join(
        f"{i + 1}. {inst}" for i, inst in enumerate(instructions)
    )
    return PREFERENCE_USER_PROMPT_INTRO.format(
        story=story_part,
        instructions=instructions_part,
    )
