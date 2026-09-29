import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class GetPatronDetailsTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], guest_ref: str) -> str:
        patron = data["patron_registry"].get(guest_ref)
        if patron is None:
            return "Error: Patron not found"
        return json.dumps(patron)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_patron_details",
                "description": "Get the details of a patron, including their saved instruments and ticket history.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "guest_ref": {
                            "type": "string",
                            "description": "The patron reference, such as 'GUEST-0001'.",
                        },
                    },
                    "required": ["guest_ref"],
                },
            },
        }
