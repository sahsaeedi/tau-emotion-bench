import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class GetTicketDetailsTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], ticket_ref: str) -> str:
        ticket = data["service_tickets"].get(ticket_ref)
        if ticket is None:
            return "Error: Ticket not found"
        return json.dumps(ticket)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_ticket_details",
                "description": "Get the current state and details of a service ticket.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticket_ref": {
                            "type": "string",
                            "description": "The ticket reference, such as 'TCKT-00001'.",
                        },
                    },
                    "required": ["ticket_ref"],
                },
            },
        }
