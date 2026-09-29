from __future__ import annotations

from typing import Iterable

PREFERENCE_JSON_CONTRACT = (
    'Output ONLY valid JSON with a single key: {"preference_instruction": "<one combined string>"}. '
    "No other keys or text."
)

COMMON_SYSTEM_PROMPT_CORE = """You will be given a STORY and a list of INSTRUCTIONS. Do the following in order:

1. COMBINE the story and all instructions into one coherent narrative.
2. USE THE TOOLS to look up details for any concrete entities or IDs mentioned in the instructions.
   Use tool outputs to ground facts and map internal identifiers to customer-facing language.
   Do not copy raw tool outputs, backend dumps, or procedural troubleshooting steps into the final instruction.
3. REWRITE that combined narrative as a single PREFERENCE instruction in natural language.
   For each main ask or preference, include a short why-clause grounded in the STORY/INSTRUCTIONS or tool facts.
   Do not invent unrelated backstory.
4. Preserve ORDER OF REQUESTS: follow the original numbered instruction order exactly.
   - If a later instruction changes direction (e.g. update first, then cancel), keep both asks in sequence.
   - Express chronology as future intent from the current moment (e.g. "You want ... Later, you will ... After that, you would like ..."), not as already-completed past events.
   - Use transition language that preserves chronology (e.g. later, after that, subsequently) and contextual motivation.
   - Do not rewrite chronology as contradiction framing (e.g. "instead of the first ask") unless the source explicitly says to replace/override the earlier ask.
5. Keep the result customer-facing and avoid internal identifiers or system-only jargon.
6. Write in SECOND-PERSON instruction style.
   - The combined preference instruction must be phrased as guidance to an agent, not a first-person customer quote.
   - Start the instruction with "You are ..." and continue in that same second-person/instructional style.

When expressing asks, use clear preference/request wording in second-person instructional voice (e.g. "You want...", "You would like...", "You prefer..."). Keep tense present/future-oriented for pending actions; avoid past-perfect framing like "You initially wanted..." unless the source explicitly states completed history.
"""

# Shared by the bank, basketball, movie, restaurant, school and travel preference prompts.
GROUNDED_PREFERENCE_RULES = """Opening:
- The instruction describes the CUSTOMER, never the support agent. Start it with "You are <customer's full name> (<every identifier the customer gives for themselves in the INSTRUCTIONS: email, and any customer/traveler/student/player ID>)", e.g. "You are Casey Parker (casey.parker3671@univ.edu), ..." or "You are Alex Rahman (alex.rahman@example.sg, traveler ID N70KFI1), ...". Never write "You are assisting/helping ...".

Lookups:
- Look entities up directly with the IDs given in the STORY/INSTRUCTIONS (the get_*_details and list_* tools).
- Do NOT page through a *_candidates tool to find a person by email or name: it returns a few rows out of hundreds and will not find them. If a detail cannot be looked up directly, write it as the INSTRUCTIONS give it.

What the user knows:
- The user does not know anything they are asking the agent to look up. Never state the answer to an information request (totals, scores, records, rosters, balances, transactions, availability, prices, lists) in the instruction.
- Never invent a value. Every digit, name, date, amount and payment or refund destination you write must appear in the STORY, the INSTRUCTIONS or a tool result. If you cannot look something up, keep it exactly as the INSTRUCTIONS give it (IDs included).
- Keep every value the agent needs to act and cannot recover with tools: the identity the user authenticates with, IDs the domain policy requires the user to provide, amounts the user chooses, full new addresses, and the dates, names and choices being changed. These count as customer-facing even when they look like identifiers.

Preference requirement:
- The instruction MUST contain at least one explicit user preference: a personal choice, habit or constraint that shapes HOW the task is done (e.g. "You prefer to pay with your Visa ending in 1234", "You like to sit together near the aisle", "You would rather get a short summary than the full list").
- A reason or motivation alone ("because the card was lost", "to review your season") is NOT a preference. Keep the why-clause and add a preference.
- Ground every preference in the STORY, INSTRUCTIONS or tool data. It must still lead the agent to exactly the same records, values and actions as the INSTRUCTIONS, and must not add asks that are not in the INSTRUCTIONS."""

COMMON_USER_PROMPT_STEPS = """Steps:
1. Combine the STORY and all INSTRUCTIONS below into one narrative.
2. Use the provided tools to look up concrete details and map internal IDs into customer-facing language.
   Use tools for grounding, not for copying backend/procedural text into the final output.
3. Write one combined preference instruction with short grounded why-clauses for each main ask.
4. Keep the same order as the numbered INSTRUCTIONS; if direction changes later, narrate it as a chronological transition, not as a contradiction, and keep pending asks in present/future wording ("you want... later you will...").
5. Write in second-person instructional style, starting with "You are ..."; do not write in first-person voice.
6. Return only the required JSON object."""


def _join_sections(sections: Iterable[str]) -> str:
    return "\n\n".join(
        section.strip() for section in sections if section and section.strip()
    )


def build_system_prompt(*sections: str) -> str:
    return _join_sections([*sections, PREFERENCE_JSON_CONTRACT])


def build_user_prompt_intro(task_line: str, *sections: str) -> str:
    safe_contract = PREFERENCE_JSON_CONTRACT.replace("{", "{{").replace("}", "}}")
    body = _join_sections(
        [task_line, COMMON_USER_PROMPT_STEPS, *sections, safe_contract]
    )
    return (
        f"{body}\n\n"
        "STORY (context): {story}\n\n"
        "INSTRUCTIONS (one per line):\n"
        "{instructions}\n\n"
        'When done, respond with ONLY a JSON object: {{"preference_instruction": "<one combined string>"}}'
    )
