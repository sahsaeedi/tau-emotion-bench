"""Generate tracer/prompts/task_generator_<domain>.py for every domain (compact v2).

    python scripts/taskgen/make_prompt.py --all
    python scripts/taskgen/make_prompt.py movie --stdout

Design (v2, 2026-09-12): the ReAct agent receives every reverse tool's JSON schema
right after this prompt, and each tool observation is appended to the conversation, so
after 10-20 steps anything long or repeated here has left the model's working window.
Therefore:
  * nothing the tool schemas already say is repeated (no per-tool guide);
  * every rule is stated ONCE, as an imperative step, in the order the model must act;
  * domain rules are only write-tool preconditions and pricing facts the reverse tools
    cannot express;
  * examples use <placeholders>, never real ids (a model once copied one verbatim).
"""

from __future__ import annotations

import argparse
import importlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
import sys

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# noun: what the user is called; user_id: what the output's user_id field holds;
# finder: the conjunctive candidates tool(s); rules: write-tool preconditions + prices.
SPEC: dict[str, dict] = {
    "airline": dict(
        user_id="the user_id string (looks like <first_last_1234>), from get_user_candidates / get_user_details",
        finder="get_user_candidates",
        rules="""
- Today is 2024-05-15; book only dates up to get_latest_bookable_flight_date, on legs whose status is "available" with enough seats in the cabin.
- book_reservation: payments must sum EXACTLY to get_reservation_price(...).total_price (fare per leg x passengers + $30/passenger insurance + $50 per bag above the free allowance; pass its nonfree_baggages). The user must hold every payment_id; gift_card/certificate need balance >= amount, credit_card is unlimited; at most 1 certificate, 1 credit card, 3 gift cards. Max 5 passengers, from saved_passengers. The new reservation id is minted by the tool -- never reference it.
- update_reservation_flights: reservation unflown and NOT basic_economy; same origin/destination/trip type/passenger count; new legs available with seats; fare difference charged/refunded to ONE payment_id of the user.
- update_reservation_baggages: bags only increase; $50 per extra non-free bag to a payment_id. Insurance cannot be added later.
- update_reservation_passengers: same passenger count, names/dob only.
- cancel_reservation: booked within 24h, or an airline-cancelled leg, or business cabin, or insurance="yes"; never if a leg already flew.
- send_certificate: silver/gold member, or insurance, or business cabin, AND a reservation with an airline-cancelled leg ($100 x passengers) or delayed leg ($50 x passengers, after changing/cancelling it). Use get_user_candidates(reservation_state='cancelled_flight'|'delayed_flight').
""",
        examples=[
            "Hi, I'm <user_id>. Please cancel my reservation <reservation_id> and refund to my credit card <payment_id>.",
            "Hi, I'm <user_id>. Book flight <flight_number> from <origin> to <destination> on <date> for 2 passengers in economy, no insurance, paid with <payment_id>.",
        ],
    ),
    "retail": dict(
        user_id="the user's EMAIL, from get_users_with_orders / get_user_details",
        finder="get_users_with_orders (statuses=[...]; repeat a status to require several orders in it) or get_user_ids_with_n_orders",
        rules="""
- Pending orders only: cancel_pending_order, modify_pending_order_address, modify_pending_order_payment, modify_pending_order_items (once per order; afterwards it is "pending (item modified)" and cannot be modified again). Delivered orders only: return_delivered_order_items, exchange_delivered_order_items (once per order; never both on the same order).
- modify_pending_order_payment: new method differs from the current one; the user needs >= 2 methods among credit_card/paypal (a gift card must cover the whole order).
- modify_pending_order_items / exchange: new items are AVAILABLE variants of the SAME product (get_product_variants); price increase charged to a payment_id the user holds (gift card needs balance), decrease refunded to it.
- Refunds: original payment method or an existing gift card of the user.
- modify_user_address: any user; generate_new_address gives a fresh address.
""",
        examples=[
            "Hi, my email is <email>. Please cancel my pending order <order_id>; I no longer need it.",
            "Hi, my email is <email>. For my delivered order <order_id>, exchange item <item_id> for variant <new_item_id>; charge the difference to <payment_method_id>.",
        ],
    ),
    "telecom": dict(
        user_id="the customer's EMAIL (demographics.email), from get_customer_candidates / get_customer_details",
        finder="get_customer_candidates (combine senior_plan, has_devices, has_outstanding_balance, has_open_ticket, service_id, min_services, min_devices in ONE call)",
        rules="""
- get_senior_discount: customer on mobile_senior; original_price="45.00".
- troubleshoot_device: a device the customer owns (name from get_customer_details).
- manage_service: remove needs a service the customer has, add one they lack (get_services); switching = remove old then add new.
- record_payment: current_balance > 0 and amount <= balance (get_billing_details). manage_billing: fields from get_billing_details.
- create_support_ticket: customer_id, category, priority. modify_support_ticket: an EXISTING ticket of that customer (open_ticket_ids from the finder), never one this task creates.
""",
        examples=[
            "Hi, I'm <email>. My <device name> keeps dropping calls -- troubleshoot it and open a high-priority device ticket.",
            "Hi, I'm <email>. I owe $<amount>; please pay it in full with my credit card.",
        ],
    ),
    "telehealth": dict(
        user_id="the patient's EMAIL, from query_patient_candidates / get_patient_details_complete",
        finder="query_patient_candidates (appointment_status, min_appointments, has_telemetry_assigned, min_medical_records, has_regimen_plan, ...)",
        rules="""
- Tools answer in plain English; a refusal carries no "Error:" prefix -- read the text.
- cancel_appointment / reschedule_appointment: appointment scheduled or pending_approval (never cancelled/completed); rescheduling needs a free slot on a working day of the provider (check_provider_appointment_slot); a slot this task books is no longer free.
- schedule_appointment: provider from list_available_providers, free slot, supported type; the patient must not already have an appointment at that time.
- Records / telemetry / prescriptions belong to the patient: choose a patient who HAS them (min_medical_records, has_telemetry_assigned, has_regimen_plan) before listing or updating; update_prescription_supplier needs a medication from the patient's regimen and a supplier from list_medication_suppliers.
- Never medical advice; one patient per task.
""",
        examples=[
            "Hi, my email is <email>. Please move my appointment <appointment_id> with <provider name> to <date> at <time>.",
            "Hi, my email is <email>. Cancel appointment <appointment_id>, then book a follow-up with <provider_id> on <date> at <time>.",
        ],
    ),
    "bank": dict(
        user_id="the client's EMAIL (contact.email), from get_client_candidates / get_client_details",
        finder="get_client_candidates (account_status, min_active_accounts_same_currency, min_available_balance, card_status, beneficiary_status, beneficiary_verification, loan_status, ...)",
        rules="""
- initiate_internal_transfer: both accounts of the client, both active, source not credit, same currency, amount <= source available (get_account_details).
- initiate_transfer_to_beneficiary: beneficiary of the client, status active AND verification verified (one added in this task is pending -> unusable); source active, in allowed_from_account_ids, amount <= per_transfer_limit and <= available.
- make_loan_payment: the client's loan (get_loan_details); active source with available >= amount.
- freeze/unfreeze: account active<->frozen, card active<->blocked; closed/expired never reopen. A transfer FROM a frozen account fails -- unfreeze first or use another account.
- add_beneficiary: every schema field; allowed_from_account_ids are the client's.
""",
        examples=[
            "Hi, I'm <email>. Move <amount> <currency> from my checking <account_id> to my savings <account_id>.",
            "Hi, this is <email>. My debit card <card_id> was lost -- freeze it, then show my recent transactions on <account_id>.",
        ],
    ),
    "basketball": dict(
        user_id="the player's EMAIL, from get_player_candidates / get_player_details",
        finder="get_player_candidates (game_status, has_updatable_game, min_total_points, min_games, ...)",
        rules="""
- update_game_status: only scheduled->in_progress, scheduled->postponed, postponed->scheduled, in_progress->final; final is terminal.
- record_scoring_event: the game must be in_progress at that step (if the trace sets a game to final before scoring, score in a DIFFERENT in_progress game); club_id is that game's home or away club; player on that club's roster (list_club_roster_ids); 2PT=2, 3PT=3, FT=1; timestamp like "Q2 03:21".
- modify_player_address: the authenticated player only; all five address fields.
- Season strings look like "2024-25".
""",
        examples=[
            "Hi, I'm <email> (player <player_id>). Game <game_id> tipped off -- set it to in_progress and record my 3-pointer for <club_id> at Q1 09:12.",
            "Hi, this is <email>. Update my address to <street>, <city>, <state>, <country>, <zip>.",
        ],
    ),
    "movie": dict(
        user_id="the customer's EMAIL (customer.email inside the booking), from get_booking_candidates / get_booking_details",
        finder="get_booking_candidates (booking_status, min_customer_bookings, delivery_method, payment_source, ...) and get_show_candidates",
        rules="""
- create_booking: show scheduled; seats from get_seat_availability(theater_id, show_id).available (no wheelchair seats unless asked); the same customer's name/email/phone; delivery e-ticket|kiosk|box-office; payments sum EXACTLY to price_preview(...).grand_total for the same seats/concessions. The new booking id is minted by the tool -- never reference it.
- update_booking_seats: booking must be confirmed (one this task cancels is unusable -- take the customer's OTHER confirmed booking: min_customer_bookings=2); seats free for THAT booking's show; call preview_seat_update(booking_id, seats) and pass payment with exactly requires_additional_payment when > 0.
- cancel_booking: any confirmed/pending booking; refunds the amount paid.
- Showtime, theater, delivery, customer info and promotions cannot be changed.
""",
        examples=[
            "Hi, I'm <email>. Please cancel my booking <booking_id>.",
            "Hi, this is <email>. For booking <booking_id> change my seats to <seat_id> and <seat_id>; I'll pay any difference by card.",
        ],
    ),
    "school": dict(
        user_id="the student's EMAIL, from get_student_candidates / get_student_details",
        finder="get_student_candidates (registration_term, min_registrations, min_registered_courses, min_payment_methods, ...) and search_courses(term, compatible_with_registration_id=..., open_only=true)",
        rules="""
- register_courses: one term, no full course, no weekly-meeting conflict; total due = credits x rate (undergraduate 500, graduate 800, continuing_ed 400) per course + 300 if health insurance; payments from saved methods sum exactly to it.
- update_registration_courses: the student's registration; adds from search_courses(term, compatible_with_registration_id=<registration_id>, open_only=true); term unchanged; tuition increase needs one saved payment_id, decrease is refunded.
- cancel_registration: drops all courses, refunds all payments; afterwards that registration is unusable -- use another (min_registrations=2).
- get_course_meeting_status: a date the course actually meets.
""",
        examples=[
            "Hi, I'm <email> (student <student_id>). Add course <course_id> to my registration <registration_id>; charge the difference to <payment_id>.",
            "Hi, this is <email>. Cancel my registration <registration_id> and refund my payments.",
        ],
    ),
    "travel": dict(
        user_id="the traveler's EMAIL (contact.email), from get_traveler_candidates / get_traveler_details",
        finder="get_traveler_candidates (has_booking, min_bookings, has_saved_payment_method, can_update_add_ons, can_change_departure_date, min_travelers_in_booking, ...)",
        rules="""
- book_package: departure status available with available_slots >= travelers; payments sum EXACTLY to preview_booking_price(package_id, departure_date, num_travelers, add_ons, insurance).total_price; each payment_id is a saved method of the traveler. The booking id is minted by the tool -- never reference it.
- update_booking_departure_date: same package, new departure available with slots for all travelers; one payment_method_id for the delta.
- update_booking_add_ons: replaces the list; the booking's departure must still be available (can_update_add_ons=true); one payment_method_id for the delta.
- update_booking_travelers: SAME traveler count, names/dob only (min_travelers_in_booking=2 to rename a companion). update_booking_rooming: any booking.
- cancel_booking: per get_package_details policies; refunds every payment.
- schedule_agent_meeting: an agent managing the package, on a date/time_range listed in get_agent_details availability.
""",
        examples=[
            "Hi, I'm <email> (traveler <traveler_id>). Move booking <booking_id> to the <date> departure; charge the difference to <payment_method_id>.",
            "Hi, this is <email>. Book package <package_id> departing <date> for 2 travelers, double room, standard insurance, on <payment_method_id>.",
        ],
    ),
    "restaurant": dict(
        user_id="the patron's EMAIL (contact_email), from get_patron_candidates / get_patron_details",
        finder="get_patron_candidates (ticket_state, service_mode, min_placed_tickets, min_saved_instruments, has_tip_charge, has_alternate_plate_available, ...)",
        rules="""
- Only "placed" tickets can be cancelled or modified; one this task cancels is unusable afterwards -- use the patron's OTHER placed ticket (min_placed_tickets=2).
- modify_placed_ticket_dropoff: delivery tickets only (all address fields). modify_placed_ticket_table: dine_in tickets only.
- modify_placed_ticket_instrument: a DIFFERENT saved instrument of the patron (min_saved_instruments=2); do it BEFORE any items change (it needs exactly one payment charge).
- modify_placed_ticket_items: swap a plate for another served-today plate of the SAME dish (has_alternate_plate_available=true); difference charged to the given instrument.
- add_tip_to_ticket: any non-cancelled ticket, tip_total > 0, a saved instrument. cancel_placed_ticket needs a reason.
""",
        examples=[
            "Hi, I'm <email>. Please cancel my placed ticket <ticket_ref>; I ordered by mistake.",
            "Hi, this is <email>. Add a $<amount> tip to ticket <ticket_ref> with my card <instrument_ref>.",
        ],
    ),
}

SYSTEM_TEMPLATE = '''"""Task-generator prompt for the {domain} domain (scripts/taskgen/make_prompt.py v2 -- regenerate, do not hand-edit)."""

SYSTEM_PROMPT = """You turn a TOOL-TRACE from the {domain} customer-support environment into ONE realistic task: the user's instruction for each TURN, a short story, and the exact `actions` (tool name + kwargs) the support agent will execute. The trace's tools are the agent's; you cannot call them. You can only READ the current database through the reverse tools whose schemas follow. The task is accepted only if every action executes without error on the current data.

USER IDENTITY
user_id = {user_id}. Every instruction states it; it authenticates the user. One user for the whole task.

METHOD -- in this order
1. Read every tool in the trace and derive the preconditions its writes need (entity state, ownership, balance, capacity, how many entities of a kind). Call {finder} ONCE with every matching filter so ONE user satisfies all TURNs.
2. Read that user's records with the detail tools. Every id, amount, seat, slot and date in your output is copied from a tool result of this session -- never computed, guessed, taken from the trace, or from the examples.
3. One entity per write. If the trace cancels / finalizes an entity and a later tool modifies or reads one of the same kind, ask the finder for two of that kind (min_*=2 / a status listed twice): its row then names cancel_target and modify_target -- use exactly those two ids. Never act on an entity this task already cancelled; never reference an id that only exists after a write in this task.
4. Before any write with a price, seat, slot or balance, call the matching read-only preview / price / availability tool with the exact arguments you will use, and copy its numbers.
5. kwargs use only that tool's schema parameters, all required ones present.
6. `actions` lists ONLY the trace's tool calls. These reverse tools are for your lookups and must NEVER appear in `actions` (the agent cannot call them; replay fails with "Unknown action"): {reverse_names}. If a trace tool shares a name with a reverse tool, pass only the parameters of the TRACE schema.

DOMAIN CONSTRAINTS (write-tool preconditions; read tools are self-describing)
{rules}
OUTPUT -- respond with ONLY this JSON (action name "respond", arguments {{"content": <JSON>}})
{{"user_id": "...", "instructions": ["one string per TURN; each states the user_id and every id/value that TURN needs, as a natural request"], "story": "one paragraph tying the turns together", "actions": [{{"name": "<snake_case info.function.name>", "kwargs": {{...}}}}, ... one per trace tool call, flat, in trace order]}}
The <placeholders> in these examples do not exist -- never copy them:
{examples}
"""
'''

USER_TEMPLATE = '''
USER_PROMPT = """TOOL-TRACE ({domain}). N = number of TURNs = len(instructions). Ground it with the reverse tools, then respond with the JSON only.
<TOOL_TRACE>
{{trace}}
</TOOL_TRACE>
<VERIFIER_FEEDBACK>
{{feedback}}
</VERIFIER_FEEDBACK>
"""
'''


def build(domain: str) -> str:
    spec = SPEC[domain]
    rev = importlib.import_module(f"tracer.envs.{domain}.reverse_tools").ALL_TOOLS
    fwd = {
        t.get_info()["function"]["name"]
        for t in importlib.import_module(f"tracer.envs.{domain}.tools").ALL_TOOLS
    }
    reverse_only = [
        t.get_info()["function"]["name"]
        for t in rev
        if t.get_info()["function"]["name"] not in fwd
    ]
    system = SYSTEM_TEMPLATE.format(
        domain=domain,
        user_id=spec["user_id"],
        finder=spec["finder"],
        reverse_names=", ".join(reverse_only),
        rules=spec["rules"].strip("\n") + "\n",
        examples="\n".join(f'- "{e}"' for e in spec["examples"]),
    )
    return system + USER_TEMPLATE.format(domain=domain)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("domain", nargs="?")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--stdout", action="store_true")
    args = ap.parse_args()
    for d in sorted(SPEC) if args.all else [args.domain]:
        text = build(d)
        if args.stdout:
            print(text)
            continue
        out = REPO / "tracer" / "prompts" / f"task_generator_{d}.py"
        out.write_text(text, encoding="utf-8")
        print(f"wrote {out.name}  ({len(text)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
