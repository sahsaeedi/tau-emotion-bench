import json
from typing import Any, Dict

from tracer.envs.tool import Tool

_MAX_USERS = 5
_call_counter = 0


class GetCustomersWithDevices(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any]) -> str:
        global _call_counter
        customers = data["customers"]
        entries = [
            {
                "customer_id": cid,
                "email": info.get("demographics", {}).get("email", ""),
                "devices": [d["name"] for d in info.get("devices", [])],
            }
            for cid, info in customers.items()
            if info.get("devices")
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
                "name": "get_customers_with_devices",
                "description": (
                    "Get a paginated batch of up to 5 customers who have at least one device. "
                    "Returns customer_id, email, and a list of their device names. "
                    "Use this when the trace involves troubleshooting a device to ensure "
                    "the customer actually owns that device."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }
