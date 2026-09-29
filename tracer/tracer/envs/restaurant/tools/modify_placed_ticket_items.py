import json
from typing import Any, Dict, List, Optional

from tracer.envs.tool import Tool


def _get_instrument(
    data: Dict[str, Any], guest_ref: str, instrument_ref: str
) -> Optional[Dict[str, Any]]:
    patron = data["patron_registry"].get(guest_ref)
    if patron is None:
        return None
    return patron["saved_instruments"].get(instrument_ref)


def _find_dish_by_plate(
    data: Dict[str, Any], plate_ref: str
) -> Optional[Dict[str, Any]]:
    for dish in data["menu_board"].values():
        if plate_ref in dish["selections"]:
            return dish
    return None


class ModifyPlacedTicketItemsTool(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        ticket_ref: str,
        plate_refs: List[str],
        new_plate_refs: List[str],
        instrument_ref: str,
    ) -> str:
        ticket = data["service_tickets"].get(ticket_ref)
        if ticket is None:
            return "Error: Ticket not found"
        if ticket["state"] != "placed":
            return "Error: Non-placed ticket cannot be modified"

        # Validate instrument exists for the patron
        if _get_instrument(data, ticket["guest_ref"], instrument_ref) is None:
            return "Error: Payment instrument not found"

        # Check counts of existing plates in ticket
        ticket_plate_refs = [entry["plate_ref"] for entry in ticket["line_entries"]]
        for pr in plate_refs:
            if plate_refs.count(pr) > ticket_plate_refs.count(pr):
                return f"Error: Plate {pr} not found in the ticket the requested number of times"

        if len(plate_refs) != len(new_plate_refs):
            return "Error: The number of plates to be modified should match"

        # Compute price differences and validate new plates
        diff_total = 0.0
        used_indices: Dict[str, int] = {}  # plate_ref -> how many times consumed
        modifications: List[Dict[str, Any]] = []  # store (index, new_plate)

        for old_pr, new_pr in zip(plate_refs, new_plate_refs):
            occurrences = used_indices.get(old_pr, 0)

            count_seen = 0
            target_idx = None
            for idx, le in enumerate(ticket["line_entries"]):
                if le["plate_ref"] == old_pr:
                    if count_seen == occurrences:
                        target_idx = idx
                        break
                    count_seen += 1

            if target_idx is None:
                return f"Error: Plate {old_pr} not found"

            used_indices[old_pr] = occurrences + 1
            old_entry = ticket["line_entries"][target_idx]

            # Validate new plate exists and belongs to the same dish as the old one
            old_dish = _find_dish_by_plate(data, old_pr)
            new_dish = _find_dish_by_plate(data, new_pr)
            if new_dish is None:
                return f"Error: New plate {new_pr} not found"
            if old_dish is None or old_dish["dish_ref"] != new_dish["dish_ref"]:
                return "Error: New plate must be from the same dish as the original"

            new_plate = new_dish["selections"][new_pr]
            if not new_plate["served_today"]:
                return f"Error: New plate {new_pr} is not available today"

            old_cost = old_entry["cost"]
            new_cost = new_plate["cost"]
            diff_total += new_cost - old_cost

            modifications.append({"index": target_idx, "new_plate": new_plate})

        # Record the payment/refund for the difference
        diff_total = round(diff_total, 2)
        if diff_total != 0:
            ticket["charges"].append(
                {
                    "kind": "payment" if diff_total > 0 else "refund",
                    "total": abs(diff_total),
                    "instrument_ref": instrument_ref,
                }
            )

        # Apply the modifications
        for mod in modifications:
            idx = mod["index"]
            plate = mod["new_plate"]
            ticket["line_entries"][idx]["plate_ref"] = plate["plate_ref"]
            ticket["line_entries"][idx]["cost"] = plate["cost"]

        return json.dumps(ticket)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "modify_placed_ticket_items",
                "description": (
                    "Modify plate selections in a placed ticket to new plate selections of the same dish. "
                    "This function can only be applied to tickets in 'placed' state. The agent needs to "
                    "explain the modification and ask for explicit user confirmation (yes/no) to proceed."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticket_ref": {
                            "type": "string",
                            "description": "The ticket reference, such as 'TCKT-00001'.",
                        },
                        "plate_refs": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "The current plate_refs to be modified; duplicates allowed.",
                        },
                        "new_plate_refs": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "The new plate_refs to replace with; must match positional count and be same dish.",
                        },
                        "instrument_ref": {
                            "type": "string",
                            "description": "The payment instrument to charge/refund the price difference.",
                        },
                    },
                    "required": [
                        "ticket_ref",
                        "plate_refs",
                        "new_plate_refs",
                        "instrument_ref",
                    ],
                },
            },
        }
