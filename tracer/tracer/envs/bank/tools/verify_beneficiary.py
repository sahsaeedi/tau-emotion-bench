import json
from datetime import datetime
from typing import Any, Dict

from tracer.envs.tool import Tool


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


class VerifyBeneficiaryTool(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        client_id: str,
        beneficiary_id: str,
        method: str = "document",
    ) -> str:
        client = data["clients"].get(client_id)
        if client is None:
            return "Error: Client not found"
        if beneficiary_id not in client["beneficiary_ids"]:
            return "Error: Beneficiary not owned by this client"
        beneficiary = data["beneficiaries"].get(beneficiary_id)
        if beneficiary is None:
            return "Error: Beneficiary not found"

        beneficiary["verification"]["status"] = "verified"
        beneficiary["verification"]["method"] = method
        beneficiary["verification"]["verified_at"] = _now()
        return json.dumps(beneficiary)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "verify_beneficiary",
                "description": (
                    "Mark a beneficiary as verified. The agent should confirm with the user before proceeding."
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
                            "description": "The beneficiary id.",
                        },
                        "method": {
                            "type": "string",
                            "enum": ["micro_deposits", "document", "instant"],
                            "description": "Verification method label, default 'document'.",
                        },
                    },
                    "required": ["client_id", "beneficiary_id"],
                },
            },
        }
