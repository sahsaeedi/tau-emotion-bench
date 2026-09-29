# Copyright Sierra

from __future__ import annotations

import json
import random
from typing import Any, Dict, List

from tracer.envs.tool import Tool

_MAX_RECORDS = 5
_call_counter = 0


class ListPatientMedicalRecords(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], patient_id: str) -> str:
        global _call_counter

        records: Dict[str, Dict[str, Any]] = data["medical_records"]
        filtered: List[Dict[str, Any]] = [
            record
            for record in records.values()
            if record.get("patient_id") == patient_id
        ]
        if not filtered:
            return json.dumps({"total_matching": 0, "returned_count": 0, "records": []})

        random.shuffle(filtered)
        total = len(filtered)
        batch_size = min(_MAX_RECORDS, total)
        offset = (_call_counter * batch_size) % total
        _call_counter += 1
        doubled = filtered + filtered
        batch = doubled[offset : offset + batch_size]

        return json.dumps(
            {"total_matching": total, "returned_count": len(batch), "records": batch},
            indent=2,
        )

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "list_patient_medical_records",
                "description": (
                    "List medical record identifiers for a patient. "
                    "The list is randomized; each call returns the next batch "
                    f"(up to {_MAX_RECORDS} records, different from previous calls)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "patient_id": {
                            "type": "string",
                            "description": "ID of the patient",
                        },
                    },
                    "required": ["patient_id"],
                },
            },
        }
