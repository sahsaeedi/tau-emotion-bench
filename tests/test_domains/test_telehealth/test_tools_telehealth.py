"""Tests for the telehealth domain, ported from TRACER\'s environment.

These run against the real data/tau_emotion/domains/telehealth/db.json and pin
the places where the toolkit deliberately follows TRACER's tools: text
output, "not found" reported as a normal message, and TRACER's failures on
missing fields. Each test gets its own freshly loaded db.
"""

import json

import pytest

from tau_emotion.domains.telehealth.data_model import TelehealthDB
from tau_emotion.domains.telehealth.environment import get_environment
from tau_emotion.domains.telehealth.tools import TelehealthTools
from tau_emotion.domains.telehealth.utils import TELEHEALTH_DB_PATH

# Known-good records from the shipped db.json.
PATIENT_ID = "aaron_martin_tracer_0001"
PATIENT_EMAIL = "aaron.martin@tracer-health.org"
PROVIDER_ID = "adrian_christensen_pulmonology_tracer_0001"
UNLICENSED_PROVIDER_ID = "pt_james_chen"
# A Monday with no existing booking for PROVIDER_ID at MONDAY_SLOT.
MONDAY = "2026-03-02"
MONDAY_SLOT = "08:00"


@pytest.fixture
def db() -> TelehealthDB:
    return TelehealthDB.load(TELEHEALTH_DB_PATH)


@pytest.fixture
def tools(db: TelehealthDB) -> TelehealthTools:
    return TelehealthTools(db)


def test_environment_exposes_23_tools():
    assert len(get_environment().tools.get_tools()) == 23


def test_lookups_that_find_nothing_are_messages_not_errors(tools: TelehealthTools):
    assert tools.find_patient_by_email("nobody@example.com") == (
        "No patient found with email: nobody@example.com"
    )
    assert tools.get_patient_details("nope") == "Patient with ID nope not found."
    assert tools.list_telemetry_devices(status_filter="zzz") == (
        "No telemetry devices with status zzz."
    )
    assert tools.get_telemetry_upload("zzz", "2025-01-01") == (
        "No telemetry upload found for device zzz on 2025-01-01."
    )


def test_email_lookup_is_case_sensitive(tools: TelehealthTools):
    assert tools.find_patient_by_email(PATIENT_EMAIL) == PATIENT_ID
    assert tools.find_patient_by_email(PATIENT_EMAIL.upper()).startswith(
        "No patient found"
    )


def test_patient_details_are_formatted_text(tools: TelehealthTools):
    details = tools.get_patient_details(PATIENT_ID)
    assert details.startswith(
        f"Patient Details for Aaron Martin (ID: {PATIENT_ID})\n\nDemographics:"
    )
    assert "- Primary Care Copay: $" in details


def test_provider_without_license_fails_like_tracer(tools: TelehealthTools):
    assert tools.get_provider_details(PROVIDER_ID).startswith(
        f"Provider Details (ID: {PROVIDER_ID})\n\nName: MD Adrian Christensen"
    )
    with pytest.raises(ValueError, match="license_number"):
        tools.get_provider_details(UNLICENSED_PROVIDER_ID)


def test_schedule_then_details_fails_like_tracer(tools: TelehealthTools):
    confirmation = tools.schedule_appointment(
        PATIENT_ID, PROVIDER_ID, MONDAY, MONDAY_SLOT, "follow_up"
    )
    assert confirmation.startswith(
        "Appointment successfully scheduled!\n\nAppointment ID: APPT"
    )
    appointment_id = confirmation.split("Appointment ID: ")[1].split("\n")[0]
    appointment = tools.db.appointments[appointment_id]
    assert appointment.insurance_billed is True
    assert appointment.chief_complaint is None

    # Booking the same slot again is refused with a message, not an error.
    assert tools.schedule_appointment(
        PATIENT_ID, PROVIDER_ID, MONDAY, MONDAY_SLOT, "follow_up"
    ) == (
        f"Provider {PROVIDER_ID} already has an appointment scheduled at "
        f"{MONDAY_SLOT} on {MONDAY}."
    )
    # TRACER's tool never records a chief complaint for new appointments, then reads it.
    with pytest.raises(ValueError, match="chief_complaint"):
        tools.get_appointment_details(appointment_id)


def test_record_updates_return_the_raw_record(tools: TelehealthTools):
    record_id = next(
        r.record_id for r in tools.db.medical_records.values() if r.prescriptions
    )
    medication = tools.db.medical_records[record_id].prescriptions[0].medication

    result = json.loads(
        tools.update_prescription_supplier(
            record_id, medication, "Acme", "AcmeBrand", 12
        )
    )
    prescription = next(
        p for p in result["prescriptions"] if p["medication"] == medication
    )
    assert prescription["supplier"] == {
        "company": "Acme",
        "brand_name": "AcmeBrand",
        "price_usd": 12.0,
        "currency": "USD",
    }
    # Fields the record never had are not invented.
    assert "lab_orders" not in result

    result = json.loads(tools.update_medical_record_note(record_id, "audited"))
    assert result["notes"][-1] == {"note": "audited"}
    result = json.loads(
        tools.update_medical_record_note(record_id, "flagged", {"by": "qa"})
    )
    assert result["notes"][-1] == {"note": "flagged", "metadata": {"by": "qa"}}


def test_update_prescription_supplier_rejects_bad_input_unchanged(
    tools: TelehealthTools,
):
    record = next(r for r in tools.db.medical_records.values() if r.prescriptions)
    prescription = record.prescriptions[0]
    pharmacy_before = prescription.pharmacy

    with pytest.raises(ValueError):
        tools.update_prescription_supplier(
            record.record_id, prescription.medication, "Acme", None, 12
        )
    assert prescription.pharmacy == pharmacy_before
