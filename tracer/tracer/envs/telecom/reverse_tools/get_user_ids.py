import json
from typing import Any, Dict

from tracer.envs.tool import Tool

_MAX_USERS = 5
_call_counter = 0


class GetUserIds(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any]) -> str:
        global _call_counter
        customers = data["customers"]
        entries = [
            {
                "customer_id": cid,
                "email": info.get("demographics", {}).get("email", ""),
                "phone": info.get("demographics", {}).get("phone", ""),
            }
            for cid, info in customers.items()
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
                "name": "get_user_ids",
                "description": (
                    "Get a paginated batch of up to 5 customer records, each containing "
                    "customer_id, email, and phone. Each call returns a different batch. "
                    "Use this to find a real customer to ground a task in."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }
