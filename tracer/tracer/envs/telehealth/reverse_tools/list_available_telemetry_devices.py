# Copyright Sierra

from __future__ import annotations

import json
import random
from typing import Any, Dict, List, Optional

from tracer.envs.tool import Tool

_MAX_DEVICES = 5
_call_counter = 0


class ListAvailableTelemetryDevices(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        status_filter: Optional[str] = None,
    ) -> str:
        global _call_counter

        inventory: List[Dict[str, Any]] = data.get("telemetry_inventory", [])
        if not inventory:
            return json.dumps({"total_matching": 0, "returned_count": 0, "devices": []})

        filtered = list(inventory)
        if status_filter:
            filtered = [
                item
                for item in filtered
                if item.get("status", "").lower() == status_filter.lower()
            ]
            if not filtered:
                return json.dumps(
                    {"total_matching": 0, "returned_count": 0, "devices": []}
                )

        random.shuffle(filtered)
        total = len(filtered)
        batch_size = min(_MAX_DEVICES, total)
        offset = (_call_counter * batch_size) % total
        _call_counter += 1
        doubled = filtered + filtered
        batch = doubled[offset : offset + batch_size]

        return json.dumps(
            {"total_matching": total, "returned_count": len(batch), "devices": batch},
            indent=2,
        )

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "list_available_telemetry_devices",
                "description": (
                    "List telemetry devices in inventory, optionally filtered by status "
                    "(e.g. available, deployed, shipped). "
                    "The list is randomized; each call returns the next batch "
                    f"(up to {_MAX_DEVICES} devices, different from previous calls)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "status_filter": {
                            "type": "string",
                            "description": "Optional status filter (e.g., 'available', 'deployed', 'shipped').",
                        },
                    },
                    "required": [],
                },
            },
        }
