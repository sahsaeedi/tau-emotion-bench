import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class GetClientDetails(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], client_id: str) -> str:
        client = data["clients"].get(client_id)
        if client is None:
            return "Error: Client not found"
        return json.dumps(client)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_client_details",
                "description": "Get the details of a client, including accounts, cards, loans, and beneficiaries.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "client_id": {
                            "type": "string",
                            "description": "The client id.",
                        },
                    },
                    "required": ["client_id"],
                },
            },
        }
