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


class ModifyPlacedTicketInstrumentTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], ticket_ref: str, instrument_ref: str) -> str:
        ticket = data["service_tickets"].get(ticket_ref)
        if ticket is None:
            return "Error: Ticket not found"
        if ticket["state"] != "placed":
            return "Error: Non-placed ticket cannot be modified"

        # Validate new instrument exists
        if _get_instrument(data, ticket["guest_ref"], instrument_ref) is None:
            return "Error: Payment instrument not found"

        payment_charges = [ch for ch in ticket["charges"] if ch["kind"] == "payment"]
        if len(payment_charges) != 1:
            return (
                "Error: There should be exactly one payment charge for a placed ticket"
            )

        current_payment = payment_charges[0]
        if current_payment["instrument_ref"] == instrument_ref:
            return "Error: The new instrument should be different from the current one"

        amount = current_payment["total"]

        # Append a new payment with the new instrument, and a refund to the old instrument
        ticket["charges"].extend(
            [
                {"kind": "payment", "total": amount, "instrument_ref": instrument_ref},
                {
                    "kind": "refund",
                    "total": amount,
                    "instrument_ref": current_payment["instrument_ref"],
                },
            ]
        )
        return json.dumps(ticket)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "modify_placed_ticket_instrument",
                "description": (
                    "Modify the payment instrument on a placed ticket. The agent needs to explain the change "
                    "and ask for explicit user confirmation (yes/no) to proceed. Only tickets in 'placed' "
                    "state are eligible; there must be exactly one 'payment' charge on the ticket; and the "
                    "new instrument must be different from the current one."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticket_ref": {
                            "type": "string",
                            "description": "The ticket reference, such as 'TCKT-00001'.",
                        },
                        "instrument_ref": {
                            "type": "string",
                            "description": "The new instrument reference to use for the payment.",
                        },
                    },
                    "required": ["ticket_ref", "instrument_ref"],
                },
            },
        }
