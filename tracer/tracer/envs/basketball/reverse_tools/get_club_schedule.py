import json
from typing import Any, Dict, List, Optional

from tracer.envs.tool import Tool


class GetClubScheduleTool(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        club_id: str,
        season: Optional[str] = None,
        status: Optional[str] = None,
    ) -> str:
        club = data["clubs"].get(club_id)
        if club is None:
            return "Error: Club not found"
        result: List[str] = []
        for gid in club["games"]:
            g = data["games"].get(gid)
            if g is None:
                continue
            if season is not None and g["season"] != season:
                continue
            if status is not None and g["status"] != status:
                continue
            result.append(gid)
        return json.dumps(result)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_club_schedule",
                "description": "Get the schedule (list of game IDs) for a club, optionally filtered by season and status.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "club_id": {
                            "type": "string",
                            "description": "The club ID.",
                        },
                        "season": {
                            "type": "string",
                            "description": "Optional season (e.g., '2024-25').",
                        },
                        "status": {
                            "type": "string",
                            "enum": ["scheduled", "in_progress", "final", "postponed"],
                            "description": "Optional status filter.",
                        },
                    },
                    "required": ["club_id"],
                },
            },
        }
