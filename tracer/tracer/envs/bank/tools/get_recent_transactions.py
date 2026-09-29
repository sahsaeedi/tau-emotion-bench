import json
from typing import Any, Dict

from tracer.envs.tool import Tool


def _account_exists(data: Dict[str, Any], account_id: str) -> bool:
    return any(account_id in client["accounts"] for client in data["clients"].values())


class GetRecentTransactionsTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], account_id: str, limit: int = 10) -> str:
        if not _account_exists(data, account_id):
            return "Error: Account not found"
        transactions = [
            tx
            for tx in data["transactions"].values()
            if tx["account_id"] == account_id and tx["status"] in ("posted", "pending")
        ]
        transactions.sort(key=lambda t: t["timestamp"], reverse=True)
        return json.dumps(transactions[: max(0, limit)])

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_recent_transactions",
                "description": "Get recent transactions for an account, most recent posted/pending transactions first.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "account_id": {
                            "type": "string",
                            "description": "The account id.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max number of transactions to return, default 10.",
                        },
                    },
                    "required": ["account_id"],
                },
            },
        }
