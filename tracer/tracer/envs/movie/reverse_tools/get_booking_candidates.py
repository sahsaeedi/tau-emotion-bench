import json
import random
from typing import Any, Dict, List, Optional, Set, Tuple

from tracer.envs.tool import Tool

# Max number of bookings to return per call (paginated batch)
_MAX_BOOKINGS = 5

# Call counter: each invoke returns the "next" batch so subsequent calls get different bookings
_call_counter = 0


def _find_show(
    data: Dict[str, Any], theater_id: str, show_id: str
) -> Tuple[Optional[dict], Optional[str]]:
    """Find a show by ID in a given theater, searching across all dates.

    Returns (show, date) - both None if not found.
    """
    theater = data.get("theaters", {}).get(theater_id)
    if theater is None:
        return None, None
    for d, day in (theater.get("dates") or {}).items():
        for show in day.get("shows", []):
            if show.get("show_id") == show_id:
                return show, d
    return None, None


def _list_all_seat_ids(auditorium: Dict[str, Any]) -> Set[str]:
    seat_ids: Set[str] = set()
    for seats in auditorium.get("seat_map", {}).get("rows", {}).values():
        for seat in seats:
            seat_ids.add(seat["seat_id"])
    return seat_ids


def _list_wheelchair_seat_ids(auditorium: Dict[str, Any]) -> Set[str]:
    seat_ids: Set[str] = set()
    for seats in auditorium.get("seat_map", {}).get("rows", {}).values():
        for seat in seats:
            if seat.get("wheelchair_accessible"):
                seat_ids.add(seat["seat_id"])
    return seat_ids


def _booked_seats_for_show(
    data: Dict[str, Any], theater_id: str, show_id: str
) -> Set[str]:
    """Seats already booked for this show (only confirmed bookings count)."""
    seat_ids: Set[str] = set()
    for booking in data.get("bookings", {}).values():
        if (
            booking.get("theater_id") == theater_id
            and booking.get("show_id") == show_id
        ):
            if booking.get("status") == "confirmed":
                for s in booking.get("seats", []):
                    seat_ids.add(s["seat_id"])
    return seat_ids


def _ticket_types(booking: Dict[str, Any]) -> Set[str]:
    return {s.get("ticket_type") for s in booking.get("seats", [])}


def _has_refund_entry(booking: Dict[str, Any]) -> bool:
    return any(
        float(p.get("amount", 0)) < 0 for p in booking.get("payment_history", [])
    )


def _payment_sources(booking: Dict[str, Any]) -> Set[str]:
    return {
        (p.get("method") or {}).get("source")
        for p in booking.get("payment_history", [])
    }


def _amount_due(booking: Dict[str, Any]) -> float:
    try:
        return round(float((booking.get("totals") or {}).get("amount_due", 0)), 2)
    except (TypeError, ValueError):
        return 0.0


class GetBookingCandidates(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        booking_status: Optional[str] = None,
        show_status: Optional[str] = None,
        min_seats: Optional[int] = None,
        ticket_type: Optional[str] = None,
        has_mixed_ticket_types: Optional[bool] = None,
        holds_wheelchair_seat: Optional[bool] = None,
        min_free_seats_on_show: Optional[int] = None,
        has_concessions: Optional[bool] = None,
        has_promotions_applied: Optional[bool] = None,
        has_loyalty_id: Optional[bool] = None,
        has_refund_entry: Optional[bool] = None,
        has_amount_due: Optional[bool] = None,
        delivery_method: Optional[str] = None,
        payment_source: Optional[str] = None,
        min_customer_bookings: Optional[int] = None,
    ) -> str:
        global _call_counter

        bookings: Dict[str, Any] = data.get("bookings") or {}
        theaters: Dict[str, Any] = data.get("theaters") or {}
        movies: Dict[str, Any] = data.get("movies") or {}

        candidates: List[Dict[str, Any]] = []
        # bookings per customer email, restricted to booking_status when given, so
        # "a customer with two confirmed bookings" is one filter (bookings are the
        # unit here; without this a customer's second booking is invisible)
        per_customer: Dict[str, int] = {}
        for b in bookings.values():
            if booking_status is None or b.get("status") == booking_status:
                e = (b.get("customer") or {}).get("email", "")
                per_customer[e] = per_customer.get(e, 0) + 1

        for booking_id, booking in bookings.items():
            if booking_status is not None and booking.get("status") != booking_status:
                continue
            if min_customer_bookings is not None and per_customer.get(
                (booking.get("customer") or {}).get("email", ""), 0
            ) < int(min_customer_bookings):
                continue

            theater_id = booking.get("theater_id")
            show_id = booking.get("show_id")
            show, show_date = _find_show(data, theater_id, show_id)

            if show_status is not None:
                if show is None or show.get("status") != show_status:
                    continue

            seats = booking.get("seats", [])
            if min_seats is not None:
                try:
                    if len(seats) < int(min_seats):
                        continue
                except (TypeError, ValueError):
                    pass

            types = _ticket_types(booking)
            if ticket_type is not None and ticket_type not in types:
                continue
            if has_mixed_ticket_types is not None and bool(len(types) > 1) != bool(
                has_mixed_ticket_types
            ):
                continue

            # Seat-map derived facts require resolving the show's auditorium.
            theater = theaters.get(theater_id) or {}
            auditorium = (theater.get("auditoriums") or {}).get(
                show.get("auditorium_id") if show else None
            )
            held_seat_ids = {s.get("seat_id") for s in seats}
            wheelchair_ids = (
                _list_wheelchair_seat_ids(auditorium) if auditorium else set()
            )
            holds_wc = bool(held_seat_ids & wheelchair_ids)
            if holds_wheelchair_seat is not None and holds_wc != bool(
                holds_wheelchair_seat
            ):
                continue

            free_regular = 0
            if auditorium is not None:
                all_ids = _list_all_seat_ids(auditorium)
                booked_ids = _booked_seats_for_show(data, theater_id, show_id)
                free_regular = len((all_ids - booked_ids) - wheelchair_ids)
            if min_free_seats_on_show is not None:
                try:
                    if free_regular < int(min_free_seats_on_show):
                        continue
                except (TypeError, ValueError):
                    pass

            if has_concessions is not None and bool(booking.get("concessions")) != bool(
                has_concessions
            ):
                continue
            if has_promotions_applied is not None and bool(
                booking.get("promotions_applied")
            ) != bool(has_promotions_applied):
                continue

            customer = booking.get("customer") or {}
            if has_loyalty_id is not None and bool(customer.get("loyalty_id")) != bool(
                has_loyalty_id
            ):
                continue

            if has_refund_entry is not None and _has_refund_entry(booking) != bool(
                has_refund_entry
            ):
                continue

            due = _amount_due(booking)
            if has_amount_due is not None and bool(due > 0) != bool(has_amount_due):
                continue

            if (
                delivery_method is not None
                and (booking.get("delivery") or {}).get("method") != delivery_method
            ):
                continue

            if payment_source is not None and payment_source not in _payment_sources(
                booking
            ):
                continue

            name = customer.get("name", {})
            display_name = (
                " ".join(
                    p for p in [name.get("first_name"), name.get("last_name")] if p
                ).strip()
                or "Unknown"
            )
            movie = movies.get(booking.get("movie_id")) or {}
            pair: Dict[str, Any] = {}
            want_pair = (
                min_customer_bookings is not None and int(min_customer_bookings) >= 2
            )
            if True:
                email = (booking.get("customer") or {}).get("email", "")
                other = next(
                    (
                        oid
                        for oid in sorted(bookings)
                        if oid != booking_id
                        and (bookings[oid].get("customer") or {}).get("email", "")
                        == email
                        and bookings[oid].get("status") in ("confirmed", "pending")
                    ),
                    None,
                )
                if other is None and want_pair:
                    continue
                pair = (
                    {}
                    if other is None
                    else {
                        "modify_target": {
                            "booking_id": booking_id,
                            "status": booking.get("status"),
                            "why": "this row matches your filters; confirmed -> update_booking_seats accepts it",
                        },
                        "cancel_target": {
                            "booking_id": other,
                            "status": bookings[other].get("status"),
                            "why_cancellable": "another confirmed/pending booking of the same customer",
                        },
                    }
                )
            candidates.append(
                {
                    **pair,
                    "booking_id": booking_id,
                    "status": booking.get("status"),
                    "customer_name": display_name,
                    "customer_email": customer.get("email", ""),
                    "theater_id": theater_id,
                    "theater_name": theater.get("name", ""),
                    "movie_id": booking.get("movie_id"),
                    "movie_title": movie.get("title", ""),
                    "show_id": show_id,
                    "show_status": show.get("status") if show else None,
                    "date": booking.get("date") or show_date,
                    "start_time_local": booking.get("start_time_local"),
                    "num_seats": len(seats),
                    "seat_ids": sorted(s for s in held_seat_ids if s),
                    "ticket_types": sorted(t for t in types if t),
                    "holds_wheelchair_seat": holds_wc,
                    "free_regular_seats_on_show": free_regular,
                    "has_concessions": bool(booking.get("concessions")),
                    "has_promotions_applied": bool(booking.get("promotions_applied")),
                    "grand_total": (booking.get("totals") or {}).get("grand_total"),
                    "amount_due": due,
                    "delivery_method": (booking.get("delivery") or {}).get("method"),
                }
            )

        random.shuffle(candidates)
        total = len(candidates)
        if total == 0:
            return json.dumps(
                {"total_matching": 0, "returned_count": 0, "bookings": []}, indent=2
            )

        offset = (_call_counter * _MAX_BOOKINGS) % total
        _call_counter += 1
        doubled = candidates + candidates
        batch = doubled[offset : offset + _MAX_BOOKINGS]

        payload = {
            "total_matching": total,
            "returned_count": len(batch),
            "bookings": batch,
        }
        return json.dumps(payload, indent=2)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_booking_candidates",
                "description": (
                    "Read-only roster of existing bookings matching zero or more filters, for finding a real "
                    "booking whose data already satisfies a scenario precondition (e.g. a confirmed booking on a "
                    "scheduled show that can legitimately have its seats changed, or a booking that already "
                    "carries a refund entry). This domain has no customer-profile lookup — a booking can only be "
                    "reached by its booking_id — so this tool is the only way to obtain a booking_id that really "
                    "exists before writing a story around it. All filter parameters are optional; when a filter is "
                    "omitted, no constraint is applied for that field. Filters combine with AND semantics — a "
                    "booking must satisfy every filter provided to match. Returns concise summaries (booking_id, "
                    "status, customer name/email, theater/movie/show ids, seat ids, ticket types and totals), not "
                    "full records — use get_booking_details for the full record once a candidate booking_id is "
                    "chosen. The list is randomized; each call returns the next batch "
                    f"(up to {_MAX_BOOKINGS} bookings, different from previous calls)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "booking_status": {
                            "type": "string",
                            "enum": ["confirmed", "pending", "canceled", "refunded"],
                            "description": (
                                "If set, only bookings in this status. update_booking_seats accepts ONLY "
                                "'confirmed' bookings, and cancel_booking rejects bookings already 'canceled' or "
                                "'refunded', so use 'confirmed' to ground a task that must succeed. Use 'pending' "
                                "or 'refunded' to ground a task that must legitimately be refused. Note: the "
                                "current dataset contains confirmed, pending and refunded bookings but no "
                                "'canceled' ones."
                            ),
                        },
                        "show_status": {
                            "type": "string",
                            "enum": ["scheduled", "canceled", "completed"],
                            "description": (
                                "If set, only bookings whose associated show is in this status. Both booking and "
                                "show preconditions matter: update_booking_seats requires the show to be "
                                "'scheduled', and cancel_booking may only be used when the show is 'scheduled' or "
                                "'canceled' by the theater (a 'completed' show must be transferred to a human "
                                "agent). Note: every show in the current dataset is 'scheduled', so filtering on "
                                "'canceled' or 'completed' returns nothing — do not build a story around a show "
                                "the theater canceled or already screened."
                            ),
                        },
                        "min_seats": {
                            "type": "integer",
                            "description": (
                                "If set, only bookings holding at least this many seats. Use 2 or more to ground a "
                                "partial cancellation, which the policy handles as a seat REDUCTION via "
                                "update_booking_seats (and which therefore needs a booking with a seat to spare)."
                            ),
                        },
                        "ticket_type": {
                            "type": "string",
                            "enum": ["adult", "child", "senior"],
                            "description": (
                                "If set, only bookings holding at least one seat of this ticket type. Useful for "
                                "grounding a story in the customer's own words, e.g. 'the child ticket for my "
                                "daughter' or 'my father's senior ticket'."
                            ),
                        },
                        "has_mixed_ticket_types": {
                            "type": "boolean",
                            "description": (
                                "If set, selects bookings that do (True) or do not (False) mix ticket types across "
                                "their seats. True grounds a seat update that only changes a ticket_type (e.g. "
                                "'one of those adult tickets should have been a senior')."
                            ),
                        },
                        "holds_wheelchair_seat": {
                            "type": "boolean",
                            "description": (
                                "If set, selects bookings that do (True) or do not (False) currently hold a "
                                "wheelchair-accessible seat. Policy forbids assigning wheelchair-accessible seats "
                                "unless the user explicitly requests them, so True grounds a scenario where the "
                                "accessible seat was genuinely requested."
                            ),
                        },
                        "min_free_seats_on_show": {
                            "type": "integer",
                            "description": (
                                "If set, only bookings whose show still has at least this many free "
                                "NON-wheelchair-accessible seats. A seat INCREASE via update_booking_seats "
                                "requires the new seats to be available, so set this to the number of seats the "
                                "story wants to add."
                            ),
                        },
                        "has_concessions": {
                            "type": "boolean",
                            "description": (
                                "If set, selects bookings that do (True) or do not (False) include concession "
                                "items. Concessions cannot be changed by any tool after booking, so True grounds a "
                                "request the agent must refuse."
                            ),
                        },
                        "has_promotions_applied": {
                            "type": "boolean",
                            "description": (
                                "If set, selects bookings that do (True) or do not (False) carry an applied "
                                "promotion. Promotions and coupons are not supported by the tools for creation or "
                                "update, so True grounds a story where the customer asks about a discount the "
                                "agent cannot reapply or modify."
                            ),
                        },
                        "has_loyalty_id": {
                            "type": "boolean",
                            "description": (
                                "If set, selects bookings whose customer does (True) or does not (False) have a "
                                "loyalty_id on file. Useful for grounding how the customer identifies themselves."
                            ),
                        },
                        "has_refund_entry": {
                            "type": "boolean",
                            "description": (
                                "If set, selects bookings whose payment_history does (True) or does not (False) "
                                "already contain a negative (refund) amount. True grounds a follow-up story about "
                                "a refund that has already been issued."
                            ),
                        },
                        "has_amount_due": {
                            "type": "boolean",
                            "description": (
                                "If set, selects bookings whose totals show an outstanding amount_due greater than "
                                "zero (True) or fully paid (False). For new bookings payments must sum exactly to "
                                "the grand total, so True grounds a story about a booking that was never fully "
                                "settled."
                            ),
                        },
                        "delivery_method": {
                            "type": "string",
                            "enum": ["e-ticket", "box-office", "kiosk"],
                            "description": (
                                "If set, only bookings using this delivery method. Delivery method cannot be "
                                "changed by any tool after booking, so this grounds both ticket-collection stories "
                                "and requests the agent must refuse."
                            ),
                        },
                        "payment_source": {
                            "type": "string",
                            "enum": ["card", "wallet", "cash", "gift_card"],
                            "description": (
                                "If set, only bookings with at least one payment from this source. Cancellations "
                                "and seat reductions issue refunds against the original payment, so this grounds "
                                "questions about how the money comes back."
                            ),
                        },
                        "min_customer_bookings": {
                            "type": "integer",
                            "description": (
                                "If set, only bookings whose customer (same email) holds at least this many bookings, "
                                "counted within booking_status when that filter is given. Use 2 with "
                                "booking_status='confirmed' when the trace cancels one booking and then updates the "
                                "seats of another: the row then carries modify_target (this booking) and "
                                "cancel_target (a DIFFERENT booking of the same customer) -- copy both ids."
                            ),
                        },
                    },
                    "required": [],
                },
            },
        }
