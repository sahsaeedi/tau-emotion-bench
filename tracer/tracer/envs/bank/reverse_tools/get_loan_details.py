import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class GetLoanDetailsTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], loan_id: str) -> str:
        loan = data["loans"].get(loan_id)
        if loan is None:
            return "Error: Loan not found"
        return json.dumps(loan)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_loan_details",
                "description": "Get the details of a loan by loan id.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "loan_id": {
                            "type": "string",
                            "description": "The loan id.",
                        },
                    },
                    "required": ["loan_id"],
                },
            },
        }
