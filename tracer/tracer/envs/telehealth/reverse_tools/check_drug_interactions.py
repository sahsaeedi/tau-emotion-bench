# Copyright Sierra

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from tracer.envs.tool import Tool


class CheckDrugInteractions(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        primary_medication: str,
        current_medications: List[str],
    ) -> str:
        interactions: Dict[str, Dict[str, Dict[str, Any]]] = data.get(
            "drug_interactions", {}
        )

        canonical_name: Dict[str, str] = {}
        for outer_key, inner in interactions.items():
            canonical_name.setdefault(outer_key.lower(), outer_key)
            for inner_key in inner.keys():
                canonical_name.setdefault(inner_key.lower(), inner_key)

        def canonical(med: str) -> str:
            return canonical_name.get(med.lower(), med)

        def lookup(med_a: str, med_b: str) -> Optional[Dict[str, Any]]:
            key_a = canonical(med_a)
            key_b = canonical(med_b)
            med_a_data = interactions.get(key_a, {})
            for candidate, details in med_a_data.items():
                if candidate.lower() == key_b.lower():
                    return details
            med_b_data = interactions.get(key_b, {})
            for candidate, details in med_b_data.items():
                if candidate.lower() == key_a.lower():
                    return details
            return None

        found: List[Dict[str, Any]] = []
        skip_set: set = set()
        emergency = False
        max_overlap = 0
        highest_severity = "none"
        severity_ranking = {"low": 1, "moderate": 2, "high": 3}
        severity_pair: Optional[str] = None

        for medication in current_medications:
            details = lookup(primary_medication, medication)
            if not details:
                continue
            severity = details.get("severity", "unknown")
            risk = details.get("risk_score")
            overlap = details.get("time_overlap_hours", 0)
            action = details.get("action", "Monitor.")
            skip_set.update(details.get("skip", []))
            emergency = emergency or details.get("emergency", False)
            max_overlap = max(max_overlap, overlap)
            pair_label = f"{canonical(primary_medication)} + {canonical(medication)}"
            found.append(
                {
                    "pair": pair_label,
                    "severity": severity,
                    "risk_score": risk,
                    "overlap_hours": overlap,
                    "action": action,
                }
            )
            if severity_ranking.get(severity, 0) > severity_ranking.get(
                highest_severity, 0
            ):
                highest_severity = severity
                severity_pair = pair_label

        for idx, med_a in enumerate(current_medications):
            for med_b in current_medications[idx + 1 :]:
                details = lookup(med_a, med_b)
                if not details:
                    continue
                severity = details.get("severity", "unknown")
                risk = details.get("risk_score")
                overlap = details.get("time_overlap_hours", 0)
                action = details.get("action", "Monitor.")
                skip_set.update(details.get("skip", []))
                emergency = emergency or details.get("emergency", False)
                max_overlap = max(max_overlap, overlap)
                pair_label = f"{canonical(med_a)} + {canonical(med_b)}"
                found.append(
                    {
                        "pair": pair_label,
                        "severity": severity,
                        "risk_score": risk,
                        "overlap_hours": overlap,
                        "action": action,
                    }
                )
                if severity_ranking.get(severity, 0) > severity_ranking.get(
                    highest_severity, 0
                ):
                    highest_severity = severity
                    severity_pair = pair_label

        if not found:
            return json.dumps(
                {
                    "interactions_found": 0,
                    "interactions": [],
                    "note": "No documented high-risk interactions found for the supplied medications.",
                }
            )

        payload: Dict[str, Any] = {
            "interactions_found": len(found),
            "interactions": found,
            "medications_to_hold": sorted(skip_set) if skip_set else [],
            "emergency_escalation_required": emergency,
            "peak_overlap_risk_hours": max_overlap,
        }
        if severity_pair:
            payload["highest_severity_interaction"] = {
                "pair": severity_pair,
                "severity": highest_severity,
            }
        return json.dumps(payload, indent=2)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "check_drug_interactions",
                "description": "Evaluate potential interactions between an incident medication and a patient's current regimen.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "primary_medication": {
                            "type": "string",
                            "description": "The medication that was taken accidentally or requires review.",
                        },
                        "current_medications": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of the patient's active medications.",
                        },
                    },
                    "required": ["primary_medication", "current_medications"],
                },
            },
        }
