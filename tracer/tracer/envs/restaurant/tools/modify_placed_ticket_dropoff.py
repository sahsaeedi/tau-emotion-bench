import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class ModifyPlacedTicketDropoffTool(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        ticket_ref: str,
        line_one: str,
        line_two: str,
        municipality: str,
        province: str,
        nation: str,
        postal_code: str,
    ) -> str:
        ticket = data["service_tickets"].get(ticket_ref)
        if ticket is None:
            return "Error: Ticket not found"
        if ticket["state"] != "placed":
            return "Error: Non-placed ticket cannot be modified"
        if ticket["service_mode"] != "delivery":
            return "Error: Only delivery tickets have a dropoff address"

        ticket["dropoff"] = {
            "line_one": line_one,
            "line_two": line_two,
            "municipality": municipality,
            "nation": nation,
            "province": province,
            "postal_code": postal_code,
        }
        return json.dumps(ticket)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "modify_placed_ticket_dropoff",
                "description": (
                    "Modify the dropoff address of a placed delivery ticket. The agent must explain the "
                    "update and ask for explicit user confirmation (yes/no) to proceed."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticket_ref": {
                            "type": "string",
                            "description": "The ticket reference, such as 'TCKT-00001'.",
                        },
                        "line_one": {
                            "type": "string",
                            "description": "Primary address line.",
                        },
                        "line_two": {
                            "type": "string",
                            "description": "Secondary address line.",
                        },
                        "municipality": {
                            "type": "string",
                            "description": "City or municipality.",
                        },
                        "province": {
                            "type": "string",
                            "description": "State or province.",
                        },
                        "nation": {"type": "string", "description": "Country name."},
                        "postal_code": {
                            "type": "string",
                            "description": "Postal or ZIP code.",
                        },
                    },
                    "required": [
                        "ticket_ref",
                        "line_one",
                        "line_two",
                        "municipality",
                        "province",
                        "nation",
                        "postal_code",
                    ],
                },
            },
        }
