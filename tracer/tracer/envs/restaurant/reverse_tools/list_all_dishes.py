import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class ListAllDishesTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any]) -> str:
        mapping = {
            dish["title"]: dish["dish_ref"] for dish in data["menu_board"].values()
        }
        return json.dumps(mapping, sort_keys=True)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "list_all_dishes",
                "description": "List the title and dish_ref of all dishes, as a JSON string mapping dish titles to their dish_refs, sorted alphabetically by title.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }
