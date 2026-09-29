import copy
import json
from typing import Any, Dict, List

from tracer.envs.movie.tools.update_booking_seats import UpdateBookingSeatsTool
from tracer.envs.tool import Tool

# Read-only dry run of update_booking_seats: runs the real tool on a deep copy of the
# booking table, so every precondition error and the exact price delta are the tool's
# own. 5 of 19 failed movie tasks updated seats that were unknown / taken / on a
# canceled booking, or guessed the additional payment.


class PreviewSeatUpdate(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any], booking_id: str, seats: List[Dict[str, Any]]
    ) -> str:
        booking = data["bookings"].get(booking_id)
        if booking is None:
            return f"Error: Booking {booking_id} not found"
        old_total = float(booking["totals"]["grand_total"])

        # scratch copy: bookings is the only table the tool mutates
        scratch = dict(data)
        scratch["bookings"] = copy.deepcopy(data["bookings"])
        # first pass without payment: a price rise is reported as the exact difference
        out = UpdateBookingSeatsTool.invoke(scratch, booking_id, seats)
        if out.startswith("Error: Additional payment of"):
            diff = round(float(out.split("Additional payment of ")[1].split()[0]), 2)
            return json.dumps(
                {
                    "ok": True,
                    "requires_additional_payment": diff,
                    "refund": 0.0,
                    "old_grand_total": old_total,
                    "new_grand_total": round(old_total + diff, 2),
                    "note": (
                        f"update_booking_seats needs payment={{'payment_id': ..., 'amount': {diff}, "
                        f"'method': {{...}}, 'created_at': ...}} with amount exactly {diff}."
                    ),
                }
            )
        if out.startswith("Error"):
            return json.dumps({"ok": False, "error": out})
        updated = json.loads(out)
        new_total = float(updated["totals"]["grand_total"])
        return json.dumps(
            {
                "ok": True,
                "requires_additional_payment": 0.0,
                "refund": round(max(0.0, old_total - new_total), 2),
                "old_grand_total": old_total,
                "new_grand_total": new_total,
                "amount_paid_after": updated["totals"]["amount_paid"],
                "note": "No payment argument needed"
                + (" (a refund entry is appended)." if new_total < old_total else "."),
            }
        )

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "preview_seat_update",
                "description": (
                    "Read-only dry run of update_booking_seats for a booking and a new seat list: "
                    "returns the exact error the tool would raise (booking not confirmed, show not "
                    "scheduled, unknown or unavailable seat ids) or, when valid, the exact "
                    "requires_additional_payment / refund and new grand total. Call it before writing "
                    "an update_booking_seats action and copy the amount."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "booking_id": {"type": "string"},
                        "seats": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "seat_id": {"type": "string"},
                                    "ticket_type": {
                                        "type": "string",
                                        "enum": ["adult", "child", "senior"],
                                    },
                                },
                                "required": ["seat_id", "ticket_type"],
                            },
                            "description": "The complete new seat list (replaces the current one).",
                        },
                    },
                    "required": ["booking_id", "seats"],
                },
            },
        }
