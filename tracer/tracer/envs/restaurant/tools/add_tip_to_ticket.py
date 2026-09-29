import json
from typing import Any, Dict, Optional

from tracer.envs.tool import Tool


def _get_instrument(
    data: Dict[str, Any], guest_ref: str, instrument_ref: str
) -> Optional[Dict[str, Any]]:
    patron = data["patron_registry"].get(guest_ref)
    if patron is None:
        return None
    return patron["saved_instruments"].get(instrument_ref)


class AddTipToTicketTool(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any], ticket_ref: str, tip_total: float, instrument_ref: str
    ) -> str:
        ticket = data["service_tickets"].get(ticket_ref)
        if ticket is None:
            return "Error: Ticket not found"
        if ticket["state"] == "cancelled":
            return "Error: Cannot add tip to a cancelled ticket"
        if tip_total < 0:
            return "Error: Tip amount must be non-negative"

        # Validate instrument
        if _get_instrument(data, ticket["guest_ref"], instrument_ref) is None:
            return "Error: Payment instrument not found"

        ticket["charges"].append(
            {
                "kind": "tip",
                "total": round(float(tip_total), 2),
                "instrument_ref": instrument_ref,
            }
        )
        return json.dumps(ticket)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "add_tip_to_ticket",
                "description": (
                    "Add a tip to a ticket. The agent must explain the tip addition and ask for explicit "
                    "user confirmation (yes/no) to proceed. Tip can be added as long as the ticket is not "
                    "cancelled; the tip is charged to the specified instrument."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticket_ref": {
                            "type": "string",
                            "description": "The ticket reference, such as 'TCKT-00001'.",
                        },
                        "tip_total": {
                            "type": "number",
                            "description": "The tip amount to add (must be non-negative).",
                        },
                        "instrument_ref": {
                            "type": "string",
                            "description": "The instrument reference to charge the tip.",
                        },
                    },
                    "required": ["ticket_ref", "tip_total", "instrument_ref"],
                },
            },
        }
