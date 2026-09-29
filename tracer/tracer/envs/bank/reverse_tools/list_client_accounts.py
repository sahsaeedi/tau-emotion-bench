import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class ListClientAccountsTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], client_id: str) -> str:
        client = data["clients"].get(client_id)
        if client is None:
            return "Error: Client not found"
        summary = {
            account_id: {
                "type": account["type"],
                "status": account["status"],
                "masked": account["account_number_masked"],
                "currency": account["currency"],
            }
            for account_id, account in client["accounts"].items()
        }
        return json.dumps(summary, sort_keys=True)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "list_client_accounts",
                "description": "List all accounts for a client as a JSON string mapping account_id to a summary.",
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
