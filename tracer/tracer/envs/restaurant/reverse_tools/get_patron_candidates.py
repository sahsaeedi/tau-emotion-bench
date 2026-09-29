import json
import random
from typing import Any, Dict, List, Optional

from tracer.envs.tool import Tool

# Max number of patrons to return per call (paginated batch)
_MAX_PATRONS = 5

# Call counter: each invoke returns the "next" batch so subsequent calls get different patrons
_call_counter = 0


def _patron_tickets(
    patron: Dict[str, Any], service_tickets: Dict[str, Any]
) -> List[Dict[str, Any]]:
    return [
        service_tickets[ref]
        for ref in patron.get("ticket_log", [])
        if ref in service_tickets
    ]


def _dishes_with_alternate_plate(menu_board: Dict[str, Any]) -> set:
    """dish_refs offering 2+ plate selections that are served_today.

    Only these dishes can ever back a modify_placed_ticket_items call: a replacement
    plate must belong to the SAME dish as the original and must be served_today.
    """
    refs = set()
    for dish in menu_board.values():
        available = sum(
            1 for s in dish.get("selections", {}).values() if s.get("served_today")
        )
        if available >= 2:
            refs.add(dish.get("dish_ref"))
    return refs


def _has_charge_kind(ticket: Dict[str, Any], kind: str) -> bool:
    return any(ch.get("kind") == kind for ch in ticket.get("charges", []))


def _ticket_has_alternate_plate(ticket: Dict[str, Any], alt_dish_refs: set) -> bool:
    return any(
        le.get("dish_ref") in alt_dish_refs for le in ticket.get("line_entries", [])
    )


def _ticket_matches(
    ticket: Dict[str, Any],
    alt_dish_refs: set,
    ticket_state: Optional[str],
    service_mode: Optional[str],
    has_tip_charge: Optional[bool],
    min_line_entries: Optional[int],
    has_alternate_plate_available: Optional[bool],
) -> bool:
    if ticket_state is not None and ticket.get("state") != ticket_state:
        return False
    if service_mode is not None and ticket.get("service_mode") != service_mode:
        return False
    if has_tip_charge is not None and bool(has_tip_charge) != _has_charge_kind(
        ticket, "tip"
    ):
        return False
    if min_line_entries is not None:
        try:
            if len(ticket.get("line_entries", [])) < int(min_line_entries):
                return False
        except (TypeError, ValueError):
            pass
    if has_alternate_plate_available is not None:
        if bool(has_alternate_plate_available) != _ticket_has_alternate_plate(
            ticket, alt_dish_refs
        ):
            return False
    return True


class GetPatronCandidates(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        ticket_state: Optional[str] = None,
        service_mode: Optional[str] = None,
        has_tip_charge: Optional[bool] = None,
        min_line_entries: Optional[int] = None,
        has_alternate_plate_available: Optional[bool] = None,
        min_tickets: Optional[int] = None,
        min_placed_tickets: Optional[int] = None,
        min_saved_instruments: Optional[int] = None,
        instrument_origin: Optional[str] = None,
    ) -> str:
        global _call_counter

        patrons: Dict[str, Any] = data.get("patron_registry") or {}
        service_tickets: Dict[str, Any] = data.get("service_tickets") or {}
        menu_board: Dict[str, Any] = data.get("menu_board") or {}

        alt_dish_refs = _dishes_with_alternate_plate(menu_board)

        candidates: List[Dict[str, Any]] = []

        for guest_ref, patron in patrons.items():
            tickets = _patron_tickets(patron, service_tickets)
            instruments = patron.get("saved_instruments", {})

            if min_tickets is not None:
                try:
                    if len(tickets) < int(min_tickets):
                        continue
                except (TypeError, ValueError):
                    pass
            if min_placed_tickets is not None:
                try:
                    if sum(1 for t in tickets if t.get("state") == "placed") < int(
                        min_placed_tickets
                    ):
                        continue
                except (TypeError, ValueError):
                    pass
            if min_saved_instruments is not None:
                try:
                    if len(instruments) < int(min_saved_instruments):
                        continue
                except (TypeError, ValueError):
                    pass
            if instrument_origin is not None and not any(
                i.get("origin") == instrument_origin for i in instruments.values()
            ):
                continue

            matching_tickets = [
                t
                for t in tickets
                if _ticket_matches(
                    t,
                    alt_dish_refs,
                    ticket_state,
                    service_mode,
                    has_tip_charge,
                    min_line_entries,
                    has_alternate_plate_available,
                )
            ]
            if not matching_tickets:
                continue

            # two DIFFERENT placed tickets: the one matching the caller's filters goes to
            # the write with the most preconditions, any OTHER placed ticket is the one to
            # cancel (cancel_placed_ticket only checks state == placed)
            pair: Dict[str, Any] = {}
            want_pair = min_placed_tickets is not None and int(min_placed_tickets) >= 2
            if sum(1 for t in tickets if t.get("state") == "placed") >= 2:
                modify = matching_tickets[0]
                cancel = next(
                    (
                        t
                        for t in sorted(tickets, key=lambda x: x.get("ticket_ref", ""))
                        if t.get("state") == "placed"
                        and t.get("ticket_ref") != modify.get("ticket_ref")
                    ),
                    None,
                )
                if cancel is None and want_pair:
                    continue
                pair = (
                    {}
                    if cancel is None
                    else {
                        "modify_target": {
                            "ticket_ref": modify.get("ticket_ref"),
                            "state": "placed",
                            "service_mode": modify.get("service_mode"),
                            "why": "matches your ticket filters; placed -> modify_placed_ticket_* accepts it",
                        },
                        "cancel_target": {
                            "ticket_ref": cancel.get("ticket_ref"),
                            "state": "placed",
                            "service_mode": cancel.get("service_mode"),
                            "why_cancellable": "another placed ticket of this patron",
                        },
                    }
                )

            identity = patron.get("identity", {})
            display_name = (
                " ".join(
                    p for p in [identity.get("given"), identity.get("family")] if p
                ).strip()
                or "Unknown"
            )
            candidates.append(
                {
                    **pair,
                    "guest_ref": guest_ref,
                    "name": display_name,
                    "contact_email": patron.get("contact_email", ""),
                    "postal_code": patron.get("location", {}).get("postal_code", ""),
                    "num_saved_instruments": len(instruments),
                    "num_tickets": len(tickets),
                    "matching_tickets": [
                        {
                            "ticket_ref": t.get("ticket_ref"),
                            "state": t.get("state"),
                            "service_mode": t.get("service_mode"),
                            "num_line_entries": len(t.get("line_entries", [])),
                            "has_tip_charge": _has_charge_kind(t, "tip"),
                            "has_alternate_plate_available": _ticket_has_alternate_plate(
                                t, alt_dish_refs
                            ),
                        }
                        for t in matching_tickets
                    ],
                }
            )

        random.shuffle(candidates)
        total = len(candidates)
        if total == 0:
            return json.dumps(
                {"total_matching": 0, "returned_count": 0, "patrons": []}, indent=2
            )

        offset = (_call_counter * _MAX_PATRONS) % total
        _call_counter += 1
        doubled = candidates + candidates
        batch = doubled[offset : offset + _MAX_PATRONS]

        payload = {
            "total_matching": total,
            "returned_count": len(batch),
            "patrons": batch,
        }
        return json.dumps(payload, indent=2)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_patron_candidates",
                "description": (
                    "Read-only roster of patrons matching zero or more filters, for finding a real patron whose "
                    "data already satisfies a scenario precondition (e.g. a patron with a delivery ticket still in "
                    "'placed' state, so its dropoff address can actually be modified). All filter parameters are "
                    "optional; when a filter is omitted, no constraint is applied for that field. Filters combine "
                    "with AND semantics — a patron must satisfy every filter provided to match — and the "
                    "ticket-level filters (ticket_state, service_mode, has_tip_charge, min_line_entries, "
                    "has_alternate_plate_available) must all be satisfied by the SAME ticket, so a match is always "
                    "a genuinely actionable ticket rather than two unrelated ones. Returns concise summaries "
                    "(guest_ref, name, contact_email, postal_code, instrument/ticket counts, and a per-ticket "
                    "summary of the tickets that matched), not full records — use get_patron_details, "
                    "get_ticket_details and get_dish_details for full details once a candidate guest_ref is chosen. "
                    f"The list is randomized; each call returns the next batch (up to {_MAX_PATRONS} patrons, "
                    "different from previous calls)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticket_state": {
                            "type": "string",
                            "enum": [
                                "placed",
                                "in_progress",
                                "ready",
                                "delivered",
                                "cancelled",
                            ],
                            "description": (
                                "If set, only patrons owning at least one ticket in this state. Every write tool "
                                "except add_tip_to_ticket (cancel_placed_ticket, modify_placed_ticket_dropoff / "
                                "_table / _items / _instrument) rejects any ticket not in 'placed', so use 'placed' "
                                "to ground those tasks. Only 28% of tickets are 'placed' (the rest are "
                                "'in_progress', 'delivered' or 'ready'), so omitting this filter usually yields a "
                                "ticket the write tool will refuse. Use a non-'placed' state to ground a scenario "
                                "where the agent must correctly DENY a modification request."
                            ),
                        },
                        "service_mode": {
                            "type": "string",
                            "enum": ["delivery", "dine_in", "takeout"],
                            "description": (
                                "If set, only patrons owning at least one ticket with this service mode (the same "
                                "ticket that satisfies the other ticket-level filters). modify_placed_ticket_dropoff "
                                "works only on 'delivery' tickets and modify_placed_ticket_table only on 'dine_in' "
                                "tickets, so pair this with ticket_state='placed' when grounding either. Note no "
                                "single patron owns both a placed delivery ticket and a placed dine_in ticket, so a "
                                "task combining both modifications cannot be grounded in real data."
                            ),
                        },
                        "has_tip_charge": {
                            "type": "boolean",
                            "description": (
                                "If set, only patrons owning a matching ticket that already carries (True) or does "
                                "not carry (False) a 'tip' charge. Use False to ground a natural add_tip_to_ticket "
                                "task on a ticket with no tip yet; use True for a story about an already-tipped "
                                "ticket (e.g. adding a second tip, or asking about an existing one)."
                            ),
                        },
                        "min_line_entries": {
                            "type": "integer",
                            "description": (
                                "If set, only patrons owning a matching ticket with at least this many line "
                                "entries. Use 2 to ground a multi-plate story (e.g. swapping or asking about "
                                "several plates in one ticket); note only 3% of tickets have more than one entry."
                            ),
                        },
                        "has_alternate_plate_available": {
                            "type": "boolean",
                            "description": (
                                "If set, only patrons owning a matching ticket whose line entries reference a dish "
                                "that offers two or more plate selections served_today (True), or none (False). "
                                "modify_placed_ticket_items requires the replacement plate to belong to the SAME "
                                "dish as the original and to be served_today, so a ticket with False here can never "
                                "be modified. Almost every dish on the menu has a single plate selection, so True "
                                "matches only about 1% of patrons."
                            ),
                        },
                        "min_tickets": {
                            "type": "integer",
                            "description": (
                                "If set, only patrons with at least this many tickets in their ticket_log. Use 2 to "
                                "ground a multi-intent task that touches two different tickets; only ~3.5% of "
                                "patrons have more than one ticket."
                            ),
                        },
                        "min_placed_tickets": {
                            "type": "integer",
                            "description": (
                                "If set, only patrons with at least this many tickets in 'placed' state. Use 2 to "
                                "ground a task applying two different modifications to two different modifiable "
                                "tickets — but note no patron in the data currently has two placed tickets, so such "
                                "a task must instead target a single placed ticket."
                            ),
                            "pair_note": "With 2 or more, each row also carries modify_target (ticket matching your other filters) and cancel_target (a DIFFERENT placed ticket) -- copy those two ids into the two writes.",
                        },
                        "min_saved_instruments": {
                            "type": "integer",
                            "description": (
                                "If set, only patrons with at least this many saved payment instruments. "
                                "modify_placed_ticket_instrument requires the new instrument_ref to be saved on the "
                                "patron AND different from the one on the current payment charge, so it needs 2 "
                                "here — and no patron in the data has more than one saved instrument, meaning that "
                                "tool cannot be grounded in a successful outcome for any real patron."
                            ),
                        },
                        "instrument_origin": {
                            "type": "string",
                            "enum": ["credit_card", "mobile_money"],
                            "description": (
                                "If set, only patrons with at least one saved payment instrument of this origin. "
                                "Useful when the story should name the payment method naturally (e.g. 'charge it to "
                                "my mobile wallet'); nearly all saved instruments are 'credit_card'."
                            ),
                        },
                    },
                    "required": [],
                },
            },
        }
