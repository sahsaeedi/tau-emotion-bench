"""Toolkit for the telehealth domain, ported from TRACER's environment
(tracer/tracer/envs/telehealth/).

23 tools, one per tool module in tracer/tracer/envs/telehealth/tools/,
including its return text. Conversion rules from TRACER's tools:

- `data.get("patients", {})` → `self.db.patients`.
- Most of TRACER's tools return formatted text, and report lookups that find
  nothing as a normal message rather than an error; both are kept as-is.
- `return "Error: ..."`, and any exception TRACER's tool raises (e.g. a KeyError
  on a missing field), → `raise ValueError("...")`. Both frameworks show exceptions
  to the agent as "Error: <message>".
- `return json.dumps(record)` → `_record_json(record)`, which leaves out
  fields the record never had, as TRACER's raw dict would.
- `key in record` → the field is not None. The seed data has no explicit
  nulls for these fields, so the two agree.
- Free-function `invoke(data, ...)` → instance method with `@is_tool(...)`.
"""

from __future__ import annotations

import datetime
import json
import re
from typing import Dict, List, Optional

from pydantic import BaseModel

from tau_emotion.domains.telehealth.data_model import (
    Appointment,
    DrugInteractionEntry,
    MedicalRecord,
    PrescriptionSupplier,
    Provider,
    RecordNote,
    RegimenComponent,
    TelehealthDB,
)
from tau_emotion.environment.toolkit import ToolKitBase, ToolType, is_tool

CANCELLATION_DATE = "2025-11-05"


def _record_json(record: BaseModel | List[BaseModel]) -> str:
    if isinstance(record, list):
        return json.dumps([r.model_dump(exclude_unset=True) for r in record])
    return json.dumps(record.model_dump(exclude_unset=True))


def _readable(value: str) -> str:
    return value.replace("_", " ").title()


class TelehealthTools(ToolKitBase):
    """All telehealth domain tools."""

    db: TelehealthDB

    def __init__(self, db: TelehealthDB) -> None:
        super().__init__(db)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _patient_name(self, patient_id: str) -> str:
        patient = self.db.patients.get(patient_id)
        if patient is None:
            return "Unknown Patient"
        return f"{patient.name.first_name} {patient.name.last_name}"

    def _provider_available(
        self, provider: Provider, provider_id: str, date: str, time: str
    ) -> Optional[str]:
        """TRACER's schedule check: a message if the slot is not bookable."""
        try:
            day_of_week = (
                datetime.datetime.strptime(date, "%Y-%m-%d").strftime("%A").lower()
            )
        except ValueError:
            return f"Invalid date format: {date}. Please use YYYY-MM-DD format."
        if day_of_week not in provider.schedule:
            return f"Provider {provider_id} does not work on {day_of_week.title()}."
        available_times = provider.schedule[day_of_week]
        if time not in available_times:
            available_times_str = (
                ", ".join(available_times) if available_times else "None"
            )
            return (
                f"Provider {provider_id} is not available at {time} on "
                f"{day_of_week.title()}. Available times: {available_times_str}"
            )
        return None

    def _slot_taken(
        self, provider_id: str, date: str, time: str, ignore_id: Optional[str] = None
    ) -> bool:
        return any(
            appt_id != ignore_id
            and appt.provider_id == provider_id
            and appt.date == date
            and appt.time == time
            and appt.status in ("scheduled", "pending_approval")
            for appt_id, appt in self.db.appointments.items()
        )

    # ------------------------------------------------------------------
    # Authentication / lookups
    # ------------------------------------------------------------------

    @is_tool(ToolType.READ)
    def find_patient_by_email(self, email: str) -> str:
        """Find a patient by their email address to authenticate their identity.

        Args:
            email: The patient's email address

        Returns:
            The matching patient id, or a message saying no patient was found.
        """
        for patient_id, patient in self.db.patients.items():
            if patient.demographics.email == email:
                return patient_id
        return f"No patient found with email: {email}"

    @is_tool(ToolType.READ)
    def find_patient_by_name_dob(
        self, first_name: str, last_name: str, date_of_birth: str
    ) -> str:
        """Find a patient by their full name and date of birth to authenticate their identity.

        Args:
            first_name: The patient's first name
            last_name: The patient's last name
            date_of_birth: The patient's date of birth in YYYY-MM-DD format

        Returns:
            The matching patient id, or a message saying no patient was found.
        """
        for patient_id, patient in self.db.patients.items():
            if (
                patient.name.first_name.lower() == first_name.lower()
                and patient.name.last_name.lower() == last_name.lower()
                and patient.demographics.date_of_birth == date_of_birth
            ):
                return patient_id
        return (
            f"No patient found with name: {first_name} {last_name} "
            f"and DOB: {date_of_birth}"
        )

    @is_tool(ToolType.READ)
    def get_patient_details(self, patient_id: str) -> str:
        """Get detailed information about a patient including demographics, address, insurance, and medical history.

        Args:
            patient_id: The patient's unique identifier

        Returns:
            The patient's details as formatted text, or a not-found message.
        """
        if patient_id not in self.db.patients:
            return f"Patient with ID {patient_id} not found."
        patient = self.db.patients[patient_id]
        demographics = patient.demographics
        address = patient.address
        insurance = patient.insurance.primary
        history = patient.medical_history
        contact = patient.emergency_contact

        conditions = ", ".join(history.conditions) if history.conditions else "None"
        allergies = ", ".join(history.allergies) if history.allergies else "None"
        medications = (
            ", ".join(f"{m.name} {m.dosage} {m.frequency}" for m in history.medications)
            if history.medications
            else "None"
        )
        return (
            f"Patient Details for {patient.name.first_name} {patient.name.last_name} "
            f"(ID: {patient_id})\n"
            "\n"
            "Demographics:\n"
            f"- Date of Birth: {demographics.date_of_birth}\n"
            f"- Gender: {demographics.gender}\n"
            f"- Phone: {demographics.phone}\n"
            f"- Email: {demographics.email}\n"
            "\n"
            "Address:\n"
            f"- {address.address1}\n"
            f"- {address.address2}\n"
            f"- {address.city}, {address.state} {address.zip}\n"
            f"- {address.country}\n"
            "\n"
            "Insurance:\n"
            f"- Provider: {insurance.provider}\n"
            f"- Policy Number: {insurance.policy_number}\n"
            f"- Primary Care Copay: ${insurance.copay_primary:.2f}\n"
            f"- Specialist Copay: ${insurance.copay_specialist:.2f}\n"
            "\n"
            "Medical History:\n"
            f"- Conditions: {conditions}\n"
            f"- Allergies: {allergies}\n"
            f"- Current Medications: {medications}\n"
            "\n"
            "Emergency Contact:\n"
            f"- {contact.name} ({contact.relationship})\n"
            f"- Phone: {contact.phone}"
        )

    @is_tool(ToolType.READ)
    def get_provider_details(self, provider_id: str) -> str:
        """Get detailed information about a healthcare provider including specialty, schedule, credentials, and contact information.

        Args:
            provider_id: The provider's unique identifier

        Returns:
            The provider's details as formatted text, or a not-found message.

        Raises:
            ValueError: If the provider has no license number (TRACER's tool
                fails on these providers too).
        """
        if provider_id not in self.db.providers:
            return f"Provider with ID {provider_id} not found."
        provider = self.db.providers[provider_id]
        name = provider.name
        if provider.license_number is None:
            # TRACER's tool indexes provider['license_number'] and raises KeyError.
            raise ValueError("'license_number'")

        result = (
            f"Provider Details (ID: {provider_id})\n"
            "\n"
            f"Name: {name.title or 'Dr.'} {name.first_name} {name.last_name}\n"
            f"Specialty: {provider.specialty}\n"
            f"License Number: {provider.license_number}\n"
            f"Credentials: {', '.join(provider.credentials)}\n"
            f"Years of Experience: {provider.years_experience}\n"
            "\n"
            "Contact Information:\n"
            f"- Phone: {provider.contact.phone}\n"
            f"- Email: {provider.contact.email}\n"
            "\n"
            f"Languages: {', '.join(provider.languages)}\n"
            f"Consultation Fee: ${provider.consultation_fee:.2f}\n"
            "\n"
            "Weekly Schedule:"
        )
        for day, times in provider.schedule.items():
            if times:
                result += f"\n- {day.title()}: {', '.join(times)}"
            else:
                result += f"\n- {day.title()}: Not available"
        return result

    @is_tool(ToolType.READ)
    def get_appointment_details(self, appointment_id: str) -> str:
        """Get detailed information about a scheduled appointment including patient, provider, date, time, and clinical details.

        Args:
            appointment_id: The appointment's unique identifier

        Returns:
            The appointment's details as formatted text, or a not-found
            message.

        Raises:
            ValueError: If the appointment has no chief complaint, as with
                appointments booked by schedule_appointment (TRACER's tool fails
                on these too).
        """
        if appointment_id not in self.db.appointments:
            return f"Appointment with ID {appointment_id} not found."
        appointment = self.db.appointments[appointment_id]
        provider = self.db.providers.get(appointment.provider_id)
        provider_name = (
            f"Dr. {provider.name.last_name if provider else 'Unknown Provider'}"
        )
        provider_specialty = provider.specialty if provider else "Unknown"
        if appointment.chief_complaint is None:
            # TRACER's tool indexes appointment['chief_complaint'] and raises KeyError.
            raise ValueError("'chief_complaint'")

        result = (
            f"Appointment Details (ID: {appointment_id})\n"
            "\n"
            f"Patient: {self._patient_name(appointment.patient_id)} "
            f"(ID: {appointment.patient_id})\n"
            f"Provider: {provider_name} - {provider_specialty} "
            f"(ID: {appointment.provider_id})\n"
            "\n"
            "Appointment Information:\n"
            f"- Date: {appointment.date}\n"
            f"- Time: {appointment.time}\n"
            f"- Duration: {appointment.duration_minutes} minutes\n"
            f"- Type: {_readable(appointment.type)}\n"
            f"- Status: {_readable(appointment.status)}\n"
            "\n"
            "Clinical Information:\n"
            f"- Chief Complaint: {appointment.chief_complaint}\n"
            f"- Notes: {appointment.notes}\n"
            "\n"
            "Billing Information:\n"
            f"- Insurance Authorization: {appointment.insurance_authorization}\n"
            f"- Copay Amount: ${appointment.copay_amount:.2f}\n"
            "\n"
            "Meeting Information:\n"
            f"- Meeting Link: {appointment.meeting_link}"
        )
        if appointment.prescription_issued is not None:
            rx = appointment.prescription_issued
            result += (
                f"\n\nPrescription Issued:\n- {rx.medication} {rx.dosage} {rx.frequency}"
                f"\n- Quantity: {rx.quantity}, Refills: {rx.refills}"
            )
        if appointment.referral_from is not None:
            result += f"\n\nReferral from: {appointment.referral_from}"
        if appointment.cancellation_reason is not None:
            result += (
                f"\n\nCancellation Details:\n- Reason: "
                f"{_readable(appointment.cancellation_reason)}\n"
                f"- Date: {appointment.cancellation_date}"
            )
        return result

    @is_tool(ToolType.READ)
    def get_medical_record(
        self,
        record_id: Optional[str] = None,
        appointment_id: Optional[str] = None,
    ) -> str:
        """Retrieve a patient's medical record by record ID or related appointment ID.

        Args:
            record_id: The unique medical record identifier.
            appointment_id: The appointment ID associated with the medical record.

        Returns:
            The medical record as formatted text, or a message when no id is
            given or no record matches.
        """
        if not record_id and not appointment_id:
            return "Please provide a record_id or appointment_id to look up the medical record."

        record: Optional[MedicalRecord] = None
        if record_id:
            record = self.db.medical_records.get(record_id)
            if record is None:
                return f"Medical record with ID {record_id} not found."
        else:
            record = next(
                (
                    r
                    for r in self.db.medical_records.values()
                    if r.appointment_id == appointment_id
                ),
                None,
            )
            if record is None:
                return f"No medical record found for appointment ID {appointment_id}."

        appointment = self.db.appointments.get(record.appointment_id or "")
        patient = self.db.patients.get(record.patient_id)
        provider = self.db.providers.get(record.provider_id)
        patient_name = (
            " ".join(filter(None, [patient.name.first_name, patient.name.last_name]))
            if patient
            else ""
        ) or "Unknown Patient"
        provider_name = (
            " ".join(
                filter(
                    None,
                    [
                        provider.name.title,
                        provider.name.first_name,
                        provider.name.last_name,
                    ],
                )
            )
            if provider
            else ""
        ) or "Unknown Provider"

        lines = [
            f"Medical Record (ID: {record.record_id})",
            f"Patient: {patient_name} (ID: {record.patient_id})",
            f"Provider: {provider_name} (ID: {record.provider_id})",
        ]
        if appointment:
            lines.append(
                f"Related Appointment: {appointment.appointment_id} "
                f"on {appointment.date} at {appointment.time}"
            )
        lines.append(f"Date: {record.date}")
        lines.append(f"Type: {record.type}")
        for key in ["subjective", "objective", "assessment", "plan"]:
            value = getattr(record, key)
            if value is not None:
                lines.append(f"{key.title()}: {value}")
        if record.recommendations:
            lines.append("Recommendations:")
            for rec in record.recommendations:
                lines.append(f"- {rec}")
        return "\n".join(lines)

    @is_tool(ToolType.READ)
    def list_available_providers(self, specialty: Optional[str] = None) -> str:
        """List all available healthcare providers, optionally filtered by specialty (e.g., Primary Care, Cardiology, Dermatology, Psychiatry).

        Args:
            specialty: Optional specialty to filter providers by (e.g., 'Primary Care', 'Cardiology', 'Dermatology', 'Psychiatry')

        Returns:
            The matching providers as formatted text, or a message when none
            match.
        """
        filtered = [
            (provider_id, provider)
            for provider_id, provider in self.db.providers.items()
            if specialty is None or provider.specialty.lower() == specialty.lower()
        ]
        if not filtered:
            if specialty:
                return f"No providers found with specialty: {specialty}"
            return "No providers found."

        result = f"Available Providers{f' - {specialty}' if specialty else ''}:\n\n"
        for provider_id, provider in filtered:
            name = provider.name
            result += f"• {name.title or 'Dr.'} {name.first_name} {name.last_name} (ID: {provider_id})\n"
            result += f"  Specialty: {provider.specialty}\n"
            result += f"  Experience: {provider.years_experience} years\n"
            result += f"  Languages: {', '.join(provider.languages)}\n"
            result += f"  Consultation Fee: ${provider.consultation_fee:.2f}\n"
            result += f"  Phone: {provider.contact.phone}\n\n"
        return result.strip()

    @is_tool(ToolType.READ)
    def list_patient_appointments(
        self, patient_id: str, status_filter: Optional[str] = None
    ) -> str:
        """List all appointments for a patient, optionally filtering by an appointment status such as scheduled, pending_approval, or cancelled.

        Args:
            patient_id: The patient's unique identifier.
            status_filter: Optional appointment status filter (e.g., 'scheduled', 'pending_approval', 'cancelled').

        Returns:
            The patient's appointments, oldest first, as formatted text, or a
            message when the patient or matching appointments are not found.
        """
        if patient_id not in self.db.patients:
            return f"Patient with ID {patient_id} not found."
        normalized_filter = status_filter.lower() if status_filter else None

        matches = [
            (appt_id, appt)
            for appt_id, appt in self.db.appointments.items()
            if appt.patient_id == patient_id
            and (not normalized_filter or appt.status.lower() == normalized_filter)
        ]
        if not matches:
            if normalized_filter:
                return (
                    f"No appointments found for patient {patient_id} with status "
                    f"{status_filter}."
                )
            return f"No appointments found for patient {patient_id}."

        def sort_key(item: tuple[str, Appointment]) -> tuple[datetime.datetime, str]:
            appt_id, appt = item
            try:
                dt_value = datetime.datetime.strptime(
                    f"{appt.date} {appt.time}", "%Y-%m-%d %H:%M"
                )
            except ValueError:
                dt_value = datetime.datetime.min
            return dt_value, appt_id

        matches.sort(key=sort_key)

        header = f"Appointments for {self._patient_name(patient_id)} (ID: {patient_id})"
        if normalized_filter:
            header += f" with status {status_filter}"
        lines = [header]
        for appt_id, appt in matches:
            provider = self.db.providers.get(appt.provider_id)
            if provider:
                provider_label = (
                    f"{provider.name.title or 'Dr.'} {provider.name.last_name}"
                )
                specialty = provider.specialty
            else:
                provider_label, specialty = "Dr. Unknown", "Unknown Specialty"
            lines.append(
                f"- {appt_id}: {appt.date} at {appt.time} with {provider_label} "
                f"({specialty}) [{_readable(appt.status)}, Type: {_readable(appt.type)}]"
            )
        return "\n".join(lines)

    @is_tool(ToolType.READ)
    def list_patient_medical_records(
        self, patient_id: str, limit: Optional[int] = None
    ) -> str:
        """List medical record identifiers for a patient sorted with the newest first.

        Args:
            patient_id: ID of the patient
            limit: Optional maximum number of records to return

        Returns:
            One line per record, newest first, or a message when the patient
            has no records.
        """
        records = [
            r for r in self.db.medical_records.values() if r.patient_id == patient_id
        ]
        if not records:
            return f"No medical records found for patient {patient_id}."

        records.sort(
            key=lambda r: datetime.datetime.strptime(r.date, "%Y-%m-%d"), reverse=True
        )
        if limit is not None and limit > 0:
            records = records[:limit]

        lines = []
        for record in records:
            medications = (
                ", ".join(p.medication for p in record.prescriptions)
                if record.prescriptions
                else "None recorded"
            )
            lines.append(
                f"record_id={record.record_id} | date={record.date} | "
                f"appointment_id={record.appointment_id} | medications={medications}"
            )
        return "Medical records (newest first):\n" + "\n".join(lines)

    @is_tool(ToolType.READ)
    def get_regimen_options(self, patient_id: str) -> str:
        """Retrieve current regimen components and optimized alternative combinations for a patient, including costs and pill burden details.

        Args:
            patient_id: ID of the patient

        Returns:
            The current regimen and optimized options as formatted text, or a
            message when the patient has no regimen data.
        """
        plan = self.db.regimen_plans.get(patient_id)
        if not plan:
            return f"No regimen optimization data available for patient {patient_id}."

        def format_component(c: RegimenComponent) -> str:
            return (
                f"{c.medication} | dosage={c.dosage} | "
                f"daily_dose={c.daily_dose} | monthly_units={c.monthly_units} | "
                f"unit_type={c.unit_type} | brand={c.preferred_brand} | "
                f"supplier={c.supplier} | unit_cost_usd={c.unit_cost_usd:.2f}"
            )

        current = plan.current_regimen
        lines = ["Current regimen components:"]
        for component in current.components:
            lines.append(f"- {format_component(component)}")
        if current.pill_burden:
            lines.append(
                "Current pill burden: "
                f"tablets_per_day={current.pill_burden.tablets_per_day} | "
                f"devices_per_month={current.pill_burden.devices_per_month}"
            )
        if current.notes:
            lines.append("Current regimen notes:")
            for note in current.notes:
                lines.append(f"  * {note}")

        lines.append("Optimized regimen options:")
        for idx, regimen in enumerate(plan.optimized_regimens, start=1):
            lines.append(f"Option {idx}: {regimen.name}")
            lines.append(f"  Focus: {regimen.focus}")
            for component in regimen.components:
                lines.append(f"  - {format_component(component)}")
            if regimen.pill_burden:
                lines.append(
                    "  Pill burden: "
                    f"tablets_per_day={regimen.pill_burden.tablets_per_day} | "
                    f"devices_per_month={regimen.pill_burden.devices_per_month}"
                )
            if regimen.synergy_notes:
                lines.append("  Synergy notes:")
                for note in regimen.synergy_notes:
                    lines.append(f"    - {note}")
        return "\n".join(lines)

    @is_tool(ToolType.READ)
    def list_medication_suppliers(
        self,
        medication: str,
        country_filter: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> str:
        """List suppliers for a given medication, optionally filtered by country and sorted by price.

        Args:
            medication: Medication name to search for
            country_filter: Optional country name to filter suppliers
            limit: Optional maximum number of suppliers to list

        Returns:
            One line per supplier, cheapest first, or a message when none
            match.
        """
        canonical = {key.lower(): key for key in self.db.medication_suppliers}
        medication_key = canonical.get(medication.lower())
        suppliers = (
            self.db.medication_suppliers.get(medication_key) if medication_key else None
        )
        if not suppliers and medication_key is None:
            return (
                f"No supplier information found for {medication}. "
                "(Tip: ensure the medication name matches the catalog)"
            )
        if not suppliers:
            return f"No supplier information found for {medication}."

        if country_filter:
            suppliers = [
                s for s in suppliers if s.country.lower() == country_filter.lower()
            ]
            if not suppliers:
                return f"No suppliers in {country_filter} for {medication}."
        suppliers = sorted(suppliers, key=lambda s: s.price_usd)
        if limit is not None and limit > 0:
            suppliers = suppliers[:limit]

        lines = [
            f"{s.company} ({s.country}) | brand={s.brand_name} | price_usd={s.price_usd:.2f}"
            for s in suppliers
        ]
        return f"Suppliers for {medication}:\n" + "\n".join(lines)

    @is_tool(ToolType.READ)
    def list_telemetry_devices(
        self,
        status_filter: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> str:
        """List telemetry wearable devices optionally filtered by status.

        Args:
            status_filter: Optional status filter (e.g., 'available', 'missing_overdue').
            limit: Optional maximum number of devices to list.

        Returns:
            One line per device, sorted by device id, or a message when none
            match.
        """
        inventory = self.db.telemetry_inventory
        if not inventory:
            return "Telemetry inventory is empty."
        if status_filter:
            inventory = [
                d for d in inventory if d.status.lower() == status_filter.lower()
            ]
            if not inventory:
                return f"No telemetry devices with status {status_filter}."
        inventory = sorted(inventory, key=lambda d: d.device_id)
        if limit is not None and limit > 0:
            inventory = inventory[:limit]

        lines = [
            f"{d.device_id} | status={d.status} | last_audit={d.last_audit} | notes={d.notes}"
            for d in inventory
        ]
        return "Telemetry devices:\n" + "\n".join(lines)

    @is_tool(ToolType.READ)
    def list_telemetry_uploads(
        self,
        device_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> str:
        """List telemetry upload artifacts for a device over an optional date window.

        Args:
            device_id: Unique identifier of the telemetry device
            start_date: Start date (inclusive, YYYY-MM-DD)
            end_date: End date (inclusive, YYYY-MM-DD)
            limit: Optional maximum number of entries to return

        Returns:
            A JSON list of the matching uploads sorted by date, or a message
            when none match.
        """
        matches = [
            u
            for u in self.db.telemetry_uploads
            if u.device_id == device_id
            and not (start_date and u.date < start_date)
            and not (end_date and u.date > end_date)
        ]
        matches.sort(key=lambda u: u.date)
        if limit is not None and limit > 0:
            matches = matches[:limit]
        if not matches:
            return (
                f"No telemetry uploads found for device {device_id} in the "
                "specified window."
            )
        return _record_json(matches)

    @is_tool(ToolType.READ)
    def get_telemetry_upload(self, device_id: str, date: str) -> str:
        """Retrieve a specific telemetry upload artifact for a device and date.

        Args:
            device_id: Unique identifier of the telemetry device
            date: Target date (YYYY-MM-DD)

        Returns:
            The upload as JSON, or a message when none matches.
        """
        for upload in self.db.telemetry_uploads:
            if upload.device_id == device_id and upload.date == date:
                return _record_json(upload)
        return f"No telemetry upload found for device {device_id} on {date}."

    @is_tool(ToolType.READ)
    def check_drug_interactions(
        self, primary_medication: str, current_medications: List[str]
    ) -> str:
        """Evaluate potential interactions between an incident medication and a patient’s current regimen.

        Args:
            primary_medication: The medication that was taken accidentally or requires review.
            current_medications: List of the patient’s active medications.

        Returns:
            A formatted, multi-line interaction summary, or a "no
            interactions" message when none are documented.
        """
        interactions: Dict[str, Dict[str, DrugInteractionEntry]] = (
            self.db.drug_interactions
        )
        canonical: Dict[str, str] = {}
        for outer, inner in interactions.items():
            canonical.setdefault(outer.lower(), outer)
            for inner_key in inner:
                canonical.setdefault(inner_key.lower(), inner_key)

        def canon(name: str) -> str:
            return canonical.get(name.lower(), name)

        def lookup(a: str, b: str) -> Optional[DrugInteractionEntry]:
            ka, kb = canon(a), canon(b)
            for candidate, det in interactions.get(ka, {}).items():
                if candidate.lower() == kb.lower():
                    return det
            for candidate, det in interactions.get(kb, {}).items():
                if candidate.lower() == ka.lower():
                    return det
            return None

        severity_rank = {"low": 1, "moderate": 2, "high": 3}
        lines: List[str] = []
        skip_set: set = set()
        emergency = False
        max_overlap = 0
        highest_severity = "none"
        severity_reason: Optional[str] = None

        def consume(a: str, b: str, det: DrugInteractionEntry) -> None:
            nonlocal emergency, max_overlap, highest_severity, severity_reason
            skip_set.update(det.skip)
            emergency = emergency or det.emergency
            max_overlap = max(max_overlap, det.time_overlap_hours)
            display = f"{canon(a)} + {canon(b)}"
            lines.append(
                f"{display}: severity={det.severity}, risk_score={det.risk_score}, "
                f"overlap_hours={det.time_overlap_hours}. {det.action}"
            )
            if severity_rank.get(det.severity, 0) > severity_rank.get(
                highest_severity, 0
            ):
                highest_severity = det.severity
                severity_reason = display

        for med in current_medications:
            det = lookup(primary_medication, med)
            if det:
                consume(primary_medication, med, det)
        for i, a in enumerate(current_medications):
            for b in current_medications[i + 1 :]:
                det = lookup(a, b)
                if det:
                    consume(a, b, det)

        if not lines:
            return (
                "No documented high-risk interactions found for the supplied "
                "medications. Continue monitoring as per care plan."
            )

        summary = [
            "Drug interaction analysis:",
            *lines,
            "",
            f"Medications to hold today: {', '.join(sorted(skip_set)) if skip_set else 'None'}",
            f"Emergency escalation required: {'Yes' if emergency else 'No'}",
            f"Peak overlap risk window (hours): {max_overlap}",
        ]
        if severity_reason:
            summary.append(
                f"Highest severity interaction: {severity_reason} ({highest_severity})"
            )
        return "\n".join(summary)

    # ------------------------------------------------------------------
    # WRITE tools
    # ------------------------------------------------------------------

    @is_tool(ToolType.WRITE)
    def schedule_appointment(
        self,
        patient_id: str,
        provider_id: str,
        date: str,
        time: str,
        appointment_type: str,
        bill_insurance: bool = True,
        voucher_id: Optional[str] = None,
        payment_notes: Optional[str] = None,
    ) -> str:
        """Schedule a new telehealth appointment for a patient with a healthcare provider.

        Args:
            patient_id: The patient's unique identifier
            provider_id: The provider's unique identifier
            date: Appointment date in YYYY-MM-DD format
            time: Appointment time in HH:MM format (24-hour)
            appointment_type: Type of appointment (routine_checkup, follow_up, consultation, specialist_consultation, sick_visit)
            bill_insurance: Set to false to skip insurance billing for this appointment
            voucher_id: Optional voucher identifier applied to this appointment
            payment_notes: Optional notes regarding payment handling

        Returns:
            A confirmation with the new appointment id, or a message saying
            why the appointment could not be scheduled.
        """
        if patient_id not in self.db.patients:
            return f"Patient with ID {patient_id} not found."
        if provider_id not in self.db.providers:
            return f"Provider with ID {provider_id} not found."
        patient = self.db.patients[patient_id]
        provider = self.db.providers[provider_id]

        unavailable = self._provider_available(provider, provider_id, date, time)
        if unavailable:
            return unavailable
        if self._slot_taken(provider_id, date, time):
            return f"Provider {provider_id} already has an appointment scheduled at {time} on {date}."

        existing_nums = [
            int(m.group(1))
            for appt_id in self.db.appointments
            if (m := re.match(r"^APPT(?:_tracer_)?(\d+)$", appt_id))
        ]
        new_num = max(existing_nums) + 1 if existing_nums else 1
        # Avoid colliding with either legacy or tracer appointment ids.
        while (
            f"APPT{new_num:03d}" in self.db.appointments
            or f"APPT_tracer_{new_num:03d}" in self.db.appointments
        ):
            new_num += 1
        new_id = f"APPT{new_num:03d}"

        insurance = patient.insurance.primary
        if provider.specialty == "Primary Care":
            base_copay = insurance.copay_primary
        else:
            base_copay = insurance.copay_specialist

        if bill_insurance:
            copay_amount = base_copay
            payment_method = "insurance"
            insurance_billed = True
            applied_voucher = None
            insurance_auth: Optional[str] = f"AUTH{new_num:06d}"
        else:
            payment_method = "telehealth_voucher" if voucher_id else "self_pay"
            insurance_billed = False
            applied_voucher = voucher_id
            copay_amount = 0.0
            insurance_auth = None

        # Like TRACER's tool, no chief_complaint is recorded for new appointments.
        appointment = Appointment(
            appointment_id=new_id,
            patient_id=patient_id,
            provider_id=provider_id,
            date=date,
            time=time,
            duration_minutes=30,
            type=appointment_type,
            status="scheduled",
            notes=payment_notes or "",
            insurance_authorization=insurance_auth,
            copay_amount=copay_amount,
            meeting_link=f"https://telehealth.healthcenter.com/room/{new_id}",
            payment_method=payment_method,
            voucher_id=applied_voucher,
            insurance_billed=insurance_billed,
        )
        self.db.appointments[new_id] = appointment

        lines = [
            "Appointment successfully scheduled!",
            "",
            f"Appointment ID: {new_id}",
            f"Patient: {patient.name.first_name} {patient.name.last_name}",
            f"Provider: Dr. {provider.name.last_name} - {provider.specialty}",
            f"Date: {date}",
            f"Time: {time}",
            f"Type: {_readable(appointment_type)}",
        ]
        if bill_insurance:
            lines.append(f"Copay: ${copay_amount:.2f}")
            lines.append(f"Insurance Authorization: {insurance_auth}")
        else:
            lines.append("Insurance Billing: Skipped")
            lines.append(f"Payment Method: {_readable(payment_method)}")
            if applied_voucher:
                lines.append(f"Voucher Applied: {applied_voucher}")
            lines.append(f"Amount Due Today: ${copay_amount:.2f}")
            if payment_notes:
                lines.append(f"Billing Notes: {payment_notes}")
        lines.append(f"Meeting Link: {appointment.meeting_link}")
        lines.append("")
        lines.append("Please save your appointment ID for future reference.")
        return "\n".join(lines)

    @is_tool(ToolType.WRITE)
    def cancel_appointment(self, appointment_id: str) -> str:
        """Cancel a scheduled appointment.

        Args:
            appointment_id: The appointment's unique identifier

        Returns:
            A cancellation confirmation, or a message saying why the
            appointment could not be cancelled.
        """
        if appointment_id not in self.db.appointments:
            return f"Appointment with ID {appointment_id} not found."
        appointment = self.db.appointments[appointment_id]
        if appointment.status == "cancelled":
            return f"Appointment {appointment_id} is already cancelled."
        if appointment.status == "completed":
            return f"Cannot cancel appointment {appointment_id} - appointment has already been completed."

        appointment.status = "cancelled"
        appointment.cancellation_reason = "patient_cancelled"
        # Fixed date keeps replays deterministic (TRACER's tool uses datetime.now()).
        appointment.cancellation_date = CANCELLATION_DATE

        provider = self.db.providers.get(appointment.provider_id)
        provider_name = (
            f"Dr. {provider.name.last_name if provider else 'Unknown Provider'}"
        )
        return (
            "Appointment successfully cancelled.\n"
            "\n"
            f"Appointment ID: {appointment_id}\n"
            f"Patient: {self._patient_name(appointment.patient_id)}\n"
            f"Provider: {provider_name}\n"
            f"Original Date/Time: {appointment.date} at {appointment.time}\n"
            f"Cancellation Reason: {_readable(appointment.cancellation_reason)}\n"
            f"Cancellation Date: {appointment.cancellation_date}\n"
            "\n"
            "The appointment slot is now available for other patients. If this "
            "was a patient cancellation, please remind them of the cancellation policy."
        )

    @is_tool(ToolType.WRITE)
    def reschedule_appointment(
        self, appointment_id: str, new_date: str, new_time: str
    ) -> str:
        """Reschedule an existing appointment to a new date and time.

        Args:
            appointment_id: The appointment's unique identifier
            new_date: New appointment date in YYYY-MM-DD format
            new_time: New appointment time in HH:MM format (24-hour)

        Returns:
            A confirmation with the previous and new times, or a message
            saying why the appointment could not be rescheduled.

        Raises:
            ValueError: If the appointment's provider no longer exists.
        """
        if appointment_id not in self.db.appointments:
            return f"Appointment with ID {appointment_id} not found."
        appointment = self.db.appointments[appointment_id]
        if appointment.status == "cancelled":
            return f"Cannot reschedule appointment {appointment_id} - appointment has been cancelled."
        if appointment.status == "completed":
            return f"Cannot reschedule appointment {appointment_id} - appointment has already been completed."

        provider_id = appointment.provider_id
        if provider_id not in self.db.providers:
            # TRACER's tool indexes providers[provider_id] and raises KeyError.
            raise ValueError(repr(provider_id))
        provider = self.db.providers[provider_id]

        unavailable = self._provider_available(
            provider, provider_id, new_date, new_time
        )
        if unavailable:
            return unavailable
        if self._slot_taken(provider_id, new_date, new_time, ignore_id=appointment_id):
            return f"Provider {provider_id} already has an appointment scheduled at {new_time} on {new_date}."

        old_date, old_time = appointment.date, appointment.time
        appointment.date = new_date
        appointment.time = new_time
        return (
            "Appointment successfully rescheduled.\n"
            "\n"
            f"Appointment ID: {appointment_id}\n"
            f"Patient: {self._patient_name(appointment.patient_id)}\n"
            f"Provider: Dr. {provider.name.last_name} - {provider.specialty}\n"
            "\n"
            f"Previous Date/Time: {old_date} at {old_time}\n"
            f"New Date/Time: {new_date} at {new_time}\n"
            "\n"
            f"Meeting Link: {appointment.meeting_link}\n"
            "\n"
            "Please update your calendar with the new appointment time."
        )

    @is_tool(ToolType.WRITE)
    def update_medical_record_note(self, record_id: str, note: str) -> str:
        """Append an audit or compliance note to a medical record.

        Args:
            record_id: Identifier of the medical record to update
            note: Note text to append

        Returns:
            The updated medical record as JSON.

        Raises:
            ValueError: If the record is not found.
        """
        record = self.db.medical_records.get(record_id)
        if not record:
            raise ValueError(f"medical record {record_id} not found")
        # Reassign rather than append so the field counts as set on the record.
        record.notes = [*record.notes, RecordNote(note=note)]
        return _record_json(record)

    @is_tool(ToolType.WRITE)
    def update_prescription_supplier(
        self,
        record_id: str,
        medication: str,
        supplier_company: str,
        brand_name: str,
        price_usd: float,
        currency: str = "USD",
    ) -> str:
        """Update the supplier information for a prescription in a medical record.

        Args:
            record_id: The medical record identifier, such as 'REC001'.
            medication: Name of the medication to update.
            supplier_company: Name of the supplier company providing the medication.
            brand_name: Brand name used by the supplier for this medication.
            price_usd: Price in USD from the supplier catalog.
            currency: Currency code for the quoted price (defaults to 'USD').

        Returns:
            The updated medical record as JSON.

        Raises:
            ValueError: If the record, its prescriptions, or the medication is
                not found.
        """
        if record_id not in self.db.medical_records:
            raise ValueError("medical record not found")
        record = self.db.medical_records[record_id]
        if not record.prescriptions:
            raise ValueError("medical record has no prescriptions")

        # A dict, as in TRACER's tool: when two prescriptions share a name, the
        # last wins.
        by_name = {p.medication.strip().lower(): p for p in record.prescriptions}
        normalized_name = medication.strip().lower()
        prescription = by_name.get(normalized_name)
        if prescription is None:
            # Partial match handles appended dosage text like "lamotrigine 100mg BID".
            for key, value in by_name.items():
                if normalized_name.startswith(key) or key.startswith(normalized_name):
                    prescription = value
                    break
        if prescription is None:
            raise ValueError(f"medication {medication} not found in record {record_id}")

        prescription.pharmacy = f"{supplier_company} ({brand_name})"
        prescription.supplier = PrescriptionSupplier(
            company=supplier_company,
            brand_name=brand_name,
            price_usd=float(price_usd),
            currency=currency,
        )
        return _record_json(record)

    # ------------------------------------------------------------------
    # GENERIC / utility tools
    # ------------------------------------------------------------------

    @is_tool(ToolType.GENERIC)
    def calculate(self, expression: str) -> str:
        """Calculate the result of a mathematical expression.

        Args:
            expression: The mathematical expression to calculate, such as '2 + 2'. The expression can contain numbers, operators (+, -, *, /), parentheses, and spaces.

        Returns:
            The numeric result rounded to two decimals, as a string.

        Raises:
            ValueError: If the expression contains disallowed characters or
                cannot be evaluated.
        """
        if not all(ch in "0123456789+-*/(). " for ch in expression):
            raise ValueError("invalid characters in expression")
        try:
            value = eval(expression, {"__builtins__": None}, {})  # noqa: S307
            return str(round(float(value), 2))
        except Exception as e:
            raise ValueError(str(e)) from e

    @is_tool(ToolType.WRITE)
    def transfer_to_human_support(self, reason: str) -> str:
        """Transfer the patient to human support staff when the request cannot be handled by the automated system.

        Args:
            reason: Reason for transferring to human support

        Returns:
            A confirmation message.
        """
        return (
            "Transferring you to a human support representative.\n\n"
            f"Reason for transfer: {reason}\n\n"
            "Please hold while we connect you to a member of our support "
            "team. They will be able to assist you with your request.\n\n"
            "Estimated wait time: 2-3 minutes.\n\nThank you for your patience."
        )

    @is_tool(ToolType.THINK)
    def think(self, thought: str) -> str:
        """Use the tool to think about something. It will not obtain new
        information or change the database, but just append the thought to
        the log. Use it when complex reasoning or some cache memory is needed.

        Args:
            thought: A thought to think about.

        Returns:
            An empty string.
        """
        return ""
