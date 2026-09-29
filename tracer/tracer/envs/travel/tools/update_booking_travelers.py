import json
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

from tracer.envs.tool import Tool


def _find_booking(
    data: Dict[str, Any], booking_id: str
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    for traveler in data["travelers"].values():
        for booking in traveler["bookings"]:
            if booking["booking_id"] == booking_id:
                return traveler, booking
    return None, None


class UpdateBookingTravelersTool(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any], booking_id: str, travelers: List[Dict[str, Any]]
    ) -> str:
        _, booking = _find_booking(data, booking_id)
        if booking is None:
            return "Error: Booking not found"

        if len(travelers) != len(booking["travelers"]):
            return "Error: Number of travelers does not match current booking"

        booking["travelers"] = deepcopy(travelers)
        return json.dumps(booking)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "update_booking_travelers",
                "description": (
                    "Update traveler details for a booking. The number of travelers must remain "
                    "unchanged. The agent needs to explain the details and ask for explicit user "
                    "confirmation (yes/no) before calling."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "booking_id": {
                            "type": "string",
                            "description": "The booking id.",
                        },
                        "travelers": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": "Full replacement list of travelers, each with first_name, last_name, and dob (YY-MM-DD).",
                        },
                    },
                    "required": ["booking_id", "travelers"],
                },
            },
        }
