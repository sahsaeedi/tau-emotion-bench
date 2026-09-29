import json
from typing import Any, Dict

from tracer.envs.tool import Tool

_MAX_USERS = 5
_call_counter = 0


class GetCustomersWithSeniorPlan(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any]) -> str:
        global _call_counter
        customers = data["customers"]
        entries = [
            {
                "customer_id": cid,
                "email": info.get("demographics", {}).get("email", ""),
                "services": info.get("services", []),
            }
            for cid, info in customers.items()
            if "mobile_senior" in info.get("services", [])
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
                "name": "get_customers_with_senior_plan",
                "description": (
                    "Get a paginated batch of up to 5 customers who are on the senior mobile plan "
                    "(mobile_senior). Returns customer_id, email, and their services list. "
                    "Use this when the trace involves applying a senior discount."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }
