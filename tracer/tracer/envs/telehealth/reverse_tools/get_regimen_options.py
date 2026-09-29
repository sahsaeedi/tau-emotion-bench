# Copyright Sierra

from __future__ import annotations

import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class GetRegimenOptions(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], patient_id: str) -> str:
        plans: Dict[str, Any] = data.get("regimen_plans", {})
        patient_plan = plans.get(patient_id)
        if not patient_plan:
            return json.dumps(
                {
                    "error": f"No regimen optimization data available for patient {patient_id}."
                }
            )

        return json.dumps(patient_plan, indent=2)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_regimen_options",
                "description": "Retrieve current regimen components and optimized alternative combinations for a patient, including costs and pill burden details.",
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
