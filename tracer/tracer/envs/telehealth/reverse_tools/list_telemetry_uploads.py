from __future__ import annotations

import json
from typing import Any, Dict, List

from tracer.envs.tool import Tool


class ListTelemetryUploads(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        device_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> str:
        uploads: List[Dict[str, Any]] = data.get("telemetry_uploads", [])

        filtered: List[Dict[str, Any]] = []
        for entry in uploads:
            if entry.get("device_id") != device_id:
                continue
            entry_date = entry.get("date")
            if start_date and entry_date < start_date:
                continue
            if end_date and entry_date > end_date:
                continue
            filtered.append(
                {
                    "date": entry_date,
                    "usage_hours": entry.get("usage_hours"),
                }
            )

        filtered.sort(key=lambda item: item.get("date") or "")

        return json.dumps(
            {
                "device_id": device_id,
                "start_date": start_date,
                "end_date": end_date,
                "total_days_returned": len(filtered),
                "uploads": filtered,
            },
            indent=2,
        )

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "list_telemetry_uploads",
                "description": (
                    "List telemetry usage_hours by day for a device, with optional date window filtering."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device_id": {
                            "type": "string",
                            "description": "Unique identifier of the telemetry device.",
                        },
                        "start_date": {
                            "type": "string",
                            "description": "Optional start date (inclusive, YYYY-MM-DD).",
                        },
                        "end_date": {
                            "type": "string",
                            "description": "Optional end date (inclusive, YYYY-MM-DD).",
                        },
                    },
                    "required": ["device_id"],
                },
            },
        }
