import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class GetDishDetailsTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], dish_ref: str) -> str:
        dish = data["menu_board"].get(dish_ref)
        if dish is None:
            return "Error: Dish not found"
        return json.dumps(dish)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_dish_details",
                "description": "Get the menu details of a dish.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "dish_ref": {
                            "type": "string",
                            "description": "The dish reference, such as 'DISH-0001'.",
                        },
                    },
                    "required": ["dish_ref"],
                },
            },
        }
