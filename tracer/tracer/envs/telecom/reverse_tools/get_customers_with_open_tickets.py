import json
from typing import Any, Dict

from tracer.envs.tool import Tool

_MAX_USERS = 5
_call_counter = 0


class GetCustomersWithOpenTickets(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any]) -> str:
        global _call_counter
        tickets = data["support_tickets"]
        customers = data["customers"]
        entries = [
            {
                "customer_id": record["customer_id"],
                "email": customers.get(record["customer_id"], {})
                .get("demographics", {})
                .get("email", ""),
                "ticket_id": tid,
                "priority": record.get("priority", "medium"),
            }
            for tid, record in tickets.items()
            if record.get("status") == "open"
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
                "name": "get_customers_with_open_tickets",
                "description": (
                    "Get a paginated batch of up to 5 customers who have open support tickets. "
                    "Returns customer_id, email, ticket_id, and priority. "
                    "Use this when the trace involves looking up or modifying a support ticket."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }
