import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class GetFlightDetails(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        flight_id: str,
    ) -> str:
        flights = data["flights"]
        flight_details = flights.get(flight_id, None)
        if flight_details is None:
            return json.dumps("No flight found with the given ID.")
        return json.dumps(flight_details)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_flight_details",
                "description": (
                    "Get the details of a specific flight by its flight ID."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "flight_id": {
                            "type": "string",
                            "description": "The ID of the flight to retrieve details for, such as 'flight_12345'.",
                        },
                    },
                    "required": ["flight_id"],
                },
            },
        }
