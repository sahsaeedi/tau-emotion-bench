import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class PayRegistrationTool(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any], registration_id: str, payment: Dict[str, Any]
    ) -> str:
        reg = data["registrations"].get(registration_id)
        if reg is None:
            return f"Error: Registration {registration_id} not found"
        student = data["students"].get(reg["student_id"])
        if student is None:
            return f"Error: Student {reg['student_id']} not found"

        if payment.get("payment_id") not in student["payment_methods"]:
            return f"Error: Payment method {payment.get('payment_id')} not found for student {student['student_id']}"

        reg["payment_history"].append(payment)
        return json.dumps(reg)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "pay_registration",
                "description": "Record a payment (or refund with negative amount) for a registration.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "registration_id": {
                            "type": "string",
                            "description": "The registration ID.",
                        },
                        "payment": {
                            "type": "object",
                            "description": "Payment object with payment_id and amount.",
                            "properties": {
                                "payment_id": {
                                    "type": "string",
                                    "description": "Saved payment method ID.",
                                },
                                "amount": {
                                    "type": "integer",
                                    "description": "Payment amount in dollars (negative for a refund).",
                                },
                            },
                            "required": ["payment_id", "amount"],
                        },
                    },
                    "required": ["registration_id", "payment"],
                },
            },
        }
