import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class GetPlayerDetailsTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], player_id: str) -> str:
        player = data["players"].get(player_id)
        if player is None:
            return "Error: Player not found"
        return json.dumps(player)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_player_details",
                "description": "Get details of a player by player ID.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "player_id": {
                            "type": "string",
                            "description": "The player ID, such as 'player_001'.",
                        },
                    },
                    "required": ["player_id"],
                },
            },
        }
