import json
from copy import deepcopy
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


class UpdateBookingRoomingTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], booking_id: str, rooming: Dict[str, Any]) -> str:
        _, booking = _find_booking(data, booking_id)
        if booking is None:
            return "Error: Booking not found"

        booking["rooming"] = deepcopy(rooming)
        return json.dumps(booking)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "update_booking_rooming",
                "description": (
                    "Update the rooming configuration for a booking. Price neutrality is assumed "
                    "unless the package/add-ons/policies say otherwise. The agent needs to explain "
                    "the details and ask for explicit user confirmation (yes/no) before calling."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "booking_id": {
                            "type": "string",
                            "description": "The booking id.",
                        },
                        "rooming": {
                            "type": "object",
                            "description": "New rooming configuration with room_type and occupancy.",
                        },
                    },
                    "required": ["booking_id", "rooming"],
                },
            },
        }
