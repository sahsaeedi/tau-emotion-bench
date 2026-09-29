import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class GetGameScoreTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], game_id: str) -> str:
        g = data["games"].get(game_id)
        if g is None:
            return "Error: Game not found"
        result = {
            "status": g["status"],
            "home": {
                "club_id": g["clubs"]["home"]["club_id"],
                "name": g["clubs"]["home"]["name"],
                "score": g["clubs"]["home"]["score"],
            },
            "away": {
                "club_id": g["clubs"]["away"]["club_id"],
                "name": g["clubs"]["away"]["name"],
                "score": g["clubs"]["away"]["score"],
            },
        }
        return json.dumps(result)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_game_score",
                "description": "Get a game's current score summary, including status and home/away club scores.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "game_id": {
                            "type": "string",
                            "description": "The game ID.",
                        },
                    },
                    "required": ["game_id"],
                },
            },
        }
