import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class GetBookingDetailsTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], booking_id: str) -> str:
        booking = data["bookings"].get(booking_id)
        if booking is None:
            return f"Error: Booking {booking_id} not found"
        return json.dumps(booking)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_booking_details",
                "description": "Get booking details.",
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
