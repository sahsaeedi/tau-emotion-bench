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


class InitiateInternalTransferTool(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        client_id: str,
        from_account_id: str,
        to_account_id: str,
        amount: float,
        description: Optional[str] = None,
    ) -> str:
        if amount <= 0:
            return "Error: Amount must be greater than zero"

        client = data["clients"].get(client_id)
        if client is None:
            return "Error: Client not found"
        if (
            from_account_id not in client["accounts"]
            or to_account_id not in client["accounts"]
        ):
            return "Error: Both accounts must belong to the same client"

        from_acc = client["accounts"][from_account_id]
        to_acc = client["accounts"][to_account_id]

        if from_acc["status"] != "active":
            return "Error: Source account is not active"
        if to_acc["status"] != "active":
            return "Error: Destination account is not active"
        if from_acc["type"] == "credit":
            return "Error: Transfers from a credit account are not supported"
        if from_acc["currency"] != to_acc["currency"]:
            return "Error: Cross-currency internal transfers are not supported"
        if from_acc["balance"]["available"] < amount:
            return "Error: Insufficient available balance"

        ts_now = _now()
        currency = from_acc["currency"]

        from_acc["balance"]["available"] = round(
            from_acc["balance"]["available"] - amount, 2
        )
        from_acc["balance"]["current"] = round(
            from_acc["balance"]["current"] - amount, 2
        )
        to_acc["balance"]["available"] = round(
            to_acc["balance"]["available"] + amount, 2
        )
        to_acc["balance"]["current"] = round(to_acc["balance"]["current"] + amount, 2)

        tx_id_out = _new_transaction_id(data)
        tx_out = {
            "transaction_id": tx_id_out,
            "client_id": client_id,
            "account_id": from_account_id,
            "timestamp": ts_now,
            "type": "transfer",
            "direction": "debit",
            "amount": round(amount, 2),
            "currency": currency,
            "description": description or f"Internal transfer to {to_account_id}",
            "method": "Internal",
            "status": "posted",
            "merchant": None,
            "related_transaction_id": None,
            "exchange": None,
            "fees": [],
            "hold": None,
            "balance_after": from_acc["balance"]["current"],
        }

        tx_id_in = _new_transaction_id(data)
        tx_in = {
            "transaction_id": tx_id_in,
            "client_id": client_id,
            "account_id": to_account_id,
            "timestamp": ts_now,
            "type": "transfer",
            "direction": "credit",
            "amount": round(amount, 2),
            "currency": currency,
            "description": description or f"Internal transfer from {from_account_id}",
            "method": "Internal",
            "status": "posted",
            "merchant": None,
            "related_transaction_id": tx_id_out,
            "exchange": None,
            "fees": [],
            "hold": None,
            "balance_after": to_acc["balance"]["current"],
        }
        tx_out["related_transaction_id"] = tx_id_in

        data["transactions"][tx_id_out] = tx_out
        data["transactions"][tx_id_in] = tx_in

        return json.dumps([tx_out, tx_in])

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "initiate_internal_transfer",
                "description": (
                    "Initiate an internal transfer between two accounts owned by the same client. "
                    "Both accounts must be active and share the same currency; the source account "
                    "cannot be a credit account. The agent needs to explain the details and ask for "
                    "explicit user confirmation (yes/no) before calling."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "client_id": {
                            "type": "string",
                            "description": "The client id.",
                        },
                        "from_account_id": {
                            "type": "string",
                            "description": "The source account id.",
                        },
                        "to_account_id": {
                            "type": "string",
                            "description": "The destination account id.",
                        },
                        "amount": {
                            "type": "number",
                            "description": "Transfer amount (> 0).",
                        },
                        "description": {
                            "type": "string",
                            "description": "Optional memo/description.",
                        },
                    },
                    "required": [
                        "client_id",
                        "from_account_id",
                        "to_account_id",
                        "amount",
                    ],
                },
            },
        }
