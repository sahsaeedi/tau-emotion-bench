import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class GetLatestBookableFlightDate(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
    ) -> str:
        """
        Find the latest bookable flight date in ISO format (YYYY-MM-DD). This can be used to lookup available flights from today up to this date.
        """
        return json.dumps("The latest bookable flight date is 2024-05-30.")

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_latest_bookable_flight_date",
                "description": (
                    "Find the latest bookable flight date in ISO format (YYYY-MM-DD). This can be used to lookup available flights from today up to this date."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }
