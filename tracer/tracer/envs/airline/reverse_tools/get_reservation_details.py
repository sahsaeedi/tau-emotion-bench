import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class GetReservationDetails(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        reservation_id: str,
    ) -> str:
        reservations = data["reservations"]
        reservation_details = reservations.get(reservation_id, None)
        if reservation_details is None:
            return json.dumps("No reservation found with the given ID.")
        return json.dumps(reservation_details)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_reservation_details",
                "description": (
                    "Get the details of a specific reservation by its reservation ID."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reservation_id": {
                            "type": "string",
                            "description": "The ID of the reservation to retrieve details for, such as 'res_12345'.",
                        },
                    },
                    "required": ["reservation_id"],
                },
            },
        }
