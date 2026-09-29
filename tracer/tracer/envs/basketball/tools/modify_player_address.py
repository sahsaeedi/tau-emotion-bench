import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class ModifyPlayerAddressTool(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        player_id: str,
        street: str,
        city: str,
        state: str,
        country: str,
        zip: str,
    ) -> str:
        player = data["players"].get(player_id)
        if player is None:
            return "Error: Player not found"
        player["address"]["street"] = street
        player["address"]["city"] = city
        player["address"]["state"] = state
        player["address"]["country"] = country
        player["address"]["zip"] = zip
        return json.dumps(player)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "modify_player_address",
                "description": (
                    "Modify a player's address. The agent needs to explain the modification detail "
                    "and ask for explicit user confirmation (yes/no) to proceed."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "player_id": {
                            "type": "string",
                            "description": "The player ID, such as 'player_001'.",
                        },
                        "street": {
                            "type": "string",
                            "description": "Street address, e.g., '123 Main St'.",
                        },
                        "city": {"type": "string", "description": "City name."},
                        "state": {
                            "type": "string",
                            "description": "State or province.",
                        },
                        "country": {"type": "string", "description": "Country name."},
                        "zip": {"type": "string", "description": "Postal code."},
                    },
                    "required": [
                        "player_id",
                        "street",
                        "city",
                        "state",
                        "country",
                        "zip",
                    ],
                },
            },
        }
