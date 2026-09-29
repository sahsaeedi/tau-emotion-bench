# Copyright Sierra

from __future__ import annotations

import json
import random
from typing import Any, Dict, List, Optional

from tracer.envs.tool import Tool

_MAX_APPOINTMENTS = 5
_call_counter = 0


class ListPatientAppointments(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        patient_id: str,
        status_filter: Optional[str] = None,
    ) -> str:
        global _call_counter

        patients = data["patients"]
        appointments = data["appointments"]

        if patient_id not in patients:
            return json.dumps({"error": f"Patient with ID {patient_id} not found."})

        normalized_filter = status_filter.lower() if status_filter else None

        filtered: List[Dict[str, Any]] = []
        for appointment in appointments.values():
            if appointment.get("patient_id") != patient_id:
                continue
            if (
                normalized_filter
                and appointment.get("status", "").lower() != normalized_filter
            ):
                continue
            filtered.append(appointment)

        if not filtered:
            return json.dumps(
                {"total_matching": 0, "returned_count": 0, "appointments": []}
            )

        random.shuffle(filtered)
        total = len(filtered)
        batch_size = min(_MAX_APPOINTMENTS, total)
        offset = (_call_counter * batch_size) % total
        _call_counter += 1
        doubled = filtered + filtered
        batch = doubled[offset : offset + batch_size]

        return json.dumps(
            {
                "total_matching": total,
                "returned_count": len(batch),
                "appointments": batch,
            },
            indent=2,
        )

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "list_patient_appointments",
                "description": (
                    "List appointments for a patient, optionally filtering by status "
                    "(e.g. scheduled, pending_approval, cancelled). "
                    "The list is randomized; each call returns the next batch "
                    f"(up to {_MAX_APPOINTMENTS} appointments, different from previous calls)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "patient_id": {
                            "type": "string",
                            "description": "The patient's unique identifier.",
                        },
                        "status_filter": {
                            "type": "string",
                            "description": (
                                "Optional appointment status filter (e.g., "
                                "'scheduled', 'pending_approval', 'cancelled')."
                            ),
                        },
                    },
                    "required": ["patient_id"],
                },
            },
        }
