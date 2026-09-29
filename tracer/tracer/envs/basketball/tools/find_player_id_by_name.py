from typing import Any, Dict, List

from tracer.envs.tool import Tool


class FindPlayerIdByNameTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], first_name: str, last_name: str) -> str:
        matches: List[str] = []
        fn = first_name.lower()
        ln = last_name.lower()
        for pid, p in data["players"].items():
            if (
                p["name"]["first_name"].lower() == fn
                and p["name"]["last_name"].lower() == ln
            ):
                matches.append(pid)
        if not matches:
            return "Error: Player not found"
        if len(matches) > 1:
            return "Error: Multiple players found, please provide more information"
        return matches[0]

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "find_player_id_by_name",
                "description": "Find player ID by first name and last name.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "first_name": {
                            "type": "string",
                            "description": "First name of the player, e.g., 'John'.",
                        },
                        "last_name": {
                            "type": "string",
                            "description": "Last name of the player, e.g., 'Doe'.",
                        },
                    },
                    "required": ["first_name", "last_name"],
                },
            },
        }
