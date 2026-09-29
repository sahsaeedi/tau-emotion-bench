from __future__ import annotations

import json
from typing import Any, Dict, List

from tracer.envs.tool import Tool


def _patient_exists(patients: Any, patient_id: str) -> bool:
    if isinstance(patients, dict):
        return patient_id in patients
    if isinstance(patients, list):
        return any(
            (p.get("patient_id") == patient_id) for p in patients if isinstance(p, dict)
        )
    return False


class ListAssignedTelemetryDevices(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], patient_id: str) -> str:
        patients = data.get("patients") or {}
        if not _patient_exists(patients, patient_id):
            return json.dumps(
                {
                    "patient_id": patient_id,
                    "total_assigned": 0,
                    "devices": [],
                    "error": "patient_not_found",
                },
                indent=2,
            )

        inventory: List[Dict[str, Any]] = data.get("telemetry_inventory", [])
        assigned_devices = [
            {
                "device_id": item.get("device_id"),
                "device_type": item.get("device_type"),
                "status": item.get("status"),
                "last_audit": item.get("last_audit"),
                "notes": item.get("notes"),
            }
            for item in inventory
            if item.get("assigned_to") == patient_id
        ]
        assigned_devices.sort(key=lambda item: item.get("device_id") or "")

        return json.dumps(
            {
                "patient_id": patient_id,
                "total_assigned": len(assigned_devices),
                "devices": assigned_devices,
            },
            indent=2,
        )

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "list_assigned_telemetry_devices",
                "description": "List telemetry devices currently assigned to a specific patient.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "patient_id": {
                            "type": "string",
                            "description": "Patient identifier to check for assigned telemetry devices.",
                        }
                    },
                    "required": ["patient_id"],
                },
            },
        }
