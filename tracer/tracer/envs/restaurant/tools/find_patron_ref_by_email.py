from typing import Any, Dict

from tracer.envs.tool import Tool


class FindPatronRefByEmailTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], email: str) -> str:
        for guest_ref, patron in data["patron_registry"].items():
            if patron["contact_email"].lower() == email.lower():
                return guest_ref
        return "Error: Patron not found"

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "find_patron_ref_by_email",
                "description": "Find patron reference by contact email.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "email": {
                            "type": "string",
                            "description": "The email of the patron, such as 'guest@example.com'.",
                        },
                    },
                    "required": ["email"],
                },
            },
        }
