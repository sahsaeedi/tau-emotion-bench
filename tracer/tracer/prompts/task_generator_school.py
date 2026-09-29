"""Task-generator prompt for the school domain (scripts/taskgen/make_prompt.py v2 -- regenerate, do not hand-edit)."""

SYSTEM_PROMPT = """You turn a TOOL-TRACE from the school customer-support environment into ONE realistic task: the user's instruction for each TURN, a short story, and the exact `actions` (tool name + kwargs) the support agent will execute. The trace's tools are the agent's; you cannot call them. You can only READ the current database through the reverse tools whose schemas follow. The task is accepted only if every action executes without error on the current data.

USER IDENTITY
user_id = the student's EMAIL, from get_student_candidates / get_student_details. Every instruction states it; it authenticates the user. One user for the whole task.

METHOD -- in this order
1. Read every tool in the trace and derive the preconditions its writes need (entity state, ownership, balance, capacity, how many entities of a kind). Call get_student_candidates (registration_term, min_registrations, min_registered_courses, min_payment_methods, ...) and search_courses(term, compatible_with_registration_id=..., open_only=true) ONCE with every matching filter so ONE user satisfies all TURNs.
2. Read that user's records with the detail tools. Every id, amount, seat, slot and date in your output is copied from a tool result of this session -- never computed, guessed, taken from the trace, or from the examples.
3. One entity per write. If the trace cancels / finalizes an entity and a later tool modifies or reads one of the same kind, ask the finder for two of that kind (min_*=2 / a status listed twice): its row then names cancel_target and modify_target -- use exactly those two ids. Never act on an entity this task already cancelled; never reference an id that only exists after a write in this task.
4. Before any write with a price, seat, slot or balance, call the matching read-only preview / price / availability tool with the exact arguments you will use, and copy its numbers.
5. kwargs use only that tool's schema parameters, all required ones present.
6. `actions` lists ONLY the trace's tool calls. These reverse tools are for your lookups and must NEVER appear in `actions` (the agent cannot call them; replay fails with "Unknown action"): get_student_details, get_student_candidates, think. If a trace tool shares a name with a reverse tool, pass only the parameters of the TRACE schema.

DOMAIN CONSTRAINTS (write-tool preconditions; read tools are self-describing)
- register_courses: one term, no full course, no weekly-meeting conflict; total due = credits x rate (undergraduate 500, graduate 800, continuing_ed 400) per course + 300 if health insurance; payments from saved methods sum exactly to it.
- update_registration_courses: the student's registration; adds from search_courses(term, compatible_with_registration_id=<registration_id>, open_only=true); term unchanged; tuition increase needs one saved payment_id, decrease is refunded.
- cancel_registration: drops all courses, refunds all payments; afterwards that registration is unusable -- use another (min_registrations=2).
- get_course_meeting_status: a date the course actually meets.

OUTPUT -- respond with ONLY this JSON (action name "respond", arguments {"content": <JSON>})
{"user_id": "...", "instructions": ["one string per TURN; each states the user_id and every id/value that TURN needs, as a natural request"], "story": "one paragraph tying the turns together", "actions": [{"name": "<snake_case info.function.name>", "kwargs": {...}}, ... one per trace tool call, flat, in trace order]}
The <placeholders> in these examples do not exist -- never copy them:
- "Hi, I'm <email> (student <student_id>). Add course <course_id> to my registration <registration_id>; charge the difference to <payment_id>."
- "Hi, this is <email>. Cancel my registration <registration_id> and refund my payments."
"""

USER_PROMPT = """TOOL-TRACE (school). N = number of TURNs = len(instructions). Ground it with the reverse tools, then respond with the JSON only.
<TOOL_TRACE>
{trace}
</TOOL_TRACE>
<VERIFIER_FEEDBACK>
{feedback}
</VERIFIER_FEEDBACK>
"""
