import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class GetGameDetailsTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], game_id: str) -> str:
        game = data["games"].get(game_id)
        if game is None:
            return "Error: Game not found"
        return json.dumps(game)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_game_details",
                "description": "Get details of a game by game ID.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "game_id": {
                            "type": "string",
                            "description": "The game ID, such as 'game_001'.",
                        },
                    },
                    "required": ["game_id"],
                },
            },
        }
