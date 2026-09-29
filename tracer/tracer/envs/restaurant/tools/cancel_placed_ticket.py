import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class CancelPlacedTicketTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], ticket_ref: str, reason: str) -> str:
        ticket = data["service_tickets"].get(ticket_ref)
        if ticket is None:
            return "Error: Ticket not found"
        if ticket["state"] != "placed":
            return "Error: Only tickets in 'placed' state can be cancelled"

        # Record refunds for any 'payment' charges
        refunds = []
        for ch in ticket["charges"]:
            if ch["kind"] == "payment":
                refunds.append(
                    {
                        "kind": "refund",
                        "total": ch["total"],
                        "instrument_ref": ch["instrument_ref"],
                    }
                )

        ticket["charges"].extend(refunds)
        ticket["state"] = "cancelled"
        return json.dumps(ticket)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "cancel_placed_ticket",
                "description": (
                    "Cancel a placed ticket. If the ticket has already started preparation or is delivered, "
                    "it cannot be cancelled. The agent must explain the cancellation details and ask for "
                    "explicit user confirmation (yes/no) to proceed. Upon cancellation, refund entries will "
                    "be recorded for any prior payments."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticket_ref": {
                            "type": "string",
                            "description": "The ticket reference, such as 'TCKT-00001'.",
                        },
                        "reason": {
                            "type": "string",
                            "description": "The reason for cancellation (e.g., 'no longer needed', 'ordered by mistake').",
                        },
                    },
                    "required": ["ticket_ref", "reason"],
                },
            },
        }
