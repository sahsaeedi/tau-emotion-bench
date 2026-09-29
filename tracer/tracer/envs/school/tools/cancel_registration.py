import json
from typing import Any, Dict

from tracer.envs.tool import Tool


def _credits_to_status(total_credits: int) -> str:
    return "full-time" if total_credits >= 12 else "part-time"


class CancelRegistrationTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], registration_id: str) -> str:
        reg = data["registrations"].get(registration_id)
        if reg is None:
            return f"Error: Registration {registration_id} not found"

        # Refund all payments
        refunds = [
            {"payment_id": p["payment_id"], "amount": -p["amount"]}
            for p in reg["payment_history"]
        ]
        reg["payment_history"].extend(refunds)

        # Adjust enrollments
        for rc in reg["courses"]:
            course = data["courses"].get(rc["course_id"])
            if course is not None:
                course["current_enrollment"] = max(0, course["current_enrollment"] - 1)

        # Clear courses, reset credits
        reg["courses"] = []
        reg["total_credits"] = 0
        reg["overload_credits"] = 0
        reg["status"] = _credits_to_status(0)

        return json.dumps(reg)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "cancel_registration",
                "description": (
                    "Cancel a registration: issues refunds for all recorded payments (as negative "
                    "amounts), drops all courses and updates enrollments, and sets total credits and "
                    "overload credits to 0. The registration remains in the system with an empty course "
                    "list. The agent needs to present a summary of the cancellation effects and obtain "
                    "explicit user confirmation (yes/no) before calling."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "registration_id": {
                            "type": "string",
                            "description": "The registration id to cancel.",
                        },
                    },
                    "required": ["registration_id"],
                },
            },
        }
