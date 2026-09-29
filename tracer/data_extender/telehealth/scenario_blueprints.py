from __future__ import annotations

import argparse
import copy
import math
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Collection, Dict, List, Mapping, Optional, Sequence, Tuple

if __package__ in {None, ""}:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from data_extender.telehealth.common import (
    INDEX_TO_WEEKDAY,
    TelehealthSeedPacker,
    load_base_telehealth_data,
    parse_date,
    repo_root,
    write_json,
)

DEFAULT_SCENARIO_MIX = {
    "scheduling_provider": 0.18,
    "supplier_update": 0.16,
    "drug_interaction": 0.16,
    "telemetry_compliance": 0.2,
    "regimen_optimization": 0.15,
    "family_coordination": 0.15,
}


def _empty_case(blueprint_id: str, category: str, summary: str) -> Dict[str, Any]:
    return {
        "metadata": {
            "blueprint_id": blueprint_id,
            "category": category,
            "summary": summary,
        },
        "patients": [],
        "providers": [],
        "appointments": [],
        "medical_records": [],
        "telemetry_inventory": [],
        "telemetry_uploads": [],
        "regimen_plans": [],
        "medication_suppliers": {},
        "drug_interactions": {},
        "fill_request": {
            "summary": summary,
            "appointments": [],
            "medical_records": [],
            "regimen_plans": [],
        },
    }


class _NoCandidate(Exception):
    """No newly generated record fits a scenario category."""


def _normalize_mix(mix: Optional[Mapping[str, float]]) -> Dict[str, float]:
    """Category weights summing to 1; a weight of 0 disables a category."""
    source = dict(DEFAULT_SCENARIO_MIX)
    if mix:
        for key, value in mix.items():
            if key in source:
                if value < 0:
                    raise ValueError(f"scenario_mix weight for {key} is negative.")
                source[key] = float(value)
    total = sum(source.values())
    if total <= 0:
        raise ValueError("scenario_mix disables every scenario category.")
    return {key: value / total for key, value in source.items()}


def _daily_dose(frequency: str) -> int:
    lowered = frequency.lower()
    if "twice" in lowered:
        return 2
    if "three" in lowered:
        return 3
    if "with meals" in lowered:
        return 3
    return 1


def _sort_key(item: Tuple[str, Any]) -> str:
    return item[0]


class DeterministicScenarioBlueprintGenerator:
    def __init__(
        self, master_data: Mapping[str, Any], master_metadata: Mapping[str, Any]
    ):
        self.master_data = copy.deepcopy(dict(master_data))
        self.master_metadata = copy.deepcopy(dict(master_metadata))
        self.id_factory = TelehealthSeedPacker(self.master_data)
        self.case_index = 0
        self.busy_slots = self._collect_busy_slots(self.master_data["appointments"])
        self.anchor_date = self._latest_appointment_date() + timedelta(days=14)
        self.patient_profiles: Dict[str, Dict[str, Any]] = {
            key: dict(value)
            for key, value in self.master_metadata.get("patient_profiles", {}).items()
        }
        self.family_groups = list(self.master_metadata.get("family_groups", []))
        self.telemetry_assignments = list(
            self.master_metadata.get("telemetry_assignments", [])
        )
        self.assigned_telemetry_assignments = [
            row for row in self.telemetry_assignments if row.get("assigned_to")
        ]
        self.provider_ids_by_specialty: Dict[str, List[str]] = defaultdict(list)
        for provider_id, provider in sorted(
            self.master_data["providers"].items(), key=_sort_key
        ):
            self.provider_ids_by_specialty[provider["specialty"]].append(provider_id)
        self.profile_cursors: Dict[str, int] = defaultdict(int)
        self.specialty_cursors: Dict[str, int] = defaultdict(int)
        self.telemetry_cursor = 0
        self.family_cursor = 0
        self.regimen_patient_ids = set(self.master_data["regimen_plans"])

    def _latest_appointment_date(self) -> date:
        values = [
            parse_date(row["date"]) for row in self.master_data["appointments"].values()
        ]
        return max(values) if values else date(2026, 1, 5)

    @staticmethod
    def _collect_busy_slots(
        appointments: Mapping[str, Any],
    ) -> set[Tuple[str, str, str]]:
        busy: set[Tuple[str, str, str]] = set()
        for appointment in appointments.values():
            if appointment.get("status") not in {"scheduled", "pending_approval"}:
                continue
            busy.add(
                (appointment["provider_id"], appointment["date"], appointment["time"])
            )
        return busy

    def _providers_for_specialty(self, specialty: str) -> List[str]:
        providers = self.provider_ids_by_specialty.get(specialty, [])
        if not providers:
            raise ValueError(f"No providers available for specialty: {specialty}")
        return providers

    def _next_provider(self, specialty: str) -> str:
        providers = self._providers_for_specialty(specialty)
        idx = self.specialty_cursors[specialty] % len(providers)
        self.specialty_cursors[specialty] += 1
        return providers[idx]

    def _next_patient(
        self, profile_ids: Sequence[str], exclude: Collection[str] = ()
    ) -> str:
        # Only newly generated patients: scenarios never touch existing ones.
        key = "|".join(sorted(profile_ids))
        profiles = ", ".join(sorted(profile_ids))
        matches = sorted(
            patient_id
            for patient_id, meta in self.patient_profiles.items()
            if meta.get("profile_id") in profile_ids
        )
        if not matches:
            raise _NoCandidate(f"no new patient with profile {profiles}")
        matches = [patient_id for patient_id in matches if patient_id not in exclude]
        if not matches:
            raise _NoCandidate(f"every new patient with profile {profiles} is used")
        idx = self.profile_cursors[key] % len(matches)
        self.profile_cursors[key] += 1
        return matches[idx]

    def _next_telemetry_assignment(self) -> Mapping[str, Any]:
        if not self.assigned_telemetry_assignments:
            raise _NoCandidate("no new telemetry device is assigned to a patient")
        assignment = self.assigned_telemetry_assignments[
            self.telemetry_cursor % len(self.assigned_telemetry_assignments)
        ]
        self.telemetry_cursor += 1
        return assignment

    def _next_family_group(self) -> Mapping[str, Any]:
        if not self.family_groups:
            raise _NoCandidate("no new family groups")
        group = self.family_groups[self.family_cursor % len(self.family_groups)]
        self.family_cursor += 1
        return group

    def _allocate_blueprint_id(self, category: str) -> str:
        self.case_index += 1
        return f"{category}_tracer_{self.case_index:03d}"

    def _book_slot(
        self,
        provider_id: str,
        preferred_times: Optional[Sequence[str]] = None,
        earliest_date: Optional[date] = None,
    ) -> Tuple[str, str]:
        provider = self.master_data["providers"][provider_id]
        start = earliest_date or self.anchor_date
        preferred = list(preferred_times or [])
        for day_offset in range(0, 210):
            current = start + timedelta(days=day_offset)
            weekday = INDEX_TO_WEEKDAY[current.weekday()]
            slots = list(provider.get("schedule", {}).get(weekday, []))
            if preferred:
                slots = [slot for slot in preferred if slot in slots] + [
                    slot for slot in slots if slot not in preferred
                ]
            for time_value in slots:
                key = (provider_id, current.isoformat(), time_value)
                if key in self.busy_slots:
                    continue
                self.busy_slots.add(key)
                return current.isoformat(), time_value
        raise ValueError(f"No open slot found for provider {provider_id}")

    def _copay_amount(self, patient_id: str, provider_id: str) -> float:
        patient = self.master_data["patients"][patient_id]
        provider = self.master_data["providers"][provider_id]
        primary = patient.get("insurance", {}).get("primary", {})
        if provider["specialty"] in {
            "Primary Care",
            "Care Coordination",
            "Device Coaching",
        }:
            return float(primary.get("copay_primary", 25.0))
        return float(
            primary.get("copay_specialist", primary.get("copay_primary", 40.0))
        )

    def _appointment_base(
        self,
        patient_id: str,
        provider_id: str,
        appointment_type: str,
        status: str,
        duration_minutes: int,
        preferred_times: Optional[Sequence[str]] = None,
        earliest_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        appointment_id = self.id_factory.allocate_appointment_id(None)
        date_value, time_value = self._book_slot(
            provider_id, preferred_times=preferred_times, earliest_date=earliest_date
        )
        return {
            "appointment_id": appointment_id,
            "patient_id": patient_id,
            "provider_id": provider_id,
            "date": date_value,
            "time": time_value,
            "duration_minutes": duration_minutes,
            "type": appointment_type,
            "status": status,
            "chief_complaint": "",
            "notes": "",
            "insurance_authorization": f"AUTH_TRACER_{appointment_id[-3:]}",
            "copay_amount": self._copay_amount(patient_id, provider_id),
            "meeting_link": f"https://telehealth.healthcenter.com/room/{appointment_id}",
        }

    def _record_base(
        self,
        patient_id: str,
        provider_id: str,
        appointment_id: Optional[str],
        date_value: str,
        record_type: str,
        objective: str,
        prescriptions: Sequence[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        record_id = self.id_factory.allocate_record_id(None)
        return {
            "record_id": record_id,
            "appointment_id": appointment_id,
            "patient_id": patient_id,
            "provider_id": provider_id,
            "date": date_value,
            "type": record_type,
            "subjective": "",
            "objective": objective,
            "assessment": "",
            "plan": "",
            "prescriptions": [dict(row) for row in prescriptions],
            "notes": [],
        }

    def _medication_supplier(self, medication: str) -> Optional[Dict[str, Any]]:
        rows = list(self.master_data["medication_suppliers"].get(medication, []))
        if not rows:
            return None
        ranked = sorted(rows, key=lambda row: (float(row["price_usd"]), row["company"]))
        return dict(ranked[0])

    def _interaction_pair(self) -> Tuple[str, str, Mapping[str, Any]]:
        interactions = self.master_data["drug_interactions"]
        for primary, mapping in sorted(interactions.items()):
            if not isinstance(mapping, Mapping):
                continue
            for secondary, details in sorted(mapping.items()):
                return primary, secondary, details
        raise ValueError("Drug interaction catalog is empty.")

    def _current_regimen_components(self, patient_id: str) -> List[Dict[str, Any]]:
        components: List[Dict[str, Any]] = []
        for medication in self.master_data["patients"][patient_id]["medical_history"][
            "medications"
        ]:
            supplier = self._medication_supplier(medication["name"])
            components.append(
                {
                    "medication": medication["name"],
                    "dosage": medication["dosage"],
                    "daily_dose": _daily_dose(medication["frequency"]),
                    "monthly_units": _daily_dose(medication["frequency"]) * 30,
                    "unit_type": "tablet"
                    if "inhaler" not in medication["name"].lower()
                    else "inhaler",
                    "preferred_brand": supplier["brand_name"]
                    if supplier
                    else "Generic",
                    "supplier": supplier["company"]
                    if supplier
                    else "Clinical sourcing pending",
                    "unit_cost_usd": float(supplier["price_usd"]) if supplier else 8.5,
                }
            )
        return components

    def _optimized_regimen_options(
        self, components: Sequence[Mapping[str, Any]]
    ) -> List[Dict[str, Any]]:
        baseline_tablets = sum(int(row["daily_dose"]) for row in components)
        return [
            {
                "name": "Cost-Synchronized Generic Fill",
                "focus": "",
                "components": [dict(row) for row in components],
                "pill_burden": {
                    "tablets_per_day": baseline_tablets,
                    "devices_per_month": 0,
                },
                "synergy_notes": [],
            },
            {
                "name": "Adherence Packaging Option",
                "focus": "",
                "components": [dict(row) for row in components],
                "pill_burden": {
                    "tablets_per_day": baseline_tablets,
                    "devices_per_month": 0,
                },
                "synergy_notes": [],
            },
        ]

    def _fill_entry_for_appointment(
        self, appointment: Mapping[str, Any], patient_id: str
    ) -> Dict[str, Any]:
        patient = self.master_data["patients"][patient_id]
        provider = self.master_data["providers"][appointment["provider_id"]]
        return {
            "appointment_id": appointment["appointment_id"],
            "patient_context": {
                "patient_id": patient_id,
                "name": patient["name"],
                "conditions": patient["medical_history"]["conditions"],
                "medications": patient["medical_history"]["medications"],
            },
            "provider_context": {
                "provider_id": provider["provider_id"],
                "specialty": provider["specialty"],
                "languages": provider.get("languages", []),
            },
            "appointment_context": {
                "type": appointment["type"],
                "status": appointment["status"],
                "date": appointment["date"],
                "time": appointment["time"],
            },
        }

    def _fill_entry_for_record(
        self, record: Mapping[str, Any], extra_context: Mapping[str, Any]
    ) -> Dict[str, Any]:
        return {
            "record_id": record["record_id"],
            "record_type": record["type"],
            "objective": record["objective"],
            "prescriptions": record.get("prescriptions", []),
            "context": dict(extra_context),
        }

    def _build_scheduling_provider_case(self) -> Dict[str, Any]:
        patient_id = self._next_patient(
            ["cardiometabolic", "atrial_fibrillation", "endocrine_review"]
        )
        preferred_specialty = self.patient_profiles.get(patient_id, {}).get(
            "preferred_specialty", "Primary Care"
        )
        provider_id = self._next_provider(preferred_specialty)
        blueprint_id = self._allocate_blueprint_id("scheduling_provider")
        case = _empty_case(
            blueprint_id,
            "scheduling_provider",
            "Deterministic provider-matching follow-up booking.",
        )
        appointment = self._appointment_base(
            patient_id,
            provider_id,
            "follow_up",
            "scheduled",
            30,
            preferred_times=["09:00", "10:00"],
        )
        record = self._record_base(
            patient_id=patient_id,
            provider_id=provider_id,
            appointment_id=appointment["appointment_id"],
            date_value=appointment["date"],
            record_type="follow_up_note",
            objective=f"Patient profile includes {', '.join(self.master_data['patients'][patient_id]['medical_history']['conditions'])}.",
            prescriptions=[],
        )
        case["appointments"].append(appointment)
        case["medical_records"].append(record)
        case["fill_request"]["appointments"].append(
            self._fill_entry_for_appointment(appointment, patient_id)
        )
        case["fill_request"]["medical_records"].append(
            self._fill_entry_for_record(
                record, {"scenario": "provider_matching", "patient_id": patient_id}
            )
        )
        return case

    def _build_supplier_update_case(self) -> Dict[str, Any]:
        patient_id = self._next_patient(
            ["cardiometabolic", "endocrine_review", "sleep_compliance"]
        )
        provider_id = self._next_provider("Primary Care")
        blueprint_id = self._allocate_blueprint_id("supplier_update")
        case = _empty_case(
            blueprint_id,
            "supplier_update",
            "Supplier update case with deterministic cheapest-supplier picks.",
        )
        appointment = self._appointment_base(
            patient_id,
            provider_id,
            "medication_review",
            "scheduled",
            30,
            preferred_times=["11:00", "14:00"],
        )
        prescriptions: List[Dict[str, Any]] = []
        for medication in self.master_data["patients"][patient_id]["medical_history"][
            "medications"
        ][:2]:
            supplier = self._medication_supplier(medication["name"])
            row = {
                "medication": medication["name"],
                "dosage": medication["dosage"],
                "frequency": medication["frequency"],
            }
            if supplier:
                row["supplier"] = {
                    "company": supplier["company"],
                    "brand_name": supplier["brand_name"],
                    "price_usd": float(supplier["price_usd"]),
                    "country": supplier["country"],
                }
            prescriptions.append(row)
        record = self._record_base(
            patient_id=patient_id,
            provider_id=provider_id,
            appointment_id=appointment["appointment_id"],
            date_value=appointment["date"],
            record_type="medication_supply_note",
            objective="Compared existing medications against the supplier catalog and selected the lowest-cost safe options.",
            prescriptions=prescriptions,
        )
        case["appointments"].append(appointment)
        case["medical_records"].append(record)
        case["fill_request"]["appointments"].append(
            self._fill_entry_for_appointment(appointment, patient_id)
        )
        case["fill_request"]["medical_records"].append(
            self._fill_entry_for_record(
                record, {"scenario": "supplier_update", "patient_id": patient_id}
            )
        )
        return case

    def _build_drug_interaction_case(self) -> Dict[str, Any]:
        patient_id = self._next_patient(["behavioral_health", "atrial_fibrillation"])
        provider_id = self._next_provider("Cardiology")
        primary, secondary, details = self._interaction_pair()
        blueprint_id = self._allocate_blueprint_id("drug_interaction")
        case = _empty_case(
            blueprint_id,
            "drug_interaction",
            "Drug interaction review with deterministic risk facts.",
        )
        appointment = self._appointment_base(
            patient_id,
            provider_id,
            "specialist_consultation",
            "scheduled",
            45,
            preferred_times=["10:00", "14:00"],
        )
        record = self._record_base(
            patient_id=patient_id,
            provider_id=provider_id,
            appointment_id=appointment["appointment_id"],
            date_value=appointment["date"],
            record_type="interaction_review_note",
            objective=(
                f"Interaction review for {primary} + {secondary}: severity={details['severity']}, "
                f"risk_score={details['risk_score']}, action={details['action']}"
            ),
            prescriptions=[
                {
                    "medication": primary,
                    "dosage": "per current regimen",
                    "frequency": "as prescribed",
                },
                {
                    "medication": secondary,
                    "dosage": "proposed addition",
                    "frequency": "as prescribed",
                },
            ],
        )
        case["appointments"].append(appointment)
        case["medical_records"].append(record)
        case["fill_request"]["appointments"].append(
            self._fill_entry_for_appointment(appointment, patient_id)
        )
        case["fill_request"]["medical_records"].append(
            self._fill_entry_for_record(
                record,
                {
                    "scenario": "drug_interaction",
                    "patient_id": patient_id,
                    "interaction": {
                        "primary": primary,
                        "secondary": secondary,
                        "details": dict(details),
                    },
                },
            )
        )
        return case

    def _build_telemetry_case(self) -> Dict[str, Any]:
        assignment = self._next_telemetry_assignment()
        patient_id = str(assignment["assigned_to"])
        coaching_provider = self._next_provider("Device Coaching")
        specialty = self.patient_profiles.get(patient_id, {}).get(
            "preferred_specialty", "Pulmonology"
        )
        specialist_provider = self._next_provider(specialty)
        blueprint_id = self._allocate_blueprint_id("telemetry_compliance")
        case = _empty_case(
            blueprint_id,
            "telemetry_compliance",
            "Telemetry compliance episode with deterministic uploads and audit facts.",
        )
        coaching_appointment = self._appointment_base(
            patient_id,
            coaching_provider,
            "device_coaching",
            "scheduled",
            40,
            preferred_times=["08:00", "09:00"],
        )
        specialist_appointment = self._appointment_base(
            patient_id,
            specialist_provider,
            "follow_up",
            "scheduled",
            45,
            preferred_times=["10:00", "14:00"],
            earliest_date=parse_date(coaching_appointment["date"]) + timedelta(days=2),
        )
        uploads: List[Dict[str, Any]] = []
        base_day = parse_date(coaching_appointment["date"]) - timedelta(days=6)
        usage_values = [6.8, 6.4, 5.9, 0.0, 6.2, 6.7, 7.0]
        for offset, usage in enumerate(usage_values):
            upload_date = base_day + timedelta(days=offset)
            uploads.append(
                {
                    "device_id": assignment["device_id"],
                    "date": upload_date.isoformat(),
                    "usage_hours": usage,
                    "synced_at": None
                    if usage == 0.0
                    else f"{upload_date.isoformat()}T06:15:00Z",
                    "event": "upload_missing" if usage == 0.0 else "normal",
                    "alerts": ["No data received", "Usage below compliance threshold"]
                    if usage == 0.0
                    else [],
                }
            )
        record = self._record_base(
            patient_id=patient_id,
            provider_id=coaching_provider,
            appointment_id=coaching_appointment["appointment_id"],
            date_value=coaching_appointment["date"],
            record_type="telemetry_compliance_note",
            objective=(
                f"Telemetry review for device {assignment['device_id']} ({assignment['device_type']}); "
                "7-day window includes one missing upload and one below-threshold night."
            ),
            prescriptions=[],
        )
        case["appointments"].extend([coaching_appointment, specialist_appointment])
        case["medical_records"].append(record)
        case["telemetry_uploads"].extend(uploads)
        case["fill_request"]["appointments"].append(
            self._fill_entry_for_appointment(coaching_appointment, patient_id)
        )
        case["fill_request"]["appointments"].append(
            self._fill_entry_for_appointment(specialist_appointment, patient_id)
        )
        case["fill_request"]["medical_records"].append(
            self._fill_entry_for_record(
                record,
                {
                    "scenario": "telemetry_compliance",
                    "patient_id": patient_id,
                    "device_assignment": dict(assignment),
                    "upload_window": uploads,
                },
            )
        )
        return case

    def _build_regimen_case(self) -> Dict[str, Any]:
        # One regimen plan per patient.
        patient_id = self._next_patient(
            ["cardiometabolic", "endocrine_review", "atrial_fibrillation"],
            exclude=self.regimen_patient_ids,
        )
        self.regimen_patient_ids.add(patient_id)
        provider_id = self._next_provider(
            self.patient_profiles.get(patient_id, {}).get(
                "preferred_specialty", "Primary Care"
            )
        )
        blueprint_id = self._allocate_blueprint_id("regimen_optimization")
        case = _empty_case(
            blueprint_id,
            "regimen_optimization",
            "Regimen optimization case with deterministic costed medication components.",
        )
        appointment = self._appointment_base(
            patient_id,
            provider_id,
            "medication_review",
            "scheduled",
            35,
            preferred_times=["09:00", "13:00"],
        )
        components = self._current_regimen_components(patient_id)
        regimen_plan = {
            "patient_id": patient_id,
            "current_regimen": {
                "components": components,
                "pill_burden": {
                    "tablets_per_day": sum(
                        int(row["daily_dose"]) for row in components
                    ),
                    "devices_per_month": 0,
                },
                "notes": [],
            },
            "optimized_regimens": self._optimized_regimen_options(components),
        }
        record = self._record_base(
            patient_id=patient_id,
            provider_id=provider_id,
            appointment_id=appointment["appointment_id"],
            date_value=appointment["date"],
            record_type="regimen_review_note",
            objective="Compiled current regimen costs, pill burden, and two deterministic optimization options for comparison.",
            prescriptions=[
                {
                    "medication": row["medication"],
                    "dosage": row["dosage"],
                    "frequency": f"{row['daily_dose']}x daily",
                }
                for row in components
            ],
        )
        case["appointments"].append(appointment)
        case["medical_records"].append(record)
        case["regimen_plans"].append(regimen_plan)
        case["fill_request"]["appointments"].append(
            self._fill_entry_for_appointment(appointment, patient_id)
        )
        case["fill_request"]["medical_records"].append(
            self._fill_entry_for_record(
                record, {"scenario": "regimen_optimization", "patient_id": patient_id}
            )
        )
        case["fill_request"]["regimen_plans"].append(
            {
                "patient_id": patient_id,
                "current_components": components,
                "optimized_regimen_names": [
                    row["name"] for row in regimen_plan["optimized_regimens"]
                ],
            }
        )
        return case

    def _build_family_case(self) -> Dict[str, Any]:
        family = self._next_family_group()
        guardian_id = family["guardian_patient_id"]
        pediatric_provider = self._next_provider("Pediatrics")
        coordination_provider = self._next_provider("Care Coordination")
        blueprint_id = self._allocate_blueprint_id("family_coordination")
        case = _empty_case(
            blueprint_id,
            "family_coordination",
            "Family coordination case grounded in deterministic household records.",
        )
        family_appointment = self._appointment_base(
            guardian_id,
            pediatric_provider,
            "family_consultation",
            "scheduled",
            50,
            preferred_times=["08:30", "09:30"],
        )
        coordinator_appointment = self._appointment_base(
            guardian_id,
            coordination_provider,
            "care_coordination",
            "scheduled",
            30,
            preferred_times=["10:00", "11:00"],
            earliest_date=parse_date(family_appointment["date"]) + timedelta(days=1),
        )
        member_summary = ", ".join(family["member_patient_ids"])
        record = self._record_base(
            patient_id=guardian_id,
            provider_id=coordination_provider,
            appointment_id=coordinator_appointment["appointment_id"],
            date_value=coordinator_appointment["date"],
            record_type="family_coordination_note",
            objective=f"Household coordination review for family members: {member_summary}. Shared concerns triaged into one pediatric visit and one coordination follow-up.",
            prescriptions=[],
        )
        case["appointments"].extend([family_appointment, coordinator_appointment])
        case["medical_records"].append(record)
        case["fill_request"]["appointments"].append(
            self._fill_entry_for_appointment(family_appointment, guardian_id)
        )
        case["fill_request"]["appointments"].append(
            self._fill_entry_for_appointment(coordinator_appointment, guardian_id)
        )
        case["fill_request"]["medical_records"].append(
            self._fill_entry_for_record(
                record,
                {
                    "scenario": "family_coordination",
                    "guardian_patient_id": guardian_id,
                    "family_member_ids": list(family["member_patient_ids"]),
                    "theme": family["theme"],
                },
            )
        )
        return case

    def _scenario_counts(
        self, target_scenarios: int, scenario_mix: Optional[Mapping[str, float]]
    ) -> Dict[str, int]:
        mix = _normalize_mix(scenario_mix)
        counts = {
            key: int(math.floor(target_scenarios * weight))
            for key, weight in mix.items()
        }
        assigned = sum(counts.values())
        remainder = target_scenarios - assigned
        ranked = sorted(
            [item for item in mix.items() if item[1] > 0],
            key=lambda item: item[1],
            reverse=True,
        )
        for idx in range(remainder):
            counts[ranked[idx % len(ranked)][0]] += 1
        return counts

    def build(
        self, target_scenarios: int, scenario_mix: Optional[Mapping[str, float]] = None
    ) -> List[Dict[str, Any]]:
        counts = self._scenario_counts(target_scenarios, scenario_mix)
        builders = {
            "scheduling_provider": self._build_scheduling_provider_case,
            "supplier_update": self._build_supplier_update_case,
            "drug_interaction": self._build_drug_interaction_case,
            "telemetry_compliance": self._build_telemetry_case,
            "regimen_optimization": self._build_regimen_case,
            "family_coordination": self._build_family_case,
        }
        cases: List[Dict[str, Any]] = []
        for category, count in counts.items():
            for built in range(count):
                try:
                    cases.append(builders[category]())
                except _NoCandidate as exc:
                    print(
                        f"[telehealth] Skipping {count - built} {category} "
                        f"scenario(s): {exc}.",
                        flush=True,
                    )
                    break
        return cases


def generate_scenario_blueprints(
    input_data_dir: Path,
    master_metadata: Mapping[str, Any],
    target_scenarios: int,
    scenario_mix: Optional[Mapping[str, float]],
    output_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    master_data = load_base_telehealth_data(input_data_dir)
    generator = DeterministicScenarioBlueprintGenerator(master_data, master_metadata)
    cases = generator.build(
        target_scenarios=target_scenarios, scenario_mix=scenario_mix
    )
    if target_scenarios > 0 and not cases:
        raise ValueError(
            "No scenario blueprints could be built for the new records; "
            "add more patients, family groups or devices."
        )
    if output_path is not None:
        write_json(output_path, {"cases": cases})
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="scenario_blueprints",
        description="Build deterministic telehealth scenario blueprints against an already-extended master dataset.",
    )
    parser.add_argument("input_data_dir", type=str)
    parser.add_argument("master_metadata_path", type=str)
    parser.add_argument("--target-scenarios", type=int, default=12)
    parser.add_argument(
        "--out",
        type=str,
        default=str(Path("data_extender") / "generated_telehealth_blueprints.json"),
    )
    args = parser.parse_args()

    root = repo_root(Path.cwd())
    input_dir = Path(args.input_data_dir)
    resolved_input = input_dir if input_dir.is_absolute() else (root / input_dir)
    metadata_path = Path(args.master_metadata_path)
    resolved_metadata = (
        metadata_path if metadata_path.is_absolute() else (root / metadata_path)
    )
    output_path = Path(args.out)
    resolved_output = output_path if output_path.is_absolute() else (root / output_path)

    import json

    with resolved_metadata.open("r", encoding="utf-8") as f:
        master_metadata = json.load(f)
    generate_scenario_blueprints(
        input_data_dir=resolved_input,
        master_metadata=master_metadata,
        target_scenarios=max(0, args.target_scenarios),
        scenario_mix=None,
        output_path=resolved_output,
    )
    print(f"Wrote deterministic scenario blueprints to: {resolved_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
