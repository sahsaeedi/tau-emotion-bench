# Copyright Sierra

from __future__ import annotations

import json
import random
from typing import Any, Dict, List, Optional

from tracer.envs.tool import Tool

_MAX_SUPPLIERS = 5
_call_counter = 0


class ListMedicationSuppliers(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        medication: str,
        country_filter: Optional[str] = None,
    ) -> str:
        global _call_counter

        suppliers_map: Dict[str, List[Dict[str, Any]]] = data.get(
            "medication_suppliers", {}
        )

        canonical_map: Dict[str, str] = {
            key.lower(): key for key in suppliers_map.keys()
        }
        medication_key = canonical_map.get(medication.lower())
        suppliers = suppliers_map.get(medication_key) if medication_key else None

        if not suppliers:
            return json.dumps(
                {"error": f"No supplier information found for {medication}."}
            )

        filtered: List[Dict[str, Any]] = list(suppliers)
        if country_filter:
            filtered = [
                item
                for item in filtered
                if item.get("country", "").lower() == country_filter.lower()
            ]
            if not filtered:
                return json.dumps(
                    {"error": f"No suppliers in {country_filter} for {medication}."}
                )

        random.shuffle(filtered)
        total = len(filtered)
        batch_size = min(_MAX_SUPPLIERS, total)
        offset = (_call_counter * batch_size) % total
        _call_counter += 1
        doubled = filtered + filtered
        batch = doubled[offset : offset + batch_size]

        return json.dumps(
            {
                "total_matching": total,
                "returned_count": len(batch),
                "medication": medication,
                "suppliers": batch,
            },
            indent=2,
        )

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "list_medication_suppliers",
                "description": (
                    "List suppliers for a given medication, optionally filtered by country. "
                    "The list is randomized; each call returns the next batch "
                    f"(up to {_MAX_SUPPLIERS} suppliers, different from previous calls)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "medication": {
                            "type": "string",
                            "description": "Medication name to search for",
                        },
                        "country_filter": {
                            "type": "string",
                            "description": "Optional country name to filter suppliers",
                        },
                    },
                    "required": ["medication"],
                },
            },
        }
