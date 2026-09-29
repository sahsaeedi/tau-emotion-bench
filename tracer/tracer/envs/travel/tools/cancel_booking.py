import json
from typing import Any, Dict, Optional, Tuple

from tracer.envs.tool import Tool


def _find_booking(
    data: Dict[str, Any], booking_id: str
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    for traveler in data["travelers"].values():
        for booking in traveler["bookings"]:
            if booking["booking_id"] == booking_id:
                return traveler, booking
    return None, None


class CancelBookingTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], booking_id: str) -> str:
        _, booking = _find_booking(data, booking_id)
        if booking is None:
            return "Error: Booking not found"
        package = data["packages"].get(booking["package_id"])
        if package is None:
            return "Error: Package not found for this booking"

        refunds = []
        for p in booking["payment_history"]:
            refunds.append({"payment_id": p["payment_id"], "amount": -p["amount"]})
        booking["payment_history"].extend(refunds)

        booking["status"] = "cancelled"

        departure = package["departures"].get(booking["departure_date"])
        if departure is not None:
            departure["available_slots"] += len(booking["travelers"])

        return json.dumps(booking)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "cancel_booking",
                "description": (
                    "Cancel a booking and process refunds as negative payment history entries. "
                    "Restores departure available slots. The agent needs to explain the details "
                    "and ask for explicit user confirmation (yes/no) before calling."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "booking_id": {
                            "type": "string",
                            "description": "The booking id to cancel.",
                        },
                    },
                    "required": ["booking_id"],
                },
            },
        }
