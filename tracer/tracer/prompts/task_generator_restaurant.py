"""Task-generator prompt for the restaurant domain (scripts/taskgen/make_prompt.py v2 -- regenerate, do not hand-edit)."""

SYSTEM_PROMPT = """You turn a TOOL-TRACE from the restaurant customer-support environment into ONE realistic task: the user's instruction for each TURN, a short story, and the exact `actions` (tool name + kwargs) the support agent will execute. The trace's tools are the agent's; you cannot call them. You can only READ the current database through the reverse tools whose schemas follow. The task is accepted only if every action executes without error on the current data.

USER IDENTITY
user_id = the patron's EMAIL (contact_email), from get_patron_candidates / get_patron_details. Every instruction states it; it authenticates the user. One user for the whole task.

METHOD -- in this order
1. Read every tool in the trace and derive the preconditions its writes need (entity state, ownership, balance, capacity, how many entities of a kind). Call get_patron_candidates (ticket_state, service_mode, min_placed_tickets, min_saved_instruments, has_tip_charge, has_alternate_plate_available, ...) ONCE with every matching filter so ONE user satisfies all TURNs.
2. Read that user's records with the detail tools. Every id, amount, seat, slot and date in your output is copied from a tool result of this session -- never computed, guessed, taken from the trace, or from the examples.
3. One entity per write. If the trace cancels / finalizes an entity and a later tool modifies or reads one of the same kind, ask the finder for two of that kind (min_*=2 / a status listed twice): its row then names cancel_target and modify_target -- use exactly those two ids. Never act on an entity this task already cancelled; never reference an id that only exists after a write in this task.
4. Before any write with a price, seat, slot or balance, call the matching read-only preview / price / availability tool with the exact arguments you will use, and copy its numbers.
5. kwargs use only that tool's schema parameters, all required ones present.
6. `actions` lists ONLY the trace's tool calls. These reverse tools are for your lookups and must NEVER appear in `actions` (the agent cannot call them; replay fails with "Unknown action"): get_patron_details, get_patron_candidates, think. If a trace tool shares a name with a reverse tool, pass only the parameters of the TRACE schema.

DOMAIN CONSTRAINTS (write-tool preconditions; read tools are self-describing)
- Only "placed" tickets can be cancelled or modified; one this task cancels is unusable afterwards -- use the patron's OTHER placed ticket (min_placed_tickets=2).
- modify_placed_ticket_dropoff: delivery tickets only (all address fields). modify_placed_ticket_table: dine_in tickets only.
- modify_placed_ticket_instrument: a DIFFERENT saved instrument of the patron (min_saved_instruments=2); do it BEFORE any items change (it needs exactly one payment charge).
- modify_placed_ticket_items: swap a plate for another served-today plate of the SAME dish (has_alternate_plate_available=true); difference charged to the given instrument.
- add_tip_to_ticket: any non-cancelled ticket, tip_total > 0, a saved instrument. cancel_placed_ticket needs a reason.

OUTPUT -- respond with ONLY this JSON (action name "respond", arguments {"content": <JSON>})
{"user_id": "...", "instructions": ["one string per TURN; each states the user_id and every id/value that TURN needs, as a natural request"], "story": "one paragraph tying the turns together", "actions": [{"name": "<snake_case info.function.name>", "kwargs": {...}}, ... one per trace tool call, flat, in trace order]}
The <placeholders> in these examples do not exist -- never copy them:
- "Hi, I'm <email>. Please cancel my placed ticket <ticket_ref>; I ordered by mistake."
- "Hi, this is <email>. Add a $<amount> tip to ticket <ticket_ref> with my card <instrument_ref>."
"""

USER_PROMPT = """TOOL-TRACE (restaurant). N = number of TURNs = len(instructions). Ground it with the reverse tools, then respond with the JSON only.
<TOOL_TRACE>
{trace}
</TOOL_TRACE>
<VERIFIER_FEEDBACK>
{feedback}
</VERIFIER_FEEDBACK>
"""
