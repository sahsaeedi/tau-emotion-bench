import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from tracer.envs.tool import Tool


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


class AddBeneficiaryTool(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        client_id: str,
        beneficiary_id: str,
        beneficiary_type: str,
        bank_name: str,
        account_number_masked: str,
        address1: str,
        address2: str,
        city: str,
        state: str,
        zip: str,
        country: str,
        allowed_from_account_ids: List[str],
        per_transfer_limit: float,
        daily_limit: float,
        display_name: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        business_name: Optional[str] = None,
        routing_number: Optional[str] = None,
        iban: Optional[str] = None,
        swift_bic: Optional[str] = None,
        verification_method: str = "document",
    ) -> str:
        client = data["clients"].get(client_id)
        if client is None:
            return "Error: Client not found"

        for account_id in allowed_from_account_ids:
            if account_id not in client["accounts"]:
                return f"Error: Allowed account {account_id} does not belong to client"

        beneficiary = {
            "beneficiary_id": beneficiary_id,
            "client_id": client_id,
            "name": {
                "display_name": display_name,
                "first_name": first_name,
                "last_name": last_name,
                "business_name": business_name,
            },
            "type": beneficiary_type,
            "bank_details": {
                "bank_name": bank_name,
                "account_number_masked": account_number_masked,
                "routing_number": routing_number,
                "iban": iban,
                "swift_bic": swift_bic,
            },
            "address": {
                "address1": address1,
                "address2": address2,
                "city": city,
                "state": state,
                "zip": zip,
                "country": country,
            },
            "allowed_from_account_ids": allowed_from_account_ids,
            "transfer_limits": {
                "per_transfer_limit": per_transfer_limit,
                "daily_limit": daily_limit,
            },
            "verification": {
                "status": "pending",
                "method": verification_method,
                "verified_at": None,
            },
            "status": "active",
            "created_at": _now(),
            "notes": None,
        }

        data["beneficiaries"][beneficiary_id] = beneficiary
        if beneficiary_id not in client["beneficiary_ids"]:
            client["beneficiary_ids"].append(beneficiary_id)

        return json.dumps(beneficiary)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "add_beneficiary",
                "description": (
                    "Add a beneficiary for a client. The agent needs to explain the details and ask "
                    "for explicit user confirmation (yes/no) before calling. The new beneficiary is "
                    "created with verification status 'pending'."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "client_id": {
                            "type": "string",
                            "description": "The client id.",
                        },
                        "beneficiary_id": {
                            "type": "string",
                            "description": "Identifier to assign to the new beneficiary.",
                        },
                        "beneficiary_type": {
                            "type": "string",
                            "enum": ["individual", "business"],
                            "description": "Type of beneficiary.",
                        },
                        "display_name": {
                            "type": "string",
                            "description": "Display name for the beneficiary.",
                        },
                        "first_name": {
                            "type": "string",
                            "description": "First name of the beneficiary.",
                        },
                        "last_name": {
                            "type": "string",
                            "description": "Last name of the beneficiary.",
                        },
                        "business_name": {
                            "type": "string",
                            "description": "Business name, if beneficiary is a business.",
                        },
                        "bank_name": {
                            "type": "string",
                            "description": "Name of the beneficiary's bank.",
                        },
                        "account_number_masked": {
                            "type": "string",
                            "description": "Masked account number for the beneficiary.",
                        },
                        "routing_number": {
                            "type": "string",
                            "description": "Routing number for domestic transfers.",
                        },
                        "iban": {
                            "type": "string",
                            "description": "IBAN for international transfers.",
                        },
                        "swift_bic": {
                            "type": "string",
                            "description": "SWIFT/BIC code for international transfers.",
                        },
                        "address1": {
                            "type": "string",
                            "description": "Primary address line.",
                        },
                        "address2": {
                            "type": "string",
                            "description": "Secondary address line.",
                        },
                        "city": {"type": "string", "description": "City name."},
                        "state": {
                            "type": "string",
                            "description": "State or province name.",
                        },
                        "zip": {"type": "string", "description": "Postal code."},
                        "country": {"type": "string", "description": "Country name."},
                        "allowed_from_account_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Account IDs (must belong to this client) from which transfers to this beneficiary are allowed.",
                        },
                        "per_transfer_limit": {
                            "type": "number",
                            "description": "Maximum amount per transfer.",
                        },
                        "daily_limit": {
                            "type": "number",
                            "description": "Maximum total daily transfer limit.",
                        },
                        "verification_method": {
                            "type": "string",
                            "enum": ["micro_deposits", "document", "instant"],
                            "description": "Verification method to use, default 'document'.",
                        },
                    },
                    "required": [
                        "client_id",
                        "beneficiary_id",
                        "beneficiary_type",
                        "bank_name",
                        "account_number_masked",
                        "address1",
                        "address2",
                        "city",
                        "state",
                        "zip",
                        "country",
                        "allowed_from_account_ids",
                        "per_transfer_limit",
                        "daily_limit",
                    ],
                },
            },
        }
