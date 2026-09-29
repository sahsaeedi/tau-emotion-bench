import json
from typing import Any, Dict

from tracer.envs.tool import Tool

_MAX_USERS = 5
_call_counter = 0


class GetCustomersByService(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], service_id: str) -> str:
        global _call_counter
        customers = data["customers"]
        entries = [
            {
                "customer_id": cid,
                "email": info.get("demographics", {}).get("email", ""),
                "services": info.get("services", []),
            }
            for cid, info in customers.items()
            if service_id in info.get("services", [])
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
                "name": "get_customers_by_service",
                "description": (
                    "Get a paginated batch of up to 5 customers who have a specific service. "
                    "Returns customer_id, email, and their full services list. "
                    "Use this when the trace involves removing or modifying a specific service "
                    "to ensure the customer actually has that service."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "service_id": {
                            "type": "string",
                            "description": (
                                "The service identifier to filter by, such as 'mobile_unlimited', "
                                "'internet_fiber_1gb', or 'tv_premium'."
                            ),
                        },
                    },
                    "required": ["service_id"],
                },
            },
        }
