import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class GetTheaterDetailsTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], theater_id: str) -> str:
        theater = data["theaters"].get(theater_id)
        if theater is None:
            return f"Error: Theater {theater_id} not found"
        return json.dumps(theater)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_theater_details",
                "description": "Get details for a theater, including schedules and auditoriums.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "theater_id": {
                            "type": "string",
                            "description": "The theater id.",
                        },
                    },
                    "required": ["theater_id"],
                },
            },
        }
