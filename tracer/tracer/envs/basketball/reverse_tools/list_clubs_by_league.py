import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class ListClubsByLeagueTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], league: str) -> str:
        league_lower = league.lower()
        filtered = {
            club["name"]: club["club_id"]
            for club in data["clubs"].values()
            if club["league"].lower() == league_lower
        }
        if not filtered:
            return "Error: No clubs found for the specified league"
        return json.dumps(dict(sorted(filtered.items())), sort_keys=False)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "list_clubs_by_league",
                "description": (
                    "List clubs filtered by league. Returns a JSON mapping of club names to club IDs "
                    "within the specified league, sorted alphabetically by club name."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "league": {
                            "type": "string",
                            "description": "League name, case-insensitive match.",
                        },
                    },
                    "required": ["league"],
                },
            },
        }
