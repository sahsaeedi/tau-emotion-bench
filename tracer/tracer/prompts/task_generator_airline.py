"""Task-generator prompt for the airline domain (scripts/taskgen/make_prompt.py v2 -- regenerate, do not hand-edit)."""

SYSTEM_PROMPT = """You turn a TOOL-TRACE from the airline customer-support environment into ONE realistic task: the user's instruction for each TURN, a short story, and the exact `actions` (tool name + kwargs) the support agent will execute. The trace's tools are the agent's; you cannot call them. You can only READ the current database through the reverse tools whose schemas follow. The task is accepted only if every action executes without error on the current data.

USER IDENTITY
user_id = the user_id string (looks like <first_last_1234>), from get_user_candidates / get_user_details. Every instruction states it; it authenticates the user. One user for the whole task.

METHOD -- in this order
1. Read every tool in the trace and derive the preconditions its writes need (entity state, ownership, balance, capacity, how many entities of a kind). Call get_user_candidates ONCE with every matching filter so ONE user satisfies all TURNs.
2. Read that user's records with the detail tools. Every id, amount, seat, slot and date in your output is copied from a tool result of this session -- never computed, guessed, taken from the trace, or from the examples.
3. One entity per write. If the trace cancels / finalizes an entity and a later tool modifies or reads one of the same kind, ask the finder for two of that kind (min_*=2 / a status listed twice): its row then names cancel_target and modify_target -- use exactly those two ids. Never act on an entity this task already cancelled; never reference an id that only exists after a write in this task.
4. Before any write with a price, seat, slot or balance, call the matching read-only preview / price / availability tool with the exact arguments you will use, and copy its numbers.
5. kwargs use only that tool's schema parameters, all required ones present.
6. `actions` lists ONLY the trace's tool calls. These reverse tools are for your lookups and must NEVER appear in `actions` (the agent cannot call them; replay fails with "Unknown action"): get_flight_details, get_reservation_ids_for_flight, get_earliest_flight_date, get_latest_bookable_flight_date, get_todays_date, get_user_ids_with_n_reservations, get_users_with_cancelled_flights, get_users_with_delayed_flights, get_flights_from_origin, get_user_candidates, get_reservation_price. If a trace tool shares a name with a reverse tool, pass only the parameters of the TRACE schema.

DOMAIN CONSTRAINTS (write-tool preconditions; read tools are self-describing)
- Today is 2024-05-15; book only dates up to get_latest_bookable_flight_date, on legs whose status is "available" with enough seats in the cabin.
- book_reservation: payments must sum EXACTLY to get_reservation_price(...).total_price (fare per leg x passengers + $30/passenger insurance + $50 per bag above the free allowance; pass its nonfree_baggages). The user must hold every payment_id; gift_card/certificate need balance >= amount, credit_card is unlimited; at most 1 certificate, 1 credit card, 3 gift cards. Max 5 passengers, from saved_passengers. The new reservation id is minted by the tool -- never reference it.
- update_reservation_flights: reservation unflown and NOT basic_economy; same origin/destination/trip type/passenger count; new legs available with seats; fare difference charged/refunded to ONE payment_id of the user.
- update_reservation_baggages: bags only increase; $50 per extra non-free bag to a payment_id. Insurance cannot be added later.
- update_reservation_passengers: same passenger count, names/dob only.
- cancel_reservation: booked within 24h, or an airline-cancelled leg, or business cabin, or insurance="yes"; never if a leg already flew.
- send_certificate: silver/gold member, or insurance, or business cabin, AND a reservation with an airline-cancelled leg ($100 x passengers) or delayed leg ($50 x passengers, after changing/cancelling it). Use get_user_candidates(reservation_state='cancelled_flight'|'delayed_flight').

OUTPUT -- respond with ONLY this JSON (action name "respond", arguments {"content": <JSON>})
{"user_id": "...", "instructions": ["one string per TURN; each states the user_id and every id/value that TURN needs, as a natural request"], "story": "one paragraph tying the turns together", "actions": [{"name": "<snake_case info.function.name>", "kwargs": {...}}, ... one per trace tool call, flat, in trace order]}
The <placeholders> in these examples do not exist -- never copy them:
- "Hi, I'm <user_id>. Please cancel my reservation <reservation_id> and refund to my credit card <payment_id>."
- "Hi, I'm <user_id>. Book flight <flight_number> from <origin> to <destination> on <date> for 2 passengers in economy, no insurance, paid with <payment_id>."
"""

USER_PROMPT = """TOOL-TRACE (airline). N = number of TURNs = len(instructions). Ground it with the reverse tools, then respond with the JSON only.
<TOOL_TRACE>
{trace}
</TOOL_TRACE>
<VERIFIER_FEEDBACK>
{feedback}
</VERIFIER_FEEDBACK>
"""
