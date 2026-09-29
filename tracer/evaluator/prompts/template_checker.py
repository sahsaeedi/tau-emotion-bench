"""Prompts for the task-template evaluator (Criterion 2).

Criterion: a task instruction must follow the template:
    (tool-calling task) + (user preference)

"Tool-calling task": a concrete, specific request that maps to one or more
tool calls the agent can make in the domain environment. All required
parameter values should be present or inferable.

"User preference": a stable personal trait or stylistic constraint expressed
by the user that shapes HOW the task is done — NOT simply another request
parameter or instruction detail.

Preference vs. parameter distinction
--------------------------------------
PREFERENCE (✓):
  - "I prefer window seats" — stable personal preference about seating
  - "I always pay with my gift card on file" — preferred payment method as a trait
  - "I don't like adding insurance" — a stated personal dislike/policy
  - "I'd prefer to travel in business class when possible" — stylistic constraint
  - "Please use the same flight dates, I don't want to change those" — expressed constraint

NOT A PREFERENCE (✗):
  - "passenger count = 3" — a request parameter, not a stable trait
  - "my flight date is 2024-05-21" — a specific request detail
  - "pay with gift_card_6702423" — a specific card ID used as a parameter
  - "reserve seat 14B" — a specific request parameter

Note: on raw (pre-rewrite) instructions, it is common for the preference to be
absent. Absence of a preference in a raw instruction is NOT a template violation
by itself — violations are only definitive on the preference-rewritten instruction
(the `preference_instruction` field).
"""

SYSTEM_PROMPT = """You are an evaluator that checks whether a customer-support task instruction follows the required template:

    (tool-calling task) + (user preference)

Definitions
-----------
TOOL-CALLING TASK: A concrete, specific request that the support agent can fulfill by calling one or more tools. The task must be specific enough that an agent could look up the relevant records and execute it. Vague requests like "help me with something" do not qualify.

USER PREFERENCE: A stable personal trait, stylistic constraint, or expressed personal policy that shapes *how* the task is executed — not just what the task is. A preference is something about *the user*, not just a parameter of this particular request.
  Has preference (✓): "I prefer window seats", "I always use my gift card", "I don't want insurance added", "I'd like business class whenever possible"
  NOT a preference (✗): "passenger count = 3", "payment method gift_card_6702423", "seat 14B", "flight date 2024-05-21"

Rules
-----
1. A task FOLLOWS the template if it has both a tool-calling task AND at least one user preference.
2. A task DOES NOT follow the template if either component is missing.
3. A preference that is only implied (e.g. "using my usual card") counts as a preference.
4. Multiple tool-calling tasks in one instruction are fine — the template requires at least one plus at least one preference.
5. Return ONLY the JSON object below — no extra text.

Response JSON (required keys only):
- has_tool_calling_task (boolean): true if a concrete tool-callable task is present
- tool_calling_task_summary (string): one-line summary of the task(s), or empty string
- has_preference (boolean): true if at least one user preference is present
- preference_summary (string): one-line summary of the preference(s), or empty string if none
- follows_template (boolean): true if both components are present
- reason (string): short (1–3 sentence) explanation

Do not output any other keys. Respond with valid JSON only."""


def format_user_prompt(
    instruction: str, domain: str, is_preference_pass: bool = False
) -> str:
    context = (
        "This is a preference-rewritten instruction (the `preference_instruction` field). "
        "A user preference SHOULD be present here — its absence is a template violation."
        if is_preference_pass
        else "This is a raw generated instruction. A preference may or may not be present."
    )
    return f"Domain: {domain}\nContext: {context}\n\nInstruction to evaluate:\n{instruction}"
