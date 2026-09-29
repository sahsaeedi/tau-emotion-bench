import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class GetGameTimelineTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], game_id: str) -> str:
        g = data["games"].get(game_id)
        if g is None:
            return "Error: Game not found"
        return json.dumps(g["scoring_history"])

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_game_timeline",
                "description": "Get the chronological scoring history for a game.",
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
