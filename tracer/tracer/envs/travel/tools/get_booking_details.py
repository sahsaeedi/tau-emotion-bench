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


class GetBookingDetailsTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], booking_id: str) -> str:
        _, booking = _find_booking(data, booking_id)
        if booking is None:
            return "Error: Booking not found"
        return json.dumps(booking)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_booking_details",
                "description": "Get a booking's full details.",
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
