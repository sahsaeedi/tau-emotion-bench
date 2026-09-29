# Copyright Sierra

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from tracer.envs.tool import Tool


class GetMedicalRecord(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        record_id: Optional[str] = None,
        appointment_id: Optional[str] = None,
    ) -> str:
        medical_records = data.get("medical_records", {})

        if not record_id and not appointment_id:
            return json.dumps(
                {
                    "error": "Please provide a record_id or appointment_id to look up the medical record."
                }
            )

        record: Optional[Dict[str, Any]] = None
        if record_id:
            record = medical_records.get(record_id)
            if record is None:
                return json.dumps(
                    {"error": f"Medical record with ID {record_id} not found."}
                )
        else:
            for candidate in medical_records.values():
                if candidate.get("appointment_id") == appointment_id:
                    record = candidate
                    break
            if record is None:
                return json.dumps(
                    {
                        "error": f"No medical record found for appointment ID {appointment_id}."
                    }
                )

        return json.dumps(record, indent=2)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_medical_record",
                "description": "Retrieve a patient's medical record by record ID or related appointment ID.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "record_id": {
                            "type": "string",
                            "description": "The unique medical record identifier.",
                        },
                        "appointment_id": {
                            "type": "string",
                            "description": "The appointment ID associated with the medical record.",
                        },
                    },
                    "required": [],
                },
            },
        }
