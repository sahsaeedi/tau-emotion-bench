from __future__ import annotations

import copy
import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence, Tuple

BASE_FILES = [
    "patients.json",
    "providers.json",
    "appointments.json",
    "medical_records.json",
    "medication_suppliers.json",
    "drug_interactions.json",
    "telemetry_inventory.json",
    "telemetry_uploads.json",
]

WEEKDAY_TO_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

INDEX_TO_WEEKDAY = {v: k for k, v in WEEKDAY_TO_INDEX.items()}

SPECIALIST_SPECIALTIES = {
    "Cardiology",
    "Dermatology",
    "Psychiatry",
    "Pediatrics",
    "Endocrinology",
    "Care Coordination",
    "Neurology",
    "Clinical Psychology",
    "Device Coaching",
    "Pulmonology",
    "Developmental Pediatrics",
    "Occupational Therapy",
    "Speech-Language Pathology",
    "Behavioral Analysis",
    "Orthopedic Surgery",
    "Physical Therapy",
    "Anesthesiology",
    "Cardiac Surgery",
}


def repo_root(start: Path) -> Path:
    cur = start.resolve()
    while cur != cur.parent and not (cur / "tracer").exists():
        cur = cur.parent
    if not (cur / "tracer").exists():
        raise RuntimeError(
            "Could not locate repo root (expected a `tracer/` directory)."
        )
    return cur


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=4, ensure_ascii=False, sort_keys=False)
        f.write("\n")


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "item"


def normalize_seed_payload(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(item) for item in payload]
    if isinstance(payload, Mapping):
        if isinstance(payload.get("cases"), list):
            return [dict(item) for item in payload["cases"]]
    raise ValueError(
        "Seed file must be a list of cases or an object with a top-level `cases` list."
    )


# Shared by every split; the other files live in `<data dir>/<split>/`.
CATALOG_FILES = {
    "providers.json",
    "medication_suppliers.json",
    "drug_interactions.json",
}


def _data_file(base_dir: Path, filename: str, split: Optional[str]) -> Path:
    """Where `filename` lives: `base_dir/<split>/` for a split's own files,
    else `base_dir/` (catalog files, or a flat snapshot with `split=None`)."""
    if split is not None and filename not in CATALOG_FILES:
        return base_dir / split / filename
    return base_dir / filename


def load_base_telehealth_data(
    base_dir: Path, split: Optional[str] = None
) -> Dict[str, Any]:
    """Load a telehealth dataset.

    With `split`, `base_dir` has the layout of `tracer/envs/telehealth/data/`:
    catalog files at the top and each split's own files in `<split>/`.
    Without it, `base_dir` is a flat snapshot holding every file.
    """
    out: Dict[str, Any] = {}
    for filename in BASE_FILES:
        out[filename.replace(".json", "")] = read_json(
            _data_file(base_dir, filename, split)
        )
    regimen_path = _data_file(base_dir, "regimen_plans.json", split)
    out["regimen_plans"] = read_json(regimen_path) if regimen_path.exists() else {}
    return out


def summarize_base_data(base_data: Mapping[str, Any]) -> Dict[str, Any]:
    providers_summary = []
    for provider_id, provider in base_data["providers"].items():
        providers_summary.append(
            {
                "provider_id": provider_id,
                "specialty": provider["specialty"],
                "languages": provider.get("languages", []),
                "years_experience": provider.get("years_experience"),
                "schedule": provider.get("schedule", {}),
            }
        )

    return {
        "counts": {
            "patients": len(base_data["patients"]),
            "providers": len(base_data["providers"]),
            "appointments": len(base_data["appointments"]),
            "medical_records": len(base_data["medical_records"]),
            "telemetry_inventory": len(base_data["telemetry_inventory"]),
            "telemetry_uploads": len(base_data["telemetry_uploads"]),
            "regimen_plans": len(base_data["regimen_plans"]),
        },
        "providers": providers_summary,
        "medication_supplier_keys": sorted(base_data["medication_suppliers"].keys()),
        "drug_interaction_catalog": {
            primary: sorted(list(mapping.keys()))
            for primary, mapping in base_data["drug_interactions"].items()
        },
        "existing_patient_ids_sample": sorted(list(base_data["patients"].keys()))[:30],
        "existing_provider_ids_sample": sorted(list(base_data["providers"].keys()))[
            :30
        ],
    }


class TelehealthSeedPacker:
    def __init__(
        self, base_data: Mapping[str, Any], allow_new_slot_repairs: bool = False
    ):
        self.data: Dict[str, Any] = copy.deepcopy(dict(base_data))
        self.allow_new_slot_repairs = allow_new_slot_repairs
        self._repair_baseline_schedule_coverage()
        self.used_patient_ids = set(self.data["patients"].keys())
        self.used_provider_ids = set(self.data["providers"].keys())
        self.used_patient_emails = {
            str(p["demographics"].get("email", "")).strip().lower()
            for p in self.data["patients"].values()
            if str(p["demographics"].get("email", "")).strip()
        }
        self.used_provider_emails = {
            str(p["contact"].get("email", "")).strip().lower()
            for p in self.data["providers"].values()
            if str(p["contact"].get("email", "")).strip()
        }
        self.used_appointment_ids = set(self.data["appointments"].keys())
        self.used_record_ids = set(self.data["medical_records"].keys())
        self.used_device_ids = {
            row["device_id"] for row in self.data["telemetry_inventory"]
        }
        self.next_appointment_number = self._next_number(
            self.used_appointment_ids, "APPT"
        )
        self.next_record_number = self._next_number(self.used_record_ids, "REC")
        self.next_device_number = self._next_device_number(self.used_device_ids)
        self.stats: Dict[str, int] = {
            "patients_added": 0,
            "providers_added": 0,
            "appointments_added": 0,
            "records_added": 0,
            "telemetry_devices_added": 0,
            "telemetry_uploads_added": 0,
            "regimen_plans_added": 0,
            "supplier_entries_added": 0,
            "interaction_entries_added": 0,
        }

    @staticmethod
    def _next_number(keys: Sequence[str], prefix: str) -> int:
        max_seen = 0
        for key in keys:
            match = re.fullmatch(rf"{re.escape(prefix)}(?:_tracer_)?(\d+)", key)
            if match:
                max_seen = max(max_seen, int(match.group(1)))
        return max_seen + 1

    @staticmethod
    def _next_device_number(keys: Sequence[str]) -> int:
        max_seen = 0
        for key in keys:
            match = re.search(r"(?:_tracer_|-)(\d+)$", key)
            if match:
                max_seen = max(max_seen, int(match.group(1)))
        return max_seen + 1

    def _repair_baseline_schedule_coverage(self) -> None:
        for appointment in self.data["appointments"].values():
            provider = self.data["providers"].get(appointment["provider_id"])
            if not provider:
                continue
            self._ensure_provider_slot(
                provider, appointment["date"], appointment["time"]
            )

    def _ensure_provider_slot(
        self, provider: MutableMapping[str, Any], date_value: str, time_value: str
    ) -> None:
        weekday = INDEX_TO_WEEKDAY[parse_date(date_value).weekday()]
        schedule = provider.setdefault("schedule", {})
        slots = schedule.setdefault(weekday, [])
        if time_value not in slots:
            slots.append(time_value)
            slots.sort()

    def allocate_patient_id(self, requested: Optional[str]) -> str:
        if (
            requested
            and "_tracer_" in requested
            and requested not in self.used_patient_ids
        ):
            self.used_patient_ids.add(requested)
            return requested
        base = slugify(requested or "patient")
        counter = 1
        while True:
            candidate = f"{base}_tracer_{counter:04d}"
            if candidate not in self.used_patient_ids:
                self.used_patient_ids.add(candidate)
                return candidate
            counter += 1

    def allocate_provider_id(self, requested: Optional[str]) -> str:
        if (
            requested
            and "_tracer_" in requested
            and requested not in self.used_provider_ids
        ):
            self.used_provider_ids.add(requested)
            return requested
        base = slugify(requested or "provider")
        counter = 1
        while True:
            candidate = f"{base}_tracer_{counter:04d}"
            if candidate not in self.used_provider_ids:
                self.used_provider_ids.add(candidate)
                return candidate
            counter += 1

    def allocate_appointment_id(self, requested: Optional[str]) -> str:
        if (
            requested
            and "_tracer_" in requested
            and requested not in self.used_appointment_ids
        ):
            self.used_appointment_ids.add(requested)
            return requested
        while True:
            candidate = f"APPT_tracer_{self.next_appointment_number:03d}"
            self.next_appointment_number += 1
            if candidate not in self.used_appointment_ids:
                self.used_appointment_ids.add(candidate)
                return candidate

    def allocate_record_id(self, requested: Optional[str]) -> str:
        if (
            requested
            and "_tracer_" in requested
            and requested not in self.used_record_ids
        ):
            self.used_record_ids.add(requested)
            return requested
        while True:
            candidate = f"REC_tracer_{self.next_record_number:03d}"
            self.next_record_number += 1
            if candidate not in self.used_record_ids:
                self.used_record_ids.add(candidate)
                return candidate

    def allocate_device_id(self, requested: Optional[str], device_type: str) -> str:
        if (
            requested
            and "_tracer_" in requested
            and requested not in self.used_device_ids
        ):
            self.used_device_ids.add(requested)
            return requested
        prefix = slugify(device_type).upper()[:6] or "DEVICE"
        while True:
            candidate = f"{prefix}_tracer_{self.next_device_number:03d}"
            self.next_device_number += 1
            if candidate not in self.used_device_ids:
                self.used_device_ids.add(candidate)
                return candidate

    def _unique_patient_email(self, email: str) -> str:
        email = email.strip().lower()
        if not email:
            return email
        if email not in self.used_patient_emails:
            self.used_patient_emails.add(email)
            return email
        stem, _, domain = email.partition("@")
        domain = domain or "example.com"
        counter = 2
        while True:
            candidate = f"{stem}{counter}@{domain}"
            if candidate not in self.used_patient_emails:
                self.used_patient_emails.add(candidate)
                return candidate
            counter += 1

    def _unique_provider_email(self, email: str) -> str:
        email = email.strip().lower()
        if not email:
            return email
        if email not in self.used_provider_emails:
            self.used_provider_emails.add(email)
            return email
        stem, _, domain = email.partition("@")
        domain = domain or "example.com"
        counter = 2
        while True:
            candidate = f"{stem}{counter}@{domain}"
            if candidate not in self.used_provider_emails:
                self.used_provider_emails.add(candidate)
                return candidate
            counter += 1

    def apply_seed_cases(self, cases: Sequence[Mapping[str, Any]]) -> None:
        for case in cases:
            self.apply_case(case)

    def apply_case(self, case: Mapping[str, Any]) -> None:
        patient_map: Dict[str, str] = {}
        provider_map: Dict[str, str] = {}
        appointment_map: Dict[str, str] = {}
        record_map: Dict[str, str] = {}
        device_map: Dict[str, str] = {}

        for patient in case.get("patients", []):
            requested = str(patient.get("patient_id") or "")
            final_id = self.allocate_patient_id(requested or None)
            patient_map[requested] = final_id
            payload = copy.deepcopy(dict(patient))
            payload["patient_id"] = final_id
            email = str(payload.get("demographics", {}).get("email", ""))
            if email:
                payload["demographics"]["email"] = self._unique_patient_email(email)
            self.data["patients"][final_id] = payload
            self.stats["patients_added"] += 1

        for provider in case.get("providers", []):
            requested = str(provider.get("provider_id") or "")
            final_id = self.allocate_provider_id(requested or None)
            provider_map[requested] = final_id
            payload = copy.deepcopy(dict(provider))
            payload["provider_id"] = final_id
            email = str(payload.get("contact", {}).get("email", ""))
            if email:
                payload["contact"]["email"] = self._unique_provider_email(email)
            self.data["providers"][final_id] = payload
            self.stats["providers_added"] += 1

        for appointment in case.get("appointments", []):
            requested = str(appointment.get("appointment_id") or "")
            final_id = self.allocate_appointment_id(requested or None)
            appointment_map[requested] = final_id
            payload = copy.deepcopy(dict(appointment))
            payload["appointment_id"] = final_id
            payload["patient_id"] = patient_map.get(
                str(payload["patient_id"]), str(payload["patient_id"])
            )
            payload["provider_id"] = provider_map.get(
                str(payload["provider_id"]), str(payload["provider_id"])
            )
            self.data["appointments"][final_id] = payload
            provider = self.data["providers"].get(payload["provider_id"])
            if provider is not None and self.allow_new_slot_repairs:
                self._ensure_provider_slot(provider, payload["date"], payload["time"])
            self.stats["appointments_added"] += 1

        for record in case.get("medical_records", []):
            requested = str(record.get("record_id") or "")
            final_id = self.allocate_record_id(requested or None)
            record_map[requested] = final_id
            payload = copy.deepcopy(dict(record))
            payload["record_id"] = final_id
            payload["patient_id"] = patient_map.get(
                str(payload["patient_id"]), str(payload["patient_id"])
            )
            payload["provider_id"] = provider_map.get(
                str(payload["provider_id"]), str(payload["provider_id"])
            )
            appointment_id = payload.get("appointment_id")
            if appointment_id is not None:
                payload["appointment_id"] = appointment_map.get(
                    str(appointment_id), str(appointment_id)
                )
            self.data["medical_records"][final_id] = payload
            self.stats["records_added"] += 1

        for device in case.get("telemetry_inventory", []):
            requested = str(device.get("device_id") or "")
            final_id = self.allocate_device_id(
                requested or None, str(device["device_type"])
            )
            device_map[requested] = final_id
            payload = copy.deepcopy(dict(device))
            payload["device_id"] = final_id
            assigned_to = payload.get("assigned_to")
            if assigned_to is not None:
                payload["assigned_to"] = patient_map.get(
                    str(assigned_to), str(assigned_to)
                )
            self.data["telemetry_inventory"].append(payload)
            self.stats["telemetry_devices_added"] += 1

        for upload in case.get("telemetry_uploads", []):
            payload = copy.deepcopy(dict(upload))
            payload["device_id"] = device_map.get(
                str(payload["device_id"]), str(payload["device_id"])
            )
            self.data["telemetry_uploads"].append(payload)
            self.stats["telemetry_uploads_added"] += 1

        for plan in case.get("regimen_plans", []):
            payload = copy.deepcopy(dict(plan))
            payload["patient_id"] = patient_map.get(
                str(payload["patient_id"]), str(payload["patient_id"])
            )
            self.data["regimen_plans"][payload["patient_id"]] = payload
            self.stats["regimen_plans_added"] += 1

        suppliers = case.get("medication_suppliers", {})
        if isinstance(suppliers, Mapping):
            for medication, entries in suppliers.items():
                if medication not in self.data["medication_suppliers"]:
                    self.data["medication_suppliers"][medication] = []
                existing = self.data["medication_suppliers"][medication]
                existing_keys = {
                    (row["company"], row["brand_name"], float(row["price_usd"]))
                    for row in existing
                }
                for row in entries if isinstance(entries, list) else []:
                    key = (row["company"], row["brand_name"], float(row["price_usd"]))
                    if key not in existing_keys:
                        existing.append(dict(row))
                        existing_keys.add(key)
                        self.stats["supplier_entries_added"] += 1

        interactions = case.get("drug_interactions", {})
        if isinstance(interactions, Mapping):
            for primary, mapping in interactions.items():
                if not isinstance(mapping, Mapping):
                    continue
                if primary not in self.data["drug_interactions"]:
                    self.data["drug_interactions"][primary] = {}
                for secondary, details in mapping.items():
                    if secondary not in self.data["drug_interactions"][primary]:
                        self.stats["interaction_entries_added"] += 1
                    self.data["drug_interactions"][primary][secondary] = dict(details)

    def validate(self) -> None:
        patients = self.data["patients"]
        providers = self.data["providers"]
        appointments = self.data["appointments"]
        records = self.data["medical_records"]
        suppliers = self.data["medication_suppliers"]
        interactions = self.data["drug_interactions"]
        inventory_devices = {
            row["device_id"] for row in self.data["telemetry_inventory"]
        }

        for patient_id, patient in patients.items():
            if patient_id != patient.get("patient_id"):
                raise ValueError(f"Patient key/id mismatch for {patient_id}")
        for provider_id, provider in providers.items():
            if provider_id != provider.get("provider_id"):
                raise ValueError(f"Provider key/id mismatch for {provider_id}")

        patient_emails: set[str] = set()
        for patient in patients.values():
            email = str(patient["demographics"].get("email", "")).strip().lower()
            if not email:
                continue
            if email in patient_emails:
                raise ValueError(f"Duplicate patient email detected: {email}")
            patient_emails.add(email)

        provider_emails: set[str] = set()
        for provider in providers.values():
            email = str(provider["contact"].get("email", "")).strip().lower()
            if not email:
                continue
            if email in provider_emails:
                raise ValueError(f"Duplicate provider email detected: {email}")
            provider_emails.add(email)

        for appointment_id, appointment in appointments.items():
            if appointment_id != appointment.get("appointment_id"):
                raise ValueError(f"Appointment key/id mismatch for {appointment_id}")
            patient_id = appointment["patient_id"]
            provider_id = appointment["provider_id"]
            if patient_id not in patients:
                raise ValueError(
                    f"Appointment {appointment_id} references unknown patient {patient_id}"
                )
            if provider_id not in providers:
                raise ValueError(
                    f"Appointment {appointment_id} references unknown provider {provider_id}"
                )
            weekday = INDEX_TO_WEEKDAY[parse_date(appointment["date"]).weekday()]
            slots = providers[provider_id].get("schedule", {}).get(weekday, [])
            if appointment["time"] not in slots:
                raise ValueError(
                    f"Appointment {appointment_id} uses unavailable slot {appointment['time']} for provider {provider_id}"
                )

        busy_slots: set[Tuple[str, str, str]] = set()
        for appointment_id, appointment in appointments.items():
            if appointment["status"] not in {"scheduled", "pending_approval"}:
                continue
            key = (appointment["provider_id"], appointment["date"], appointment["time"])
            if key in busy_slots:
                raise ValueError(
                    f"Provider slot collision detected at {key} (while validating {appointment_id})"
                )
            busy_slots.add(key)

        for record_id, record in records.items():
            if record_id != record.get("record_id"):
                raise ValueError(f"Medical record key/id mismatch for {record_id}")
            if record["patient_id"] not in patients:
                raise ValueError(
                    f"Record {record_id} references unknown patient {record['patient_id']}"
                )
            if record["provider_id"] not in providers:
                raise ValueError(
                    f"Record {record_id} references unknown provider {record['provider_id']}"
                )
            if (
                record.get("appointment_id") is not None
                and record["appointment_id"] not in appointments
            ):
                raise ValueError(
                    f"Record {record_id} references unknown appointment {record['appointment_id']}"
                )
            for rx in record.get("prescriptions", []):
                if "supplier" in rx and rx["medication"] not in suppliers:
                    raise ValueError(
                        f"Record {record_id} uses supplier info for medication missing from catalog: {rx['medication']}"
                    )

        for row in self.data["telemetry_inventory"]:
            assigned_to = row.get("assigned_to")
            if assigned_to is not None and assigned_to not in patients:
                raise ValueError(
                    f"Telemetry device {row['device_id']} references unknown assigned patient {assigned_to}"
                )

        for row in self.data["telemetry_uploads"]:
            if row["device_id"] not in inventory_devices:
                raise ValueError(
                    f"Telemetry upload references unknown device {row['device_id']}"
                )

        for patient_id, plan in self.data["regimen_plans"].items():
            if patient_id not in patients:
                raise ValueError(
                    f"Regimen plan references unknown patient {patient_id}"
                )
            if patient_id != plan.get("patient_id"):
                raise ValueError(f"Regimen plan key/id mismatch for {patient_id}")

        for primary, mapping in interactions.items():
            if not isinstance(mapping, Mapping):
                raise ValueError(
                    f"Drug interaction mapping for {primary} is not a mapping"
                )

    def write_snapshot(self, out_dir: Path, split: Optional[str] = None) -> None:
        """Write the dataset flat, or with `split` in the layout of
        `tracer/envs/telehealth/data/` (see `load_base_telehealth_data`)."""
        for filename in [*BASE_FILES, "regimen_plans.json"]:
            path = _data_file(out_dir, filename, split)
            path.parent.mkdir(parents=True, exist_ok=True)
            write_json(path, self.data[filename.replace(".json", "")])
