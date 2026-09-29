import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class GetTravelerDetailsTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], traveler_id: str) -> str:
        traveler = data["travelers"].get(traveler_id)
        if traveler is None:
            return "Error: Traveler not found"
        return json.dumps(traveler)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_traveler_details",
                "description": "Get traveler profile with bookings.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "traveler_id": {
                            "type": "string",
                            "description": "The traveler id.",
                        },
                    },
                    "required": ["traveler_id"],
                },
            },
        }
