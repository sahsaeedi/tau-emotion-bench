import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class GetRegistrationDetailsTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], registration_id: str) -> str:
        registration = data["registrations"].get(registration_id)
        if registration is None:
            return f"Error: Registration {registration_id} not found"
        return json.dumps(registration)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_registration_details",
                "description": "Get the details of a registration.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "registration_id": {
                            "type": "string",
                            "description": "The registration id.",
                        },
                    },
                    "required": ["registration_id"],
                },
            },
        }
