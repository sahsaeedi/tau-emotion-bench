import json
from typing import Any, Dict, List

from tracer.envs.tool import Tool


class UpdateGameStatusTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], game_id: str, new_status: str) -> str:
        game = data["games"].get(game_id)
        if game is None:
            return "Error: Game not found"
        current = game["status"]
        allowed: Dict[str, List[str]] = {
            "scheduled": ["in_progress", "postponed"],
            "postponed": ["scheduled"],
            "in_progress": ["final"],
            "final": [],
        }
        if new_status == current:
            return json.dumps(game)
        if new_status not in allowed.get(current, []):
            return "Error: Invalid status transition"
        game["status"] = new_status
        return json.dumps(game)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "update_game_status",
                "description": (
                    "Update the status of a game. The agent needs to explain the modification detail "
                    "and ask for explicit user confirmation (yes/no) to proceed. "
                    "Allowed transitions: scheduled -> in_progress or postponed; postponed -> scheduled; "
                    "in_progress -> final; final -> no further transitions."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "game_id": {
                            "type": "string",
                            "description": "The game ID, such as 'game_001'.",
                        },
                        "new_status": {
                            "type": "string",
                            "enum": ["scheduled", "in_progress", "final", "postponed"],
                            "description": "The new status for the game.",
                        },
                    },
                    "required": ["game_id", "new_status"],
                },
            },
        }
