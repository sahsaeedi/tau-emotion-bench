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


class InitiateTransferToBeneficiaryTool(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        client_id: str,
        from_account_id: str,
        beneficiary_id: str,
        amount: float,
        method: str = "ACH",
        description: Optional[str] = None,
    ) -> str:
        if amount <= 0:
            return "Error: Amount must be greater than zero"

        client = data["clients"].get(client_id)
        if client is None:
            return "Error: Client not found"
        if from_account_id not in client["accounts"]:
            return "Error: Source account must belong to the client"

        account = client["accounts"][from_account_id]
        if account["status"] != "active":
            return "Error: Source account is not active"

        if beneficiary_id not in client["beneficiary_ids"]:
            return "Error: Beneficiary not owned by this client"
        beneficiary = data["beneficiaries"].get(beneficiary_id)
        if beneficiary is None:
            return "Error: Beneficiary not found"

        if beneficiary["status"] != "active":
            return "Error: Beneficiary is not active"
        if beneficiary["verification"]["status"] != "verified":
            return "Error: Beneficiary must be verified before transfers"
        if from_account_id not in beneficiary["allowed_from_account_ids"]:
            return (
                "Error: This account is not authorized for transfers to the beneficiary"
            )
        if amount > beneficiary["transfer_limits"]["per_transfer_limit"]:
            return "Error: Amount exceeds per-transfer limit for beneficiary"
        if account["balance"]["available"] < amount:
            return "Error: Insufficient available balance"

        account["balance"]["available"] = round(
            account["balance"]["available"] - amount, 2
        )
        account["balance"]["current"] = round(account["balance"]["current"] - amount, 2)

        tx_id = _new_transaction_id(data)
        display_name = beneficiary["name"].get("display_name") or beneficiary_id
        tx = {
            "transaction_id": tx_id,
            "client_id": client_id,
            "account_id": from_account_id,
            "timestamp": _now(),
            "type": "transfer",
            "direction": "debit",
            "amount": round(amount, 2),
            "currency": account["currency"],
            "description": description or f"Transfer to beneficiary {display_name}",
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
        return json.dumps(tx)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "initiate_transfer_to_beneficiary",
                "description": (
                    "Initiate a transfer to a verified, active beneficiary from an account the client "
                    "owns that is authorized for that beneficiary. The agent needs to explain the "
                    "details and ask for explicit user confirmation (yes/no) before calling."
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
                            "description": "Source account id.",
                        },
                        "beneficiary_id": {
                            "type": "string",
                            "description": "Beneficiary id.",
                        },
                        "amount": {
                            "type": "number",
                            "description": "Transfer amount (> 0).",
                        },
                        "method": {
                            "type": "string",
                            "enum": ["ACH", "Wire"],
                            "description": "Transfer method, default 'ACH'.",
                        },
                        "description": {
                            "type": "string",
                            "description": "Optional memo.",
                        },
                    },
                    "required": [
                        "client_id",
                        "from_account_id",
                        "beneficiary_id",
                        "amount",
                    ],
                },
            },
        }
