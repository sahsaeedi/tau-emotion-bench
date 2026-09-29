import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class CancelBookingTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], booking_id: str) -> str:
        """Cancel a booking and add a refund payment for the full amount paid."""
        booking = data["bookings"].get(booking_id)
        if booking is None:
            return f"Error: Booking {booking_id} not found"
        if booking["status"] in ("canceled", "refunded"):
            return json.dumps(booking)

        # Compute refund as negative of amount_paid
        refund_amount = -float(booking["totals"]["amount_paid"])
        if refund_amount != 0.0:
            refund_payment = {
                "payment_id": f"{booking_id}-refund",
                "amount": round(refund_amount, 2),
                "method": {
                    "source": "cash",  # Method placeholder; real systems track original source
                    "payment_method_id": "refund",
                    "extra_info": None,
                },
                "created_at": "24-05-15-15-00",
            }
            booking["payment_history"].append(refund_payment)
            booking["totals"]["amount_paid"] = round(
                booking["totals"]["amount_paid"] + refund_amount, 2
            )
            booking["totals"]["amount_due"] = round(
                booking["totals"]["grand_total"] - booking["totals"]["amount_paid"], 2
            )

        booking["status"] = "canceled"
        booking["canceled_at"] = "24-05-15-15-00"
        return json.dumps(booking)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "cancel_booking",
                "description": (
                    "Cancel a booking and add a refund payment for the full amount paid. "
                    "The agent needs to explain the details and ask for explicit user "
                    "confirmation (yes/no) before calling."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "booking_id": {
                            "type": "string",
                            "description": "The booking id.",
                        },
                    },
                    "required": ["booking_id"],
                },
            },
        }
