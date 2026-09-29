import json
from typing import Any, Dict, Optional

from tracer.envs.tool import Tool


class GetClubRecordTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], club_id: str, season: Optional[str] = None) -> str:
        club = data["clubs"].get(club_id)
        if club is None:
            return "Error: Club not found"
        wins = 0
        losses = 0
        for gid in club["games"]:
            g = data["games"].get(gid)
            if g is None:
                continue
            if g["status"] != "final":
                continue
            if season is not None and g["season"] != season:
                continue
            home = g["clubs"]["home"]
            away = g["clubs"]["away"]
            if home["club_id"] == club_id:
                if home["score"] > away["score"]:
                    wins += 1
                elif home["score"] < away["score"]:
                    losses += 1
            elif away["club_id"] == club_id:
                if away["score"] > home["score"]:
                    wins += 1
                elif away["score"] < home["score"]:
                    losses += 1
        return json.dumps({"wins": wins, "losses": losses})

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_club_record",
                "description": "Compute a club's win-loss record for a season (or overall if season is None). Only final games count.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "club_id": {
                            "type": "string",
                            "description": "The club ID.",
                        },
                        "season": {
                            "type": "string",
                            "description": "Optional season filter.",
                        },
                    },
                    "required": ["club_id"],
                },
            },
        }
