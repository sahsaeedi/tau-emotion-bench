import json
import uuid
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


def _compute_concession_lines(
    theater: Dict[str, Any], concessions: List[dict]
) -> List[dict]:
    """concessions spec: [{item_id, name, size, quantity, price_each}]. Adds tax_each and total per line."""
    tax_rate = float(theater["pricing_rules"]["tax_rate_percent"]) / 100.0
    lines: List[dict] = []
    for c in concessions:
        qty = int(c["quantity"])
        price_each = float(c["price_each"])
        tax_each = price_each * tax_rate
        total = qty * (price_each + tax_each)
        lines.append(
            {
                "item_id": c["item_id"],
                "name": c["name"],
                "size": c["size"],
                "quantity": qty,
                "price_each": round(price_each, 2),
                "tax_each": round(tax_each, 2),
                "total": round(total, 2),
            }
        )
    return lines


def _sum_concessions_subtotal_and_tax(items: List[dict]) -> Tuple[float, float]:
    subtotal = 0.0
    tax_total = 0.0
    for i in items:
        subtotal += i["price_each"] * i["quantity"]
        tax_total += i["tax_each"] * i["quantity"]
    return round(subtotal, 2), round(tax_total, 2)


def _make_delivery(method: str, booking_id: str, count: int) -> dict:
    tickets = []
    for i in range(count):
        tid = f"{booking_id}-TKT-{i + 1:03d}"
        tickets.append({"ticket_id": tid, "barcode": f"BAR-{tid}"})
    return {"method": method, "tickets": tickets}


def _new_booking_id(data: Dict[str, Any]) -> str:
    while True:
        booking_id = "BKG" + uuid.uuid4().hex[:8].upper()
        if booking_id not in data["bookings"]:
            return booking_id


class CreateBookingTool(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        theater_id: str,
        show_id: str,
        customer: dict,
        seats: List[dict],
        delivery_method: str,
        payments: List[dict],
        concessions: Optional[List[dict]] = None,
        special_requests: Optional[str] = None,
    ) -> str:
        concessions = concessions or []
        theater = data["theaters"].get(theater_id)
        if theater is None:
            return f"Error: Theater {theater_id} not found"
        show, date, err = _find_show(data, theater_id, show_id)
        if err:
            return err
        if show["status"] != "scheduled":
            return f"Error: Show {show_id} is not available for booking (status={show['status']})"

        auditorium = theater["auditoriums"].get(show["auditorium_id"])
        if auditorium is None:
            return f"Error: Auditorium {show['auditorium_id']} not found at theater {theater_id}"

        requested_seat_ids = {s["seat_id"] for s in seats}
        all_seat_ids = _list_all_seat_ids(auditorium)
        missing = requested_seat_ids - all_seat_ids
        if missing:
            return f"Error: Unknown seat ids: {sorted(missing)}"
        conflict = requested_seat_ids & _booked_seats_for_show(
            data, theater_id, show_id
        )
        if conflict:
            return f"Error: Seats not available: {sorted(conflict)}"

        # Stored in seat_id order: the DB hash keeps list order, so "B4, B3" must equal "B3, B4".
        booked_seats = _build_booked_seats(
            show, theater, sorted(seats, key=lambda s: s["seat_id"])
        )
        cons_lines = _compute_concession_lines(theater, concessions)

        tickets_subtotal = round(sum(s["price"] for s in booked_seats), 2)
        ticket_fees_total = round(sum(s["convenience_fee"] for s in booked_seats), 2)
        ticket_tax_total = round(sum(s["tax"] for s in booked_seats), 2)
        concessions_subtotal, concessions_tax = _sum_concessions_subtotal_and_tax(
            cons_lines
        )

        booking_fee = float(theater["pricing_rules"]["fees"]["booking_fee"])
        fees_total = round(ticket_fees_total + booking_fee, 2)
        tax_total = round(ticket_tax_total + concessions_tax, 2)
        grand_total = round(
            tickets_subtotal + concessions_subtotal + fees_total + tax_total, 2
        )

        total_paid = round(sum(float(p["amount"]) for p in payments), 2)
        if total_paid != grand_total:
            return (
                f"Error: Payment amount does not add up, total price is {grand_total}, "
                f"but paid {total_paid}"
            )

        booking_id = _new_booking_id(data)
        delivery = _make_delivery(delivery_method, booking_id, len(booked_seats))

        totals = {
            "tickets_subtotal": tickets_subtotal,
            "concessions_subtotal": concessions_subtotal,
            "fees_total": fees_total,
            "tax_total": tax_total,
            "grand_total": grand_total,
            "amount_paid": total_paid,
            "amount_due": round(grand_total - total_paid, 2),
        }

        booking = {
            "booking_id": booking_id,
            "theater_id": theater_id,
            "movie_id": show["movie_id"],
            "show_id": show_id,
            "date": date,
            "start_time_local": show["start_time_local"],
            "status": "confirmed",
            "created_at": "24-05-15-15-00",
            "canceled_at": None,
            "customer": customer,
            "seats": booked_seats,
            "concessions": cons_lines,
            "promotions_applied": [],
            "payment_history": payments,
            "totals": totals,
            "delivery": delivery,
            "special_requests": special_requests,
        }

        data["bookings"][booking_id] = booking
        return json.dumps(booking)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "create_booking",
                "description": (
                    "Create a booking for a show with selected seats and optional concessions. "
                    "The agent needs to explain the details and ask for explicit user confirmation "
                    "(yes/no) before calling."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "theater_id": {
                            "type": "string",
                            "description": "The theater id.",
                        },
                        "show_id": {"type": "string", "description": "The show id."},
                        "customer": {
                            "type": "object",
                            "description": "Customer info.",
                            "properties": {
                                "name": {
                                    "type": "object",
                                    "description": "Customer name.",
                                    "properties": {
                                        "first_name": {
                                            "type": "string",
                                            "description": "Customer first name.",
                                        },
                                        "last_name": {
                                            "type": "string",
                                            "description": "Customer last name.",
                                        },
                                    },
                                    "required": ["first_name", "last_name"],
                                },
                                "email": {
                                    "type": "string",
                                    "description": "Customer email.",
                                },
                                "phone": {
                                    "type": "string",
                                    "description": "Customer phone.",
                                },
                                "loyalty_id": {
                                    "type": "string",
                                    "description": "Customer loyalty identifier (optional).",
                                },
                            },
                            "required": ["name", "email", "phone"],
                        },
                        "seats": {
                            "type": "array",
                            "description": "List of seat specs to book.",
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
                        "delivery_method": {
                            "type": "string",
                            "enum": ["e-ticket", "box-office", "kiosk"],
                            "description": "Delivery method for tickets.",
                        },
                        "payments": {
                            "type": "array",
                            "description": (
                                "List of payments. Amounts must sum to the grand total from price_preview."
                            ),
                            "items": {
                                "type": "object",
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
                        "concessions": {
                            "type": "array",
                            "description": "Optional list of concession item specs.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "item_id": {
                                        "type": "string",
                                        "description": "Concession item identifier.",
                                    },
                                    "name": {
                                        "type": "string",
                                        "description": "Concession item name.",
                                    },
                                    "size": {
                                        "type": "string",
                                        "description": "Size or variant.",
                                    },
                                    "quantity": {
                                        "type": "integer",
                                        "description": "Quantity purchased.",
                                    },
                                    "price_each": {
                                        "type": "number",
                                        "description": "Price per item in dollars.",
                                    },
                                },
                                "required": [
                                    "item_id",
                                    "name",
                                    "size",
                                    "quantity",
                                    "price_each",
                                ],
                            },
                        },
                        "special_requests": {
                            "type": "string",
                            "description": "Optional special requests noted by the customer.",
                        },
                    },
                    "required": [
                        "theater_id",
                        "show_id",
                        "customer",
                        "seats",
                        "delivery_method",
                        "payments",
                    ],
                },
            },
        }
