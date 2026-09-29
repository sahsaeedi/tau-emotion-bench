import json
from typing import Any, Dict

from tracer.envs.tool import Tool

_MAX_USERS = 5
_call_counter = 0


class GetCustomersWithOutstandingBalance(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any]) -> str:
        global _call_counter
        billing = data["billing"]
        customers = data["customers"]
        entries = [
            {
                "customer_id": cid,
                "email": customers.get(cid, {})
                .get("demographics", {})
                .get("email", ""),
                "current_balance": record["current_balance"],
            }
            for cid, record in billing.items()
            if record.get("current_balance", 0) > 0
        ]
        if not entries:
            return json.dumps([])
        offset = (_call_counter * _MAX_USERS) % len(entries)
        _call_counter += 1
        doubled = entries + entries
        return json.dumps(doubled[offset : offset + _MAX_USERS])

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_customers_with_outstanding_balance",
                "description": (
                    "Get a paginated batch of up to 5 customers who have an outstanding balance "
                    "(current_balance > 0). Returns customer_id, email, and current_balance. "
                    "Use this when the trace involves recording a payment or resolving a billing dispute."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }
