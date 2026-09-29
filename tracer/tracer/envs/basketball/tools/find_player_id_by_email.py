from typing import Any, Dict

from tracer.envs.tool import Tool


class FindPlayerIdByEmailTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], email: str) -> str:
        email_lower = email.lower()
        for player_id, player in data["players"].items():
            if player["email"].lower() == email_lower:
                return player_id
        return "Error: Player not found"

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "find_player_id_by_email",
                "description": "Find player ID by email.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "email": {
                            "type": "string",
                            "description": "The email of the player, such as 'player@example.com'.",
                        },
                    },
                    "required": ["email"],
                },
            },
        }
