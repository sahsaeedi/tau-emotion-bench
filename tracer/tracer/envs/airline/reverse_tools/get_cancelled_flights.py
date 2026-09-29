import json
import random
from typing import Any, Dict

from tracer.envs.tool import Tool


class GetCancelledFlights(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        date: str,
    ) -> str:
        """
        Find flights that were cancelled on a given date.
        """
        flights = data["flights"]
        result = []
        for flight_id, info in flights.items():
            day = info.get("dates", None).get(date)
            if not day:
                continue
            if day.get("status") == "cancelled":
                result.append(
                    {
                        "flight_id": flight_id,
                        "flight_number": info.get("flight_number"),
                        "origin": info.get("origin"),
                        "destination": info.get("destination"),
                        "date": date,
                        "status": "cancelled",
                        "details": day,
                    }
                )

        random.shuffle(result)
        return json.dumps(result)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_cancelled_flights",
                "description": ("Find flights that were cancelled on a given date."),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "date": {
                            "type": "string",
                            "description": "The date to retrieve cancelled flights for in ISO format (YYYY-MM-DD), such as '2024-04-27'.",
                        },
                    },
                    "required": ["date"],
                },
            },
        }
