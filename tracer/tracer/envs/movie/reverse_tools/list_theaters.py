import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class ListTheatersTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any]) -> str:
        theaters = [
            {"theater_id": t["theater_id"], "name": t["name"]}
            for t in data["theaters"].values()
        ]
        return json.dumps(theaters)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "list_theaters",
                "description": "List all theaters.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }
