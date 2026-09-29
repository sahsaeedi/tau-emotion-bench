import json
from typing import Any, Dict, Optional, Tuple

from tracer.envs.tool import Tool


def _find_account(
    data: Dict[str, Any], account_id: str
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    for client_id, client in data["clients"].items():
        if account_id in client["accounts"]:
            return client_id, client["accounts"][account_id]
    return None, None


class GetAccountDetailsTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], account_id: str) -> str:
        _, account = _find_account(data, account_id)
        if account is None:
            return "Error: Account not found"
        return json.dumps(account)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_account_details",
                "description": "Get the details of an account by account id.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "account_id": {
                            "type": "string",
                            "description": "The account id.",
                        },
                    },
                    "required": ["account_id"],
                },
            },
        }
