from typing import Any, Dict, Optional

from tracer.envs.tool import Tool


class GetPlayerTotalPointsTool(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any], player_id: str, season: Optional[str] = None
    ) -> str:
        p = data["players"].get(player_id)
        if p is None:
            return "Error: Player not found"
        total = 0
        for gid in p["games"]:
            g = data["games"].get(gid)
            if g is None:
                continue
            if season is not None and g["season"] != season:
                continue
            for entry in g["box_score"]:
                if entry["player_id"] == player_id:
                    total += entry["points"]
        return str(total)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_player_total_points",
                "description": "Compute a player's total points across games, optionally filtered by season.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "player_id": {
                            "type": "string",
                            "description": "The player ID.",
                        },
                        "season": {
                            "type": "string",
                            "description": "Optional season identifier (e.g., '2024-25').",
                        },
                    },
                    "required": ["player_id"],
                },
            },
        }
