from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any, Dict, List

from tracer.envs.tool import Tool


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


class ListMissingTelemetryUpload(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        device_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> str:
        uploads: List[Dict[str, Any]] = data.get("telemetry_uploads", [])
        device_uploads = [
            entry for entry in uploads if entry.get("device_id") == device_id
        ]

        if not device_uploads and (not start_date or not end_date):
            return json.dumps(
                {
                    "error": (
                        f"No telemetry uploads found for device {device_id}. "
                        "Provide both start_date and end_date to check for missing days."
                    )
                }
            )

        known_by_date: Dict[str, Dict[str, Any]] = {}
        for entry in device_uploads:
            entry_date = entry.get("date")
            if isinstance(entry_date, str):
                known_by_date[entry_date] = entry

        inferred_start = min(known_by_date.keys()) if known_by_date else start_date
        inferred_end = max(known_by_date.keys()) if known_by_date else end_date

        start = _parse_date(start_date or inferred_start)  # type: ignore[arg-type]
        end = _parse_date(end_date or inferred_end)  # type: ignore[arg-type]

        if start > end:
            return json.dumps(
                {"error": "start_date must be less than or equal to end_date."}
            )

        missing_days: List[Dict[str, Any]] = []
        current = start
        while current <= end:
            day = current.isoformat()
            entry = known_by_date.get(day)
            if entry is None:
                missing_days.append({"date": day, "reason": "no_upload_record"})
            elif entry.get("usage_hours") is None:
                missing_days.append({"date": day, "reason": "missing_usage_hours"})
            current += timedelta(days=1)

        return json.dumps(
            {
                "device_id": device_id,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "total_missing_days": len(missing_days),
                "missing_days": missing_days,
            },
            indent=2,
        )

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "list_missing_telemetry_upload",
                "description": (
                    "List dates in a range where telemetry usage_hours are missing for a device."
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
