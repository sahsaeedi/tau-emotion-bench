import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class GetUserDetails(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        user_id: str,
    ) -> str:
        users = data["users"]
        user_details = users.get(user_id, None)
        if user_details is None:
            return json.dumps("No user found with the given ID.")
        return json.dumps(user_details)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_user_details",
                "description": ("Get the details of a specific user by their user ID."),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_id": {
                            "type": "string",
                            "description": "The ID of the user to retrieve details for, such as 'sara_doe_496'.",
                        },
                    },
                    "required": ["user_id"],
                },
            },
        }
