# Copyright Sierra
"""Full patient record as JSON for task grounding (read-only)."""

from __future__ import annotations

import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class GetPatientDetailsComplete(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], patient_id: str) -> str:
        patients = data.get("patients") or {}
        if patient_id not in patients:
            return json.dumps({"error": f"Patient with ID {patient_id} not found."})
        return json.dumps(patients[patient_id], indent=2, ensure_ascii=False)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_patient_details_complete",
                "description": (
                    "Read-only: return the complete patient object as JSON (demographics, address, insurance, "
                    "medical_history, emergency_contact). Use for grounding task generation."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "patient_id": {
                            "type": "string",
                            "description": "The patient's unique identifier.",
                        },
                    },
                    "required": ["patient_id"],
                },
            },
        }
