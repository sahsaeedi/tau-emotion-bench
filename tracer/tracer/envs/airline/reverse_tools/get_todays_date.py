import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class GetTodaysDate(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
    ) -> str:
        """
        Find today's date in ISO format (YYYY-MM-DD). This can be used to lookup older details of flights ranged back to today and get available flights from today onwards.
        """
        return json.dumps("Today's date is 2024-05-15.")

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_todays_date",
                "description": (
                    "Find today's date in ISO format (YYYY-MM-DD). This can be used to lookup older details of flights ranged back to today and get available flights from today onwards."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }
