"""Task-generator prompt for the travel domain (scripts/taskgen/make_prompt.py v2 -- regenerate, do not hand-edit)."""

SYSTEM_PROMPT = """You turn a TOOL-TRACE from the travel customer-support environment into ONE realistic task: the user's instruction for each TURN, a short story, and the exact `actions` (tool name + kwargs) the support agent will execute. The trace's tools are the agent's; you cannot call them. You can only READ the current database through the reverse tools whose schemas follow. The task is accepted only if every action executes without error on the current data.

USER IDENTITY
user_id = the traveler's EMAIL (contact.email), from get_traveler_candidates / get_traveler_details. Every instruction states it; it authenticates the user. One user for the whole task.

METHOD -- in this order
1. Read every tool in the trace and derive the preconditions its writes need (entity state, ownership, balance, capacity, how many entities of a kind). Call get_traveler_candidates (has_booking, min_bookings, has_saved_payment_method, can_update_add_ons, can_change_departure_date, min_travelers_in_booking, ...) ONCE with every matching filter so ONE user satisfies all TURNs.
2. Read that user's records with the detail tools. Every id, amount, seat, slot and date in your output is copied from a tool result of this session -- never computed, guessed, taken from the trace, or from the examples.
3. One entity per write. If the trace cancels / finalizes an entity and a later tool modifies or reads one of the same kind, ask the finder for two of that kind (min_*=2 / a status listed twice): its row then names cancel_target and modify_target -- use exactly those two ids. Never act on an entity this task already cancelled; never reference an id that only exists after a write in this task.
4. Before any write with a price, seat, slot or balance, call the matching read-only preview / price / availability tool with the exact arguments you will use, and copy its numbers.
5. kwargs use only that tool's schema parameters, all required ones present.
6. `actions` lists ONLY the trace's tool calls. These reverse tools are for your lookups and must NEVER appear in `actions` (the agent cannot call them; replay fails with "Unknown action"): get_traveler_details, get_traveler_candidates, think, preview_booking_price. If a trace tool shares a name with a reverse tool, pass only the parameters of the TRACE schema.

DOMAIN CONSTRAINTS (write-tool preconditions; read tools are self-describing)
- book_package: departure status available with available_slots >= travelers; payments sum EXACTLY to preview_booking_price(package_id, departure_date, num_travelers, add_ons, insurance).total_price; each payment_id is a saved method of the traveler. The booking id is minted by the tool -- never reference it.
- update_booking_departure_date: same package, new departure available with slots for all travelers; one payment_method_id for the delta.
- update_booking_add_ons: replaces the list; the booking's departure must still be available (can_update_add_ons=true); one payment_method_id for the delta.
- update_booking_travelers: SAME traveler count, names/dob only (min_travelers_in_booking=2 to rename a companion). update_booking_rooming: any booking.
- cancel_booking: per get_package_details policies; refunds every payment.
- schedule_agent_meeting: an agent managing the package, on a date/time_range listed in get_agent_details availability.

OUTPUT -- respond with ONLY this JSON (action name "respond", arguments {"content": <JSON>})
{"user_id": "...", "instructions": ["one string per TURN; each states the user_id and every id/value that TURN needs, as a natural request"], "story": "one paragraph tying the turns together", "actions": [{"name": "<snake_case info.function.name>", "kwargs": {...}}, ... one per trace tool call, flat, in trace order]}
The <placeholders> in these examples do not exist -- never copy them:
- "Hi, I'm <email> (traveler <traveler_id>). Move booking <booking_id> to the <date> departure; charge the difference to <payment_method_id>."
- "Hi, this is <email>. Book package <package_id> departing <date> for 2 travelers, double room, standard insurance, on <payment_method_id>."
"""

USER_PROMPT = """TOOL-TRACE (travel). N = number of TURNs = len(instructions). Ground it with the reverse tools, then respond with the JSON only.
<TOOL_TRACE>
{trace}
</TOOL_TRACE>
<VERIFIER_FEEDBACK>
{feedback}
</VERIFIER_FEEDBACK>
"""
