import json
from typing import Any, Dict, Optional, Tuple

from tracer.envs.tool import Tool


def _find_card(
    data: Dict[str, Any], card_id: str
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    for client_id, client in data["clients"].items():
        if card_id in client["cards"]:
            return client_id, client["cards"][card_id]
    return None, None


class FreezeCardTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], card_id: str, reason: str) -> str:
        _, card = _find_card(data, card_id)
        if card is None:
            return "Error: Card not found"
        if card["status"] not in ("active", "blocked"):
            return "Error: Card not in a manageable state"
        if card["status"] == "blocked":
            return json.dumps(card)
        card["status"] = "blocked"
        return json.dumps(card)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "freeze_card",
                "description": (
                    "Block (freeze) a card. The agent needs to explain and ask for explicit "
                    "user confirmation (yes/no) before calling."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "card_id": {"type": "string", "description": "The card id."},
                        "reason": {
                            "type": "string",
                            "description": "Reason for freezing/blocking the card.",
                        },
                    },
                    "required": ["card_id", "reason"],
                },
            },
        }
