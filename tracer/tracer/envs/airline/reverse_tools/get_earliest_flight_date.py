import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class GetEarliestFlightDate(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
    ) -> str:
        """
        Find the earliest flight date in ISO format (YYYY-MM-DD). This can be used to lookup older details of flights ranged back to this date and get available flights from this date onwards to today.
        """
        return json.dumps("The earliest flight date is 2024-05-01.")

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_earliest_flight_date",
                "description": (
                    "Find the earliest flight date in ISO format (YYYY-MM-DD). This can be used to lookup older details of flights ranged back to this date and get available flights from this date onwards to today."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }
