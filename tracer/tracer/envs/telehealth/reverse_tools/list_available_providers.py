# Copyright Sierra

from __future__ import annotations

import json
import random
from typing import Any, Dict, List, Optional

from tracer.envs.tool import Tool

_MAX_PROVIDERS = 5
_call_counter = 0


class ListAvailableProviders(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], specialty: Optional[str] = None) -> str:
        global _call_counter

        providers = data["providers"]

        filtered: List[Dict[str, Any]] = []
        for provider_id, provider_info in providers.items():
            if (
                specialty is not None
                and provider_info["specialty"].lower() != specialty.lower()
            ):
                continue
            entry = dict(provider_info)
            entry["provider_id"] = provider_id
            filtered.append(entry)

        if not filtered:
            return json.dumps(
                {"total_matching": 0, "returned_count": 0, "providers": []}
            )

        random.shuffle(filtered)
        total = len(filtered)
        batch_size = min(_MAX_PROVIDERS, total)
        offset = (_call_counter * batch_size) % total
        _call_counter += 1
        doubled = filtered + filtered
        batch = doubled[offset : offset + batch_size]

        return json.dumps(
            {"total_matching": total, "returned_count": len(batch), "providers": batch},
            indent=2,
        )

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "list_available_providers",
                "description": (
                    "List available healthcare providers, optionally filtered by specialty "
                    "(e.g., Primary Care, Cardiology, Dermatology, Psychiatry). "
                    "The list is randomized; each call returns the next batch "
                    f"(up to {_MAX_PROVIDERS} providers, different from previous calls)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "specialty": {
                            "type": "string",
                            "description": "Optional specialty to filter providers by (e.g., 'Primary Care', 'Cardiology').",
                        },
                    },
                    "required": [],
                },
            },
        }
