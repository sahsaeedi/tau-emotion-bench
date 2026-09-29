import json
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from tracer.envs.tool import Tool


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _new_transaction_id(data: Dict[str, Any]) -> str:
    while True:
        tid = "TXN" + uuid.uuid4().hex[:8].upper()
        if tid not in data["transactions"]:
            return tid


class MakeLoanPaymentTool(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        client_id: str,
        loan_id: str,
        from_account_id: str,
        amount: float,
        method: str = "Internal",
        description: Optional[str] = None,
    ) -> str:
        if amount <= 0:
            return "Error: Amount must be greater than zero"

        client = data["clients"].get(client_id)
        if client is None:
            return "Error: Client not found"
        if from_account_id not in client["accounts"]:
            return "Error: Source account must belong to the client"

        loan = data["loans"].get(loan_id)
        if loan is None:
            return "Error: Loan not found"
        if loan["client_id"] != client_id:
            return "Error: Loan does not belong to the client"

        account = client["accounts"][from_account_id]
        if account["status"] != "active":
            return "Error: Source account is not active"
        if account["balance"]["available"] < amount:
            return "Error: Insufficient available balance"

        account["balance"]["available"] = round(
            account["balance"]["available"] - amount, 2
        )
        account["balance"]["current"] = round(account["balance"]["current"] - amount, 2)

        tx_id = _new_transaction_id(data)
        tx = {
            "transaction_id": tx_id,
            "client_id": client_id,
            "account_id": from_account_id,
            "timestamp": _now(),
            "type": "payment",
            "direction": "debit",
            "amount": round(amount, 2),
            "currency": account["currency"],
            "description": description or f"Loan payment {loan_id}",
            "method": method,
            "status": "posted",
            "merchant": None,
            "related_transaction_id": None,
            "exchange": None,
            "fees": [],
            "hold": None,
            "balance_after": account["balance"]["current"],
        }
        data["transactions"][tx_id] = tx

        loan.setdefault("repayment_history", []).append(
            {
                "transaction_id": tx_id,
                "posted_at": tx["timestamp"],
                "amount": tx["amount"],
                "currency": tx["currency"],
                "method": tx["method"],
                "principal_component": tx["amount"],
                "interest_component": 0.0,
                "fees_component": 0.0,
            }
        )

        return json.dumps(tx)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "make_loan_payment",
                "description": (
                    "Make a loan payment from a client-owned account. Allocation is simplified "
                    "(principal only). The agent needs to explain the details and ask for explicit "
                    "user confirmation (yes/no) before calling."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "client_id": {
                            "type": "string",
                            "description": "The client id.",
                        },
                        "loan_id": {"type": "string", "description": "The loan id."},
                        "from_account_id": {
                            "type": "string",
                            "description": "Source account id.",
                        },
                        "amount": {
                            "type": "number",
                            "description": "Payment amount (> 0).",
                        },
                        "method": {
                            "type": "string",
                            "description": 'Transaction method ("Internal", "ACH", "Wire", etc.), default \'Internal\'.',
                        },
                        "description": {
                            "type": "string",
                            "description": "Optional memo.",
                        },
                    },
                    "required": ["client_id", "loan_id", "from_account_id", "amount"],
                },
            },
        }
