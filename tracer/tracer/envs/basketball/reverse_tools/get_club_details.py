import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class GetClubDetailsTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], club_id: str) -> str:
        club = data["clubs"].get(club_id)
        if club is None:
            return "Error: Club not found"
        return json.dumps(club)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_club_details",
                "description": "Get details of a club by club ID.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "club_id": {
                            "type": "string",
                            "description": "The club ID, such as 'club_001'.",
                        },
                    },
                    "required": ["club_id"],
                },
            },
        }
