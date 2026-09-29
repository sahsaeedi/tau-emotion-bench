import json
from typing import Any, Dict, Optional

from tracer.envs.tool import Tool


class SearchTransactionsTool(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        client_id: str,
        account_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        min_amount: Optional[float] = None,
        max_amount: Optional[float] = None,
        transaction_type: Optional[str] = None,
        status: Optional[str] = None,
        merchant_name_contains: Optional[str] = None,
    ) -> str:
        client = data["clients"].get(client_id)
        if client is None:
            return "Error: Client not found"
        if account_id not in client["accounts"]:
            return "Error: Account not found for this client"

        def in_range(ts: str) -> bool:
            if start_date and ts < start_date:
                return False
            if end_date and ts > end_date:
                return False
            return True

        def amount_ok(a: float) -> bool:
            if min_amount is not None and a < min_amount:
                return False
            if max_amount is not None and a > max_amount:
                return False
            return True

        m_sub = merchant_name_contains.lower() if merchant_name_contains else None

        results = []
        for tx in data["transactions"].values():
            if tx["account_id"] != account_id:
                continue
            if not in_range(tx["timestamp"]):
                continue
            if not amount_ok(tx["amount"]):
                continue
            if transaction_type and tx["type"] != transaction_type:
                continue
            if status and tx["status"] != status:
                continue
            if m_sub:
                merchant = tx.get("merchant") or {}
                mname = (merchant.get("name") or "").lower()
                if m_sub not in mname:
                    continue
            results.append(tx)

        results.sort(key=lambda t: t["timestamp"], reverse=True)
        return json.dumps(results)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "search_transactions",
                "description": "Search transactions for a client account with optional filters, sorted by timestamp descending.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "client_id": {
                            "type": "string",
                            "description": "The client id.",
                        },
                        "account_id": {
                            "type": "string",
                            "description": "The account id owned by the client.",
                        },
                        "start_date": {
                            "type": "string",
                            "description": "ISO timestamp lower bound (inclusive).",
                        },
                        "end_date": {
                            "type": "string",
                            "description": "ISO timestamp upper bound (inclusive).",
                        },
                        "min_amount": {
                            "type": "number",
                            "description": "Minimum amount filter.",
                        },
                        "max_amount": {
                            "type": "number",
                            "description": "Maximum amount filter.",
                        },
                        "transaction_type": {
                            "type": "string",
                            "description": "Transaction type filter.",
                        },
                        "status": {
                            "type": "string",
                            "description": "Transaction status filter.",
                        },
                        "merchant_name_contains": {
                            "type": "string",
                            "description": "Case-insensitive substring to match merchant name.",
                        },
                    },
                    "required": ["client_id", "account_id"],
                },
            },
        }
