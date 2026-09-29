# Copyright Sierra

from __future__ import annotations

import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class GetAppointmentDetails(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], appointment_id: str) -> str:
        appointments = data["appointments"]

        if appointment_id not in appointments:
            return json.dumps(
                {"error": f"Appointment with ID {appointment_id} not found."}
            )

        return json.dumps(appointments[appointment_id], indent=2)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_appointment_details",
                "description": "Get detailed information about a scheduled appointment including patient, provider, date, time, and clinical details.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "appointment_id": {
                            "type": "string",
                            "description": "The appointment's unique identifier",
                        },
                    },
                    "required": ["appointment_id"],
                },
            },
        }
