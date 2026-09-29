import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class GetPackageDetailsTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], package_id: str) -> str:
        package = data["packages"].get(package_id)
        if package is None:
            return "Error: Package not found"
        return json.dumps(package)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_package_details",
                "description": "Get full package details.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "package_id": {
                            "type": "string",
                            "description": "The package id.",
                        },
                    },
                    "required": ["package_id"],
                },
            },
        }
