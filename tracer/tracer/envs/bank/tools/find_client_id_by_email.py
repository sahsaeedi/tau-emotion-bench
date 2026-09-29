from typing import Any, Dict

from tracer.envs.tool import Tool


class FindClientIdByEmail(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], email: str) -> str:
        for client_id, client in data["clients"].items():
            if client["contact"]["email"].lower() == email.lower():
                return client_id
        return "Error: Client not found"

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "find_client_id_by_email",
                "description": "Find a client's id by their email address.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "email": {
                            "type": "string",
                            "description": "The client's email, e.g., 'someone@example.com'.",
                        },
                    },
                    "required": ["email"],
                },
            },
        }
