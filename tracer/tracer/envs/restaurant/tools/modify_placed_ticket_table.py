import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class ModifyPlacedTicketTableTool(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any], ticket_ref: str, zone: str, table_no: str, seat_count: int
    ) -> str:
        ticket = data["service_tickets"].get(ticket_ref)
        if ticket is None:
            return "Error: Ticket not found"
        if ticket["state"] != "placed":
            return "Error: Non-placed ticket cannot be modified"
        if ticket["service_mode"] != "dine_in":
            return "Error: Only dine-in tickets have table information"

        ticket["table_info"] = {
            "zone": zone,
            "table_no": table_no,
            "seat_count": seat_count,
        }
        return json.dumps(ticket)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "modify_placed_ticket_table",
                "description": (
                    "Modify the table information for a placed dine-in ticket. The agent must explain the "
                    "update and ask for explicit user confirmation (yes/no) to proceed."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticket_ref": {
                            "type": "string",
                            "description": "The ticket reference, such as 'TCKT-00001'.",
                        },
                        "zone": {
                            "type": "string",
                            "description": "Dining area or zone identifier.",
                        },
                        "table_no": {"type": "string", "description": "Table number."},
                        "seat_count": {
                            "type": "integer",
                            "description": "Number of seats at the table.",
                        },
                    },
                    "required": ["ticket_ref", "zone", "table_no", "seat_count"],
                },
            },
        }
