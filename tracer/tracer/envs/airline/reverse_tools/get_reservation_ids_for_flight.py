import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class GetReservationIdsForFlight(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        flight_id: str,
        date: str,
    ) -> str:
        """
        Find reservation IDs for a specific flight on a given date.
        """
        reservations = data["reservations"]
        result = []
        for res_id, res in reservations.items():
            res_flights = res.get("flights", [])
            for flight in res_flights:
                if (
                    flight.get("flight_number") == flight_id
                    and flight.get("date") == date
                ):
                    result.append(res_id)
                    break
        import random

        random.shuffle(result)
        if not result:
            return json.dumps(
                f"No reservation IDs found for flight {flight_id} on date {date}."
            )
        return json.dumps(result)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_reservation_ids_for_flight",
                "description": (
                    " List all reservation IDs associated with a particular flight on a given date."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "flight_id": {
                            "type": "string",
                            "description": "The unique flight identifier to search within reservation records.",
                        },
                        "date": {
                            "type": "string",
                            "description": "The date to retrieve reservation IDs for in ISO format (YYYY-MM-DD), such as '2024-04-27'.",
                        },
                    },
                    "required": ["flight_id", "date"],
                },
            },
        }
