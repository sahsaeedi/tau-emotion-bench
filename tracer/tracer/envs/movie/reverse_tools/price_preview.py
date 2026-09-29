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


class PricePreviewTool(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        theater_id: str,
        show_id: str,
        seats: List[dict],
        concessions: Optional[List[dict]] = None,
    ) -> str:
        concessions = concessions or []
        theater = data["theaters"].get(theater_id)
        if theater is None:
            return f"Error: Theater {theater_id} not found"
        show, _, err = _find_show(data, theater_id, show_id)
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

        booked_seats = _build_booked_seats(show, theater, seats)
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

        result = {
            "tickets_subtotal": tickets_subtotal,
            "concessions_subtotal": concessions_subtotal,
            "fees_total": fees_total,
            "tax_total": tax_total,
            "grand_total": grand_total,
            "ticket_count": len(booked_seats),
            "booking_fee": round(booking_fee, 2),
        }
        return json.dumps(result)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "price_preview",
                "description": "Preview price breakdown for a potential booking (no booking created).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "theater_id": {
                            "type": "string",
                            "description": "The theater id.",
                        },
                        "show_id": {"type": "string", "description": "The show id."},
                        "seats": {
                            "type": "array",
                            "description": "List of seat specs to price.",
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
                    },
                    "required": ["theater_id", "show_id", "seats"],
                },
            },
        }
