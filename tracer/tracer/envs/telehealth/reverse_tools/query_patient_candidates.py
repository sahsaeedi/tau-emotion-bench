# Copyright Sierra
"""Tier-2 read-only tool: concise patient roster with optional filters and random pagination."""

from __future__ import annotations

import json
import random
from collections import Counter
from typing import Any, Dict, List, Optional

from tracer.envs.tool import Tool

_MAX_PATIENTS = 5
_call_counter = 0


def _patient_display_name(patient: Dict[str, Any]) -> str:
    name = patient.get("name") or {}
    parts = [name.get("first_name", ""), name.get("last_name", "")]
    return " ".join(p for p in parts if p).strip() or "Unknown"


def _appointment_stats_for_patient(
    patient_id: str, appointments: Dict[str, Any]
) -> tuple[int, Dict[str, int]]:
    by_status: Counter[str] = Counter()
    for appt in appointments.values():
        if appt.get("patient_id") != patient_id:
            continue
        st = str(appt.get("status", "unknown")).lower()
        by_status[st] += 1
    return sum(by_status.values()), dict(by_status)


def _record_count(patient_id: str, medical_records: Dict[str, Any]) -> int:
    return sum(1 for r in medical_records.values() if r.get("patient_id") == patient_id)


def _has_telemetry_assigned(patient_id: str, inventory: List[Dict[str, Any]]) -> bool:
    for item in inventory:
        if item.get("assigned_to") == patient_id:
            return True
    return False


def _medication_names(patient: Dict[str, Any]) -> List[str]:
    meds = (patient.get("medical_history") or {}).get("medications") or []
    out: List[str] = []
    for m in meds:
        n = m.get("name")
        if n:
            out.append(str(n))
    return out


def _matches_medication_filter(patient: Dict[str, Any], needle: str) -> bool:
    needle_l = needle.strip().lower()
    if not needle_l:
        return True
    for name in _medication_names(patient):
        if needle_l in name.lower():
            return True
    return False


class QueryPatientCandidates(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        min_appointments: Optional[int] = None,
        appointment_status: Optional[str] = None,
        has_telemetry_assigned: Optional[bool] = None,
        medication_in_regimen: Optional[str] = None,
        min_medical_records: Optional[int] = None,
        has_regimen_plan: Optional[bool] = None,
    ) -> str:
        global _call_counter

        patients: Dict[str, Any] = data.get("patients") or {}
        appointments: Dict[str, Any] = data.get("appointments") or {}
        medical_records: Dict[str, Any] = data.get("medical_records") or {}
        inventory: List[Dict[str, Any]] = data.get("telemetry_inventory") or []
        regimen_plans: Dict[str, Any] = data.get("regimen_plans") or {}

        candidates: List[Dict[str, Any]] = []

        for patient_id, patient in patients.items():
            appt_total, by_status = _appointment_stats_for_patient(
                patient_id, appointments
            )
            rec_count = _record_count(patient_id, medical_records)
            tel = _has_telemetry_assigned(patient_id, inventory)
            has_regimen = patient_id in regimen_plans and bool(
                regimen_plans.get(patient_id)
            )

            if min_appointments is not None:
                try:
                    if appt_total < int(min_appointments):
                        continue
                except (TypeError, ValueError):
                    pass

            if appointment_status is not None and str(appointment_status).strip():
                key = str(appointment_status).strip().lower()
                if by_status.get(key, 0) < 1:
                    continue

            if has_telemetry_assigned is not None:
                if bool(has_telemetry_assigned) != tel:
                    continue

            if medication_in_regimen is not None and str(medication_in_regimen).strip():
                if not _matches_medication_filter(patient, str(medication_in_regimen)):
                    continue

            if min_medical_records is not None:
                try:
                    if rec_count < int(min_medical_records):
                        continue
                except (TypeError, ValueError):
                    pass

            if has_regimen_plan is not None:
                if bool(has_regimen_plan) != has_regimen:
                    continue

            demo = patient.get("demographics") or {}
            pair: Dict[str, Any] = {}
            want_pair = min_appointments is not None and int(min_appointments) >= 2
            if appt_total >= 2:
                actionable = sorted(
                    (
                        a
                        for a in appointments.values()
                        if a.get("patient_id") == patient_id
                        and a.get("status") in ("scheduled", "pending_approval")
                    ),
                    key=lambda a: a.get("appointment_id", ""),
                )
                if appointment_status in ("scheduled", "pending_approval"):
                    preferred = [
                        a for a in actionable if a.get("status") == appointment_status
                    ]
                    actionable = preferred + [
                        a for a in actionable if a not in preferred
                    ]
                if len(actionable) < 2 and want_pair:
                    continue
                pair = (
                    {}
                    if len(actionable) < 2
                    else {
                        "modify_target": {
                            "appointment_id": actionable[0]["appointment_id"],
                            "status": actionable[0]["status"],
                            "date": actionable[0].get("date"),
                            "time": actionable[0].get("time"),
                            "why": "scheduled/pending_approval -> reschedule_appointment accepts it",
                        },
                        "cancel_target": {
                            "appointment_id": actionable[1]["appointment_id"],
                            "status": actionable[1]["status"],
                            "date": actionable[1].get("date"),
                            "time": actionable[1].get("time"),
                            "why_cancellable": "another scheduled/pending_approval appointment of this patient",
                        },
                    }
                )
            candidates.append(
                {
                    **pair,
                    "patient_id": patient_id,
                    "email": demo.get("email", ""),
                    "name": _patient_display_name(patient),
                    "appointment_total": appt_total,
                    "appointments_by_status": by_status,
                    "medical_record_count": rec_count,
                    "has_telemetry_device_assigned": tel,
                    "has_regimen_plan": has_regimen,
                    "medications_summary": _medication_names(patient),
                }
            )

        random.shuffle(candidates)
        total = len(candidates)
        if not candidates:
            return json.dumps(
                {"total_matching": 0, "returned_count": 0, "patients": []}, indent=2
            )

        offset = (_call_counter * _MAX_PATIENTS) % total
        _call_counter += 1
        doubled = candidates + candidates
        batch = doubled[offset : offset + _MAX_PATIENTS]

        payload = {
            "total_matching": total,
            "returned_count": len(batch),
            "patients": batch,
        }
        return json.dumps(payload, indent=2)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "query_patient_candidates",
                "description": (
                    "Read-only roster of patients with concise per-patient stats (appointment counts by status, "
                    "record counts, telemetry assignment, regimen plan flag, medication names). "
                    "All filter parameters are optional; when omitted, no filter is applied for that field. "
                    "Combine filters as needed. The list is randomized; each call returns the next batch "
                    f"(up to {_MAX_PATIENTS} patients, different from previous calls). "
                    "Use Tier-1 tools (e.g. get_patient_details_complete, list_patient_appointments) for full details."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "min_appointments": {
                            "type": "integer",
                            "description": "If set, only patients with at least this many appointments (any status).",
                        },
                        "appointment_status": {
                            "type": "string",
                            "description": (
                                "If set, only patients with at least one appointment in this status "
                                "(e.g. scheduled, pending_approval, cancelled, completed)."
                            ),
                        },
                        "has_telemetry_assigned": {
                            "type": "boolean",
                            "description": "If set, only patients where True/False matches telemetry device assigned_to this patient.",
                        },
                        "medication_in_regimen": {
                            "type": "string",
                            "description": "If set, only patients whose current medications include this substring (case-insensitive).",
                        },
                        "min_medical_records": {
                            "type": "integer",
                            "description": "If set, only patients with at least this many medical records.",
                        },
                        "has_regimen_plan": {
                            "type": "boolean",
                            "description": "If set, only patients where a regimen plan exists (or not) for this patient_id.",
                        },
                    },
                    "required": [],
                },
            },
        }
