import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class ListDepartmentsTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any]) -> str:
        departments = sorted({c["department"] for c in data["courses"].values()})
        return json.dumps(departments)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "list_departments",
                "description": "List all unique departments.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }
