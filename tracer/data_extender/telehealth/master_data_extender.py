from __future__ import annotations

import argparse
import copy
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

if __package__ in {None, ""}:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from faker import Faker

from data_extender.telehealth.common import (
    TelehealthSeedPacker,
    load_base_telehealth_data,
    repo_root,
    write_json,
)


def _us_address_dict(fake: Faker) -> Dict[str, Any]:
    secondary = fake.secondary_address() if fake.random.random() < 0.25 else ""
    return {
        "address1": fake.street_address(),
        "address2": secondary,
        "city": fake.city(),
        "state": fake.state_abbr(),
        "zip": fake.zipcode(),
        "country": "USA",
    }


def _first_name_for_gender(fake: Faker, gender: str) -> str:
    g = gender.strip().lower()
    if g == "male":
        return fake.first_name_male()
    if g == "female":
        return fake.first_name_female()
    return fake.first_name()


INSURANCE_POOL = [
    {
        "provider": "Blue Cross Blue Shield",
        "policy_prefix": "BCBS",
        "group_prefix": "BCG",
    },
    {"provider": "Aetna", "policy_prefix": "AET", "group_prefix": "AEG"},
    {"provider": "Cigna", "policy_prefix": "CIG", "group_prefix": "CIGG"},
    {"provider": "UnitedHealthcare", "policy_prefix": "UHC", "group_prefix": "UHG"},
]

ADULT_PATIENT_PROFILES = [
    {
        "profile_id": "cardiometabolic",
        "gender": "Female",
        "conditions": ["Hypertension", "Type 2 Diabetes"],
        "allergies": ["Penicillin"],
        "medications": [
            {"name": "Metformin", "dosage": "500mg", "frequency": "twice daily"},
            {"name": "Lisinopril", "dosage": "10mg", "frequency": "once daily"},
        ],
        "telemetry_program": None,
        "preferred_specialty": "Primary Care",
    },
    {
        "profile_id": "atrial_fibrillation",
        "gender": "Male",
        "conditions": ["Atrial Fibrillation", "Hyperlipidemia"],
        "allergies": ["Latex"],
        "medications": [
            {"name": "Warfarin", "dosage": "5mg", "frequency": "once daily"},
            {"name": "Atorvastatin", "dosage": "20mg", "frequency": "once daily"},
        ],
        "telemetry_program": {
            "device_type": "Cardiac Event Monitor",
            "program": "rhythm_surveillance",
        },
        "preferred_specialty": "Cardiology",
    },
    {
        "profile_id": "sleep_compliance",
        "gender": "Male",
        "conditions": ["Obstructive Sleep Apnea", "COPD"],
        "allergies": ["Sulfa drugs"],
        "medications": [
            {
                "name": "Fluticasone Inhaler",
                "dosage": "110mcg",
                "frequency": "twice daily",
            },
            {"name": "Montelukast", "dosage": "10mg", "frequency": "once daily"},
        ],
        "telemetry_program": {
            "device_type": "Philips Trilogy Ventilator",
            "program": "sleep_compliance",
        },
        "preferred_specialty": "Pulmonology",
    },
    {
        "profile_id": "seizure_monitoring",
        "gender": "Female",
        "conditions": ["Focal Epilepsy", "Generalized Anxiety Disorder"],
        "allergies": ["Shellfish"],
        "medications": [
            {"name": "Levetiracetam", "dosage": "750mg", "frequency": "twice daily"},
            {"name": "Sertraline", "dosage": "50mg", "frequency": "once daily"},
        ],
        "telemetry_program": {
            "device_type": "Wearable EEG",
            "program": "neurology_telemetry",
        },
        "preferred_specialty": "Neurology",
    },
    {
        "profile_id": "endocrine_review",
        "gender": "Female",
        "conditions": ["Type 1 Diabetes", "Hypothyroidism"],
        "allergies": ["Adhesive tape"],
        "medications": [
            {
                "name": "Insulin Lispro",
                "dosage": "sliding scale",
                "frequency": "with meals",
            },
            {"name": "Levothyroxine", "dosage": "75mcg", "frequency": "once daily"},
        ],
        "telemetry_program": {
            "device_type": "Continuous Glucose Monitor",
            "program": "glucose_compliance",
        },
        "preferred_specialty": "Endocrinology",
    },
    {
        "profile_id": "behavioral_health",
        "gender": "Male",
        "conditions": ["Depression", "Insomnia"],
        "allergies": [],
        "medications": [
            {"name": "Sertraline", "dosage": "100mg", "frequency": "once daily"},
            {"name": "Zolpidem", "dosage": "5mg", "frequency": "at bedtime"},
        ],
        "telemetry_program": None,
        "preferred_specialty": "Psychiatry",
    },
]

FAMILY_GROUP_THEMES = [
    {
        "theme": "viral_gastroenteritis",
        "children": [
            {
                "gender": "Female",
                "date_of_birth": "2017-04-19",
                "conditions": ["Food Sensitivity"],
                "medications": [],
            },
            {
                "gender": "Male",
                "date_of_birth": "2020-08-11",
                "conditions": [],
                "medications": [],
            },
        ],
    },
    {
        "theme": "developmental_coordination",
        "children": [
            {
                "gender": "Female",
                "date_of_birth": "2018-01-06",
                "conditions": ["Autism Spectrum Disorder"],
                "medications": [
                    {"name": "Melatonin", "dosage": "3mg", "frequency": "at bedtime"}
                ],
            },
            {
                "gender": "Male",
                "date_of_birth": "2014-10-22",
                "conditions": ["ADHD"],
                "medications": [],
            },
        ],
    },
    {
        "theme": "asthma_household",
        "children": [
            {
                "gender": "Male",
                "date_of_birth": "2016-07-14",
                "conditions": ["Asthma"],
                "medications": [
                    {"name": "Montelukast", "dosage": "5mg", "frequency": "once daily"}
                ],
            },
            {
                "gender": "Female",
                "date_of_birth": "2019-03-05",
                "conditions": ["Allergic Rhinitis"],
                "medications": [],
            },
        ],
    },
]

PROVIDER_TEMPLATES = [
    {
        "specialty": "Primary Care",
        "role_prefix": "dr",
        "name_titles": ["MD", "MD"],
        "credentials": ["MD"],
        "languages": ["English", "Spanish"],
        "years_experience": 11,
        "consultation_fee": 135.0,
        "schedule": {
            "monday": ["08:00", "09:00", "10:00", "11:00", "14:00", "15:00"],
            "tuesday": ["08:00", "09:00", "10:00", "11:00", "14:00"],
            "wednesday": ["08:00", "09:00", "10:00", "14:00", "15:00"],
            "thursday": ["08:00", "09:00", "10:00", "11:00", "14:00"],
            "friday": ["08:00", "09:00", "10:00", "11:00"],
        },
    },
    {
        "specialty": "Cardiology",
        "role_prefix": "dr",
        "name_titles": ["MD", "MD"],
        "credentials": ["MD", "FACC"],
        "languages": ["English"],
        "years_experience": 19,
        "consultation_fee": 225.0,
        "schedule": {
            "monday": ["09:00", "10:00", "11:00", "14:00", "15:00"],
            "tuesday": ["09:00", "10:00", "11:00", "14:00"],
            "wednesday": ["09:00", "10:00", "14:00", "15:00"],
            "thursday": ["09:00", "10:00", "11:00", "14:00"],
            "friday": ["09:00", "10:00", "11:00"],
        },
    },
    {
        "specialty": "Pediatrics",
        "role_prefix": "dr",
        "name_titles": ["MD", "MD"],
        "credentials": ["MD", "FAAP"],
        "languages": ["English", "Spanish"],
        "years_experience": 14,
        "consultation_fee": 165.0,
        "schedule": {
            "monday": ["08:30", "09:30", "10:30", "14:00"],
            "tuesday": ["08:30", "09:30", "10:30", "14:00"],
            "wednesday": ["08:30", "09:30", "10:30", "14:00"],
            "thursday": ["08:30", "09:30", "10:30", "14:00"],
            "friday": ["08:30", "09:30", "10:30"],
        },
    },
    {
        "specialty": "Endocrinology",
        "role_prefix": "dr",
        "name_titles": ["MD", "MD"],
        "credentials": ["MD"],
        "languages": ["English", "Hindi"],
        "years_experience": 16,
        "consultation_fee": 210.0,
        "schedule": {
            "monday": ["09:00", "10:00", "13:00", "14:00"],
            "tuesday": ["09:00", "10:00", "13:00", "14:00"],
            "wednesday": ["09:00", "10:00", "13:00"],
            "thursday": ["09:00", "10:00", "13:00", "14:00"],
            "friday": ["09:00", "10:00", "13:00"],
        },
    },
    {
        "specialty": "Pulmonology",
        "role_prefix": "dr",
        "name_titles": ["MD", "MD"],
        "credentials": ["MD"],
        "languages": ["English", "Korean"],
        "years_experience": 17,
        "consultation_fee": 215.0,
        "schedule": {
            "monday": ["08:00", "09:00", "10:00", "14:00"],
            "tuesday": ["08:00", "09:00", "10:00", "14:00"],
            "wednesday": ["08:00", "09:00", "10:00", "14:00"],
            "thursday": ["08:00", "09:00", "10:00", "14:00"],
            "friday": ["08:00", "09:00", "10:00"],
        },
    },
    {
        "specialty": "Neurology",
        "role_prefix": "dr",
        "name_titles": ["MD", "MD"],
        "credentials": ["MD"],
        "languages": ["English", "French"],
        "years_experience": 13,
        "consultation_fee": 230.0,
        "schedule": {
            "monday": ["09:30", "10:30", "14:30"],
            "tuesday": ["09:30", "10:30", "14:30"],
            "wednesday": ["09:30", "10:30", "14:30"],
            "thursday": ["09:30", "10:30", "14:30"],
            "friday": ["09:30", "10:30"],
        },
    },
    {
        "specialty": "Device Coaching",
        "role_prefix": "coach",
        "name_titles": ["RT", "RN"],
        "credentials": ["RT", "RN"],
        "languages": ["English"],
        "years_experience": 9,
        "consultation_fee": 95.0,
        "schedule": {
            "monday": ["08:00", "09:00", "10:00", "15:00"],
            "tuesday": ["08:00", "09:00", "10:00", "15:00"],
            "wednesday": ["08:00", "09:00", "10:00", "15:00"],
            "thursday": ["08:00", "09:00", "10:00", "15:00"],
            "friday": ["08:00", "09:00", "10:00"],
        },
    },
    {
        "specialty": "Care Coordination",
        "role_prefix": "care",
        "name_titles": ["LCSW", "RN"],
        "credentials": ["LCSW", "RN"],
        "languages": ["English", "Spanish"],
        "years_experience": 12,
        "consultation_fee": 110.0,
        "schedule": {
            "monday": ["10:00", "11:00", "13:00", "14:00"],
            "tuesday": ["10:00", "11:00", "13:00", "14:00"],
            "wednesday": ["10:00", "11:00", "13:00", "14:00"],
            "thursday": ["10:00", "11:00", "13:00", "14:00"],
            "friday": ["10:00", "11:00", "13:00"],
        },
    },
    {
        "specialty": "Psychiatry",
        "role_prefix": "dr",
        "name_titles": ["MD", "MD"],
        "credentials": ["MD"],
        "languages": ["English", "Arabic"],
        "years_experience": 15,
        "consultation_fee": 205.0,
        "schedule": {
            "monday": ["11:00", "13:00", "15:00"],
            "tuesday": ["11:00", "13:00", "15:00"],
            "wednesday": ["11:00", "13:00", "15:00"],
            "thursday": ["11:00", "13:00", "15:00"],
            "friday": ["11:00", "13:00"],
        },
    },
]


def _next_phone(index: int) -> str:
    return f"(555) 88{index // 100:01d}-{index % 1000:04d}"


def _insurance_payload(index: int) -> Dict[str, Any]:
    template = INSURANCE_POOL[index % len(INSURANCE_POOL)]
    return {
        "primary": {
            "provider": template["provider"],
            "policy_number": f"{template['policy_prefix']}{700000 + index}",
            "group_number": f"{template['group_prefix']}{100 + index % 900}",
            "copay_primary": float(20 + (index % 4) * 5),
            "copay_specialist": float(45 + (index % 5) * 5),
        }
    }


def _clone_schedule(schedule: Mapping[str, Sequence[str]]) -> Dict[str, List[str]]:
    return {day: list(slots) for day, slots in schedule.items()}


def _empty_case(summary: str) -> Dict[str, Any]:
    return {
        "metadata": {"category": "deterministic_master_data", "summary": summary},
        "patients": [],
        "providers": [],
        "appointments": [],
        "medical_records": [],
        "telemetry_inventory": [],
        "telemetry_uploads": [],
        "regimen_plans": [],
        "medication_suppliers": {},
        "drug_interactions": {},
    }


class DeterministicMasterDataExtender:
    def __init__(self, base_data: Mapping[str, Any], seed: int = 1337):
        self.base_data = copy.deepcopy(dict(base_data))
        self.packer = TelehealthSeedPacker(self.base_data)
        self._rng = random.Random(seed)
        self._fake = Faker("en_US")
        self._fake.random = self._rng
        self.metadata: Dict[str, Any] = {
            "family_groups": [],
            "patient_profiles": {},
            "provider_ids_by_specialty": {},
            "generated_provider_ids": [],
            "telemetry_assignments": [],
        }

    def _build_patient(
        self,
        first_name: str,
        last_name: str,
        date_of_birth: str,
        gender: str,
        address: Mapping[str, Any],
        insurance: Mapping[str, Any],
        conditions: Sequence[str],
        allergies: Sequence[str],
        medications: Sequence[Mapping[str, Any]],
        emergency_contact: Mapping[str, Any],
        requested_id: str,
    ) -> Dict[str, Any]:
        patient_id = self.packer.allocate_patient_id(requested_id)
        email = self.packer._unique_patient_email(
            f"{first_name.lower()}.{last_name.lower()}@tracer-health.org"
        )
        return {
            "patient_id": patient_id,
            "name": {"first_name": first_name, "last_name": last_name},
            "demographics": {
                "date_of_birth": date_of_birth,
                "gender": gender,
                "phone": _next_phone(len(self.metadata["patient_profiles"]) + 200),
                "email": email,
            },
            "address": dict(address),
            "insurance": copy.deepcopy(dict(insurance)),
            "medical_history": {
                "conditions": list(conditions),
                "allergies": list(allergies),
                "medications": [dict(row) for row in medications],
            },
            "emergency_contact": dict(emergency_contact),
        }

    def _family_group_sizes(
        self, target_new_patients: int, target_family_groups: int
    ) -> Tuple[List[int], int]:
        groups = min(target_family_groups, max(0, target_new_patients // 2))
        sizes = [2] * groups
        remaining = target_new_patients - (2 * groups)
        idx = 0
        while remaining > 0 and idx < len(sizes):
            sizes[idx] += 1
            remaining -= 1
            idx += 1
        singles = target_new_patients - sum(sizes)
        return sizes, singles

    def _generate_family_patients(
        self, target_new_patients: int, target_family_groups: int
    ) -> List[Dict[str, Any]]:
        case_patients: List[Dict[str, Any]] = []
        sizes, _ = self._family_group_sizes(target_new_patients, target_family_groups)
        for group_index, group_size in enumerate(sizes):
            theme = FAMILY_GROUP_THEMES[group_index % len(FAMILY_GROUP_THEMES)]
            address = _us_address_dict(self._fake)
            insurance = _insurance_payload(group_index + 1)
            guardian_gender = "Female" if group_index % 2 else "Male"
            guardian_first = _first_name_for_gender(self._fake, guardian_gender)
            last_name = self._fake.last_name()
            guardian = self._build_patient(
                first_name=guardian_first,
                last_name=last_name,
                date_of_birth=f"198{group_index % 10}-0{(group_index % 8) + 1}-1{group_index % 8}",
                gender=guardian_gender,
                address=address,
                insurance=insurance,
                conditions=["Family care coordination"],
                allergies=[],
                medications=[],
                emergency_contact={
                    "name": "Same household contact",
                    "relationship": "Partner",
                    "phone": _next_phone(500 + group_index),
                },
                requested_id=f"{guardian_first}_{last_name}",
            )
            case_patients.append(guardian)
            member_ids = [guardian["patient_id"]]
            self.metadata["patient_profiles"][guardian["patient_id"]] = {
                "profile_id": "family_guardian",
                "preferred_specialty": "Pediatrics",
                "family_group_index": group_index,
            }

            for child_index in range(group_size - 1):
                child_template = theme["children"][child_index % len(theme["children"])]
                child_gender = str(child_template["gender"])
                child_first = _first_name_for_gender(self._fake, child_gender)
                child = self._build_patient(
                    first_name=child_first,
                    last_name=last_name,
                    date_of_birth=str(child_template["date_of_birth"]),
                    gender=child_gender,
                    address=address,
                    insurance=insurance,
                    conditions=child_template["conditions"],
                    allergies=[],
                    medications=child_template["medications"],
                    emergency_contact={
                        "name": f"{guardian['name']['first_name']} {guardian['name']['last_name']}",
                        "relationship": "Parent",
                        "phone": guardian["demographics"]["phone"],
                    },
                    requested_id=f"{child_first}_{last_name}",
                )
                case_patients.append(child)
                member_ids.append(child["patient_id"])
                self.metadata["patient_profiles"][child["patient_id"]] = {
                    "profile_id": str(theme["theme"]),
                    "preferred_specialty": "Pediatrics",
                    "family_group_index": group_index,
                }

            self.metadata["family_groups"].append(
                {
                    "group_id": f"family_group_tracer_{group_index + 1:03d}",
                    "theme": theme["theme"],
                    "member_patient_ids": member_ids,
                    "guardian_patient_id": guardian["patient_id"],
                }
            )
        return case_patients

    def _generate_individual_patients(
        self, target_new_patients: int, target_family_groups: int
    ) -> List[Dict[str, Any]]:
        _, single_count = self._family_group_sizes(
            target_new_patients, target_family_groups
        )
        offset = len(self.metadata["patient_profiles"])
        patients: List[Dict[str, Any]] = []
        for index in range(single_count):
            profile = ADULT_PATIENT_PROFILES[index % len(ADULT_PATIENT_PROFILES)]
            first_name = _first_name_for_gender(self._fake, str(profile["gender"]))
            last_name = self._fake.last_name()
            address = _us_address_dict(self._fake)
            insurance = _insurance_payload(offset + index + 10)
            patient = self._build_patient(
                first_name=first_name,
                last_name=last_name,
                date_of_birth=f"198{(offset + index) % 10}-0{((offset + index) % 8) + 1}-1{(offset + index) % 8}",
                gender=profile["gender"],
                address=address,
                insurance=insurance,
                conditions=profile["conditions"],
                allergies=profile["allergies"],
                medications=profile["medications"],
                emergency_contact={
                    "name": f"{first_name} Contact",
                    "relationship": "Sibling",
                    "phone": _next_phone(650 + index),
                },
                requested_id=f"{first_name}_{last_name}",
            )
            patients.append(patient)
            self.metadata["patient_profiles"][patient["patient_id"]] = {
                "profile_id": profile["profile_id"],
                "preferred_specialty": profile["preferred_specialty"],
                "telemetry_program": copy.deepcopy(profile["telemetry_program"]),
            }
        return patients

    def _generate_providers(self, target_new_providers: int) -> List[Dict[str, Any]]:
        providers: List[Dict[str, Any]] = []
        for index in range(target_new_providers):
            template = PROVIDER_TEMPLATES[index % len(PROVIDER_TEMPLATES)]
            name_titles = template["name_titles"]
            title = str(name_titles[index % len(name_titles)])
            first_name = self._fake.first_name()
            last_name = self._fake.last_name()
            requested_id = f"{first_name}_{last_name}_{template['specialty']}"
            provider_id = self.packer.allocate_provider_id(requested_id)
            email = self.packer._unique_provider_email(
                f"{template['role_prefix']}.{last_name.lower()}.{index + 1}@tracer-health.org"
            )
            provider = {
                "provider_id": provider_id,
                "name": {
                    "first_name": first_name,
                    "last_name": last_name,
                    "title": title,
                },
                "specialty": template["specialty"],
                "license_number": f"{title}{78000 + index}",
                "credentials": list(template["credentials"]),
                "contact": {"phone": _next_phone(900 + index), "email": email},
                "schedule": _clone_schedule(template["schedule"]),
                "consultation_fee": float(template["consultation_fee"]),
                "languages": list(template["languages"]),
                "years_experience": int(template["years_experience"] + (index % 4)),
            }
            providers.append(provider)
            self.metadata["generated_provider_ids"].append(provider_id)
            self.metadata["provider_ids_by_specialty"].setdefault(
                template["specialty"], []
            ).append(provider_id)
        return providers

    def _generate_devices(self, target_new_devices: int) -> List[Dict[str, Any]]:
        devices: List[Dict[str, Any]] = []
        telemetry_candidates = [
            (patient_id, meta["telemetry_program"])
            for patient_id, meta in self.metadata["patient_profiles"].items()
            if meta.get("telemetry_program")
        ]
        for index in range(target_new_devices):
            assigned_to: Optional[str] = None
            telemetry_program: Optional[Mapping[str, Any]] = None
            status = "available"
            if index < len(telemetry_candidates):
                assigned_to, telemetry_program = telemetry_candidates[index]
                status = "deployed" if index % 2 == 0 else "shipped"
            elif telemetry_candidates:
                _, telemetry_program = telemetry_candidates[
                    index % len(telemetry_candidates)
                ]
                status = "inspection" if index % 3 == 0 else "available"
            else:
                telemetry_program = {
                    "device_type": "Wearable EEG",
                    "program": "inventory_spare",
                }

            device_type = str(telemetry_program["device_type"])
            device_id = self.packer.allocate_device_id(None, device_type)
            device = {
                "device_id": device_id,
                "device_type": device_type,
                "status": status,
                "last_audit": f"2026-01-{(index % 9) + 10:02d}",
                "assigned_to": assigned_to,
                "notes": (
                    f"Provisioned for {telemetry_program['program']}"
                    if assigned_to is None
                    else f"Assigned to {assigned_to} for {telemetry_program['program']}"
                ),
            }
            devices.append(device)
            self.metadata["telemetry_assignments"].append(
                {
                    "device_id": device_id,
                    "device_type": device_type,
                    "assigned_to": assigned_to,
                    "program": telemetry_program["program"],
                    "status": status,
                }
            )
        return devices

    def extend(
        self,
        target_new_patients: int,
        target_family_groups: int,
        target_new_providers: int,
        target_new_devices: int,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        case = _empty_case(
            "Deterministically generated telehealth master data additions."
        )
        case["patients"].extend(
            self._generate_family_patients(target_new_patients, target_family_groups)
        )
        case["patients"].extend(
            self._generate_individual_patients(
                target_new_patients, target_family_groups
            )
        )
        case["providers"].extend(self._generate_providers(target_new_providers))
        case["telemetry_inventory"].extend(self._generate_devices(target_new_devices))
        self.metadata["generated_patient_ids"] = [
            row["patient_id"] for row in case["patients"]
        ]
        self.metadata["generated_device_ids"] = [
            row["device_id"] for row in case["telemetry_inventory"]
        ]
        return [case], self.metadata


def generate_master_data_cases(
    input_data_dir: Path,
    target_new_patients: int,
    target_family_groups: int,
    target_new_providers: int,
    target_new_devices: int,
    cases_output_path: Optional[Path] = None,
    metadata_output_path: Optional[Path] = None,
    seed: int = 1337,
    split: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    base_data = load_base_telehealth_data(input_data_dir, split=split)
    extender = DeterministicMasterDataExtender(base_data, seed=seed)
    cases, metadata = extender.extend(
        target_new_patients=target_new_patients,
        target_family_groups=target_family_groups,
        target_new_providers=target_new_providers,
        target_new_devices=target_new_devices,
    )
    if cases_output_path is not None:
        write_json(cases_output_path, {"cases": cases})
    if metadata_output_path is not None:
        write_json(metadata_output_path, metadata)
    return cases, metadata


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="master_data_extender",
        description="Deterministically extend telehealth patients, family groups, providers, and telemetry inventory.",
    )
    parser.add_argument("input_data_dir", type=str)
    parser.add_argument(
        "--split",
        choices=["test", "train"],
        default=None,
        help="Read the split layout of tracer/envs/telehealth/data/. "
        "Omit for a flat directory.",
    )
    parser.add_argument("--target-new-patients", type=int, default=12)
    parser.add_argument("--target-family-groups", type=int, default=3)
    parser.add_argument("--target-new-providers", type=int, default=8)
    parser.add_argument("--target-new-devices", type=int, default=10)
    parser.add_argument(
        "--seed",
        type=int,
        default=1337,
        help="RNG seed for Faker (reproducible names/addresses).",
    )
    parser.add_argument(
        "--cases-out",
        type=str,
        default=str(Path("data_extender") / "generated_telehealth_master_cases.json"),
    )
    parser.add_argument(
        "--metadata-out",
        type=str,
        default=str(
            Path("data_extender") / "generated_telehealth_master_metadata.json"
        ),
    )
    args = parser.parse_args()

    root = repo_root(Path.cwd())
    input_dir = Path(args.input_data_dir)
    resolved_input = input_dir if input_dir.is_absolute() else (root / input_dir)
    cases_out = Path(args.cases_out)
    resolved_cases_out = cases_out if cases_out.is_absolute() else (root / cases_out)
    metadata_out = Path(args.metadata_out)
    resolved_metadata_out = (
        metadata_out if metadata_out.is_absolute() else (root / metadata_out)
    )

    generate_master_data_cases(
        input_data_dir=resolved_input,
        target_new_patients=max(0, args.target_new_patients),
        target_family_groups=max(0, args.target_family_groups),
        target_new_providers=max(0, args.target_new_providers),
        target_new_devices=max(0, args.target_new_devices),
        cases_output_path=resolved_cases_out,
        metadata_output_path=resolved_metadata_out,
        seed=args.seed,
        split=args.split,
    )
    print(f"Wrote deterministic master cases to: {resolved_cases_out}")
    print(f"Wrote deterministic master metadata to: {resolved_metadata_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
