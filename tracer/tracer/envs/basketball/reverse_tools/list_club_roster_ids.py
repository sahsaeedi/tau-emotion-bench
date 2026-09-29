import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class ListClubRosterIdsTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], club_id: str, active_only: bool = True) -> str:
        club = data["clubs"].get(club_id)
        if club is None:
            return "Error: Club not found"
        ids = [
            pid
            for pid, entry in club["roster"].items()
            if (entry["active"] if active_only else True)
        ]
        return json.dumps(sorted(ids))

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "list_club_roster_ids",
                "description": "List player IDs in a club's roster, sorted alphabetically.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "club_id": {
                            "type": "string",
                            "description": "The club ID, such as 'club_001'.",
                        },
                        "active_only": {
                            "type": "boolean",
                            "description": "If True, include only active players. Defaults to True.",
                        },
                    },
                    "required": ["club_id"],
                },
            },
        }
