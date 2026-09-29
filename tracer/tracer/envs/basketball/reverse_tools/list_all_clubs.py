import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class ListAllClubsTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any]) -> str:
        club_dict = {club["name"]: club["club_id"] for club in data["clubs"].values()}
        return json.dumps(club_dict, sort_keys=True)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "list_all_clubs",
                "description": "List the name and club id of all clubs, sorted alphabetically by name.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }
