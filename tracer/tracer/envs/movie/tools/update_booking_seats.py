import json
from typing import Any, Dict, List, Optional, Set, Tuple

from tracer.envs.tool import Tool


def _find_show(
    data: Dict[str, Any], theater_id: str, show_id: str
) -> Tuple[Optional[dict], Optional[str], Optional[str]]:
    """Find a show by ID in a given theater, searching across all dates.

    Returns (show, date, error) - show and date are None if error is set.
    """
    theater = data["theaters"].get(theater_id)
    if theater is None:
        return None, None, f"Error: Theater {theater_id} not found"
    for d, day in theater["dates"].items():
        for show in day["shows"]:
            if show["show_id"] == show_id:
                return show, d, None
    return None, None, f"Error: Show {show_id} not found at theater {theater_id}"


def _list_all_seat_ids(auditorium: Dict[str, Any]) -> Set[str]:
    seat_ids: Set[str] = set()
    for seats in auditorium["seat_map"]["rows"].values():
        for seat in seats:
            seat_ids.add(seat["seat_id"])
    return seat_ids


def _booked_seats_for_show(
    data: Dict[str, Any], theater_id: str, show_id: str
) -> Set[str]:
    """Seats already booked for this show (only confirmed bookings count)."""
    seat_ids: Set[str] = set()
    for booking in data["bookings"].values():
        if booking["theater_id"] == theater_id and booking["show_id"] == show_id:
            if booking["status"] == "confirmed":
                for s in booking["seats"]:
                    seat_ids.add(s["seat_id"])
    return seat_ids


def _per_ticket_price(
    price_schema: Dict[str, Any], ticket_type: str
) -> Optional[float]:
    if ticket_type == "adult":
        return float(price_schema["adult"])
    if ticket_type == "child":
        return float(price_schema["child"])
    if ticket_type == "senior":
        return float(price_schema["senior"])
    return None


def _build_booked_seats(
    show: Dict[str, Any], theater: Dict[str, Any], seat_specs: List[dict]
) -> List[dict]:
    """Build seat entries with computed price, convenience_fee, tax."""
    tax_rate = float(theater["pricing_rules"]["tax_rate_percent"]) / 100.0
    per_ticket_fee = float(show["price_schema"]["fees"]["convenience_fee"])

    booked: List[dict] = []
    for spec in seat_specs:
        seat_id = spec["seat_id"]
        tt = spec["ticket_type"]
        price = _per_ticket_price(show["price_schema"], tt)
        fee = per_ticket_fee
        tax = (price + fee) * tax_rate
        booked.append(
            {
                "seat_id": seat_id,
                "ticket_type": tt,
                "price": round(price, 2),
                "convenience_fee": round(fee, 2),
                "tax": round(tax, 2),
            }
        )
    return booked


def _sum_concessions_subtotal_and_tax(items: List[dict]) -> Tuple[float, float]:
    subtotal = 0.0
    tax_total = 0.0
    for i in items:
        subtotal += i["price_each"] * i["quantity"]
        tax_total += i["tax_each"] * i["quantity"]
    return round(subtotal, 2), round(tax_total, 2)


class UpdateBookingSeatsTool(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        booking_id: str,
        seats: List[dict],
        payment: Optional[dict] = None,
    ) -> str:
        booking = data["bookings"].get(booking_id)
        if booking is None:
            return f"Error: Booking {booking_id} not found"
        theater = data["theaters"].get(booking["theater_id"])
        if theater is None:
            return f"Error: Theater {booking['theater_id']} not found"
        show, _, err = _find_show(data, booking["theater_id"], booking["show_id"])
        if err:
            return err
        if booking["status"] != "confirmed":
            return f"Error: Only confirmed bookings can be updated (status={booking['status']})"
        if show["status"] != "scheduled":
            return f"Error: Show {booking['show_id']} is not bookable (status={show['status']})"

        auditorium = theater["auditoriums"].get(show["auditorium_id"])
        if auditorium is None:
            return f"Error: Auditorium {show['auditorium_id']} not found at theater {booking['theater_id']}"

        new_seat_ids = {s["seat_id"] for s in seats}
        all_seat_ids = _list_all_seat_ids(auditorium)
        missing = new_seat_ids - all_seat_ids
        if missing:
            return f"Error: Unknown seat ids: {sorted(missing)}"

        # Seats currently held by this booking should be considered "free" for the update.
        globally_booked = _booked_seats_for_show(
            data, booking["theater_id"], booking["show_id"]
        )
        current_seat_ids = {s["seat_id"] for s in booking["seats"]}
        unavailable = (new_seat_ids - current_seat_ids) & globally_booked
        if unavailable:
            return f"Error: Seats not available: {sorted(unavailable)}"

        # Build new seats and recompute totals
        # Stored in seat_id order: the DB hash keeps list order, so "B4, B3" must equal "B3, B4".
        new_booked_seats = _build_booked_seats(
            show, theater, sorted(seats, key=lambda s: s["seat_id"])
        )
        new_tickets_subtotal = round(sum(s["price"] for s in new_booked_seats), 2)
        new_ticket_fees_total = round(
            sum(s["convenience_fee"] for s in new_booked_seats), 2
        )
        new_ticket_tax_total = round(sum(s["tax"] for s in new_booked_seats), 2)

        # Concessions unchanged
        cons_subtotal, cons_tax = _sum_concessions_subtotal_and_tax(
            booking["concessions"]
        )
        booking_fee = float(theater["pricing_rules"]["fees"]["booking_fee"])
        new_fees_total = round(new_ticket_fees_total + booking_fee, 2)
        new_tax_total = round(new_ticket_tax_total + cons_tax, 2)
        new_grand_total = round(
            new_tickets_subtotal + cons_subtotal + new_fees_total + new_tax_total, 2
        )

        old_grand = float(booking["totals"]["grand_total"])
        diff = round(new_grand_total - old_grand, 2)

        if diff > 0:
            # Need additional payment
            if payment is None or round(float(payment["amount"]), 2) != diff:
                return f"Error: Additional payment of {diff} is required to complete the update"
            booking["payment_history"].append(payment)
            booking["totals"]["amount_paid"] = round(
                booking["totals"]["amount_paid"] + diff, 2
            )
        elif diff < 0:
            # Refund
            refund_payment = {
                "payment_id": f"{booking_id}-adj-refund",
                "amount": diff,  # negative
                "method": {
                    "source": "cash",
                    "payment_method_id": "refund",
                    "extra_info": None,
                },
                "created_at": "24-05-15-15-00",
            }
            booking["payment_history"].append(refund_payment)
            booking["totals"]["amount_paid"] = round(
                booking["totals"]["amount_paid"] + diff, 2
            )

        # Update booking fields
        booking["seats"] = new_booked_seats
        booking["totals"]["tickets_subtotal"] = new_tickets_subtotal
        booking["totals"]["fees_total"] = new_fees_total
        booking["totals"]["tax_total"] = new_tax_total
        booking["totals"]["grand_total"] = new_grand_total
        booking["totals"]["amount_due"] = round(
            booking["totals"]["grand_total"] - booking["totals"]["amount_paid"], 2
        )

        return json.dumps(booking)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "update_booking_seats",
                "description": (
                    "Update seats for an existing booking. Recalculates totals and processes "
                    "payment/refund difference. The agent needs to explain the details and ask "
                    "for explicit user confirmation (yes/no) before calling."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "booking_id": {
                            "type": "string",
                            "description": "The booking id.",
                        },
                        "seats": {
                            "type": "array",
                            "description": "New list of seat specs for the booking.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "seat_id": {
                                        "type": "string",
                                        "description": "Seat identifier.",
                                    },
                                    "ticket_type": {
                                        "type": "string",
                                        "enum": ["adult", "child", "senior"],
                                        "description": "Type of ticket for this seat.",
                                    },
                                },
                                "required": ["seat_id", "ticket_type"],
                            },
                        },
                        "payment": {
                            "type": "object",
                            "description": "Optional additional payment to cover an increase in total, if any.",
                            "properties": {
                                "payment_id": {
                                    "type": "string",
                                    "description": "Unique payment identifier.",
                                },
                                "amount": {
                                    "type": "number",
                                    "description": "Payment amount in dollars.",
                                },
                                "method": {
                                    "type": "object",
                                    "description": "Payment method details.",
                                    "properties": {
                                        "source": {
                                            "type": "string",
                                            "enum": [
                                                "card",
                                                "wallet",
                                                "cash",
                                                "gift_card",
                                            ],
                                            "description": "Payment source type.",
                                        },
                                        "payment_method_id": {
                                            "type": "string",
                                            "description": "Payment method identifier.",
                                        },
                                        "extra_info": {
                                            "type": "object",
                                            "description": "Additional method details (optional).",
                                            "properties": {
                                                "brand": {
                                                    "type": "string",
                                                    "description": "Card or wallet brand (if applicable).",
                                                },
                                                "last_four": {
                                                    "type": "string",
                                                    "description": "Last four digits of card (if applicable).",
                                                },
                                            },
                                        },
                                    },
                                    "required": ["source", "payment_method_id"],
                                },
                                "created_at": {
                                    "type": "string",
                                    "description": "Payment timestamp in the format YY-MM-DD-HH-MM.",
                                },
                            },
                            "required": [
                                "payment_id",
                                "amount",
                                "method",
                                "created_at",
                            ],
                        },
                    },
                    "required": ["booking_id", "seats"],
                },
            },
        }
