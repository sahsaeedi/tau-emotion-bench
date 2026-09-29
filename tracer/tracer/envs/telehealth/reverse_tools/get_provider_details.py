# Copyright Sierra

from __future__ import annotations

import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class GetProviderDetails(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], provider_id: str) -> str:
        providers = data["providers"]

        if provider_id not in providers:
            return json.dumps({"error": f"Provider with ID {provider_id} not found."})

        return json.dumps(providers[provider_id], indent=2)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_provider_details",
                "description": "Get detailed information about a healthcare provider including specialty, schedule, credentials, and contact information.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "provider_id": {
                            "type": "string",
                            "description": "The provider's unique identifier",
                        },
                    },
                    "required": ["provider_id"],
                },
            },
        }
