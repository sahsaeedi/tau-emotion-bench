import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class GetBeneficiaryDetails(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], beneficiary_id: str) -> str:
        beneficiary = data["beneficiaries"].get(beneficiary_id)
        if beneficiary is None:
            return "Error: Beneficiary not found"
        return json.dumps(beneficiary)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_beneficiary_details",
                "description": "Get the details of a beneficiary by beneficiary id.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "beneficiary_id": {
                            "type": "string",
                            "description": "The beneficiary id.",
                        },
                    },
                    "required": ["beneficiary_id"],
                },
            },
        }
