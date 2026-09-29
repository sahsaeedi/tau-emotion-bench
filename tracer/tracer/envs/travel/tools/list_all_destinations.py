import json
from typing import Any, Dict, List, Set, Tuple

from tracer.envs.tool import Tool


class ListAllDestinationsTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any]) -> str:
        seen: Set[Tuple[str, str]] = set()
        dests: List[Dict[str, Any]] = []
        for pkg in data["packages"].values():
            for loc in pkg["destinations"]:
                key = (loc["city"], loc["country"])
                if key not in seen:
                    seen.add(key)
                    dests.append(loc)
        return json.dumps(dests)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "list_all_destinations",
                "description": "Return a unique list of all destinations across all packages.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }
