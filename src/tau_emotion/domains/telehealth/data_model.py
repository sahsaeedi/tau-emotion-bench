"""Pydantic models for the telehealth domain.

Schema is reverse-engineered from TRACER's telehealth data files
(tracer/tracer/envs/telehealth/data/) merged into db.json. Many sub-record
fields are optional because TRACER's data only populates them on a subset of
records and the
tools (e.g. update_medical_record_note, update_prescription_supplier,
schedule_appointment) progressively add fields at write time.
"""

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field

from tau_emotion.domains.telehealth.utils import TELEHEALTH_DB_PATH
from tau_emotion.environment.db import DB

# ---------------------------------------------------------------------------
# Patients
# ---------------------------------------------------------------------------


class Name(BaseModel):
    first_name: str
    last_name: str
    # Providers add a `title` (e.g. "MD"). Patients usually don't.
    title: Optional[str] = None


class Demographics(BaseModel):
    date_of_birth: str
    gender: Optional[str] = None
    phone: str
    email: str


class Address(BaseModel):
    address1: str
    address2: Optional[str] = ""
    city: str
    state: str
    zip: str
    country: str


class InsurancePlan(BaseModel):
    provider: str
    policy_number: str
    group_number: Optional[str] = None
    copay_primary: float
    copay_specialist: float


class Insurance(BaseModel):
    primary: InsurancePlan


class HistoryMedication(BaseModel):
    name: str
    dosage: Optional[str] = None
    frequency: Optional[str] = None


class HistorySurgery(BaseModel):
    procedure: str
    date: Optional[str] = None
    surgeon: Optional[str] = None


class MedicalHistory(BaseModel):
    conditions: List[str] = Field(default_factory=list)
    allergies: List[str] = Field(default_factory=list)
    medications: List[HistoryMedication] = Field(default_factory=list)
    surgeries: List[HistorySurgery] = Field(default_factory=list)


class EmergencyContact(BaseModel):
    name: str
    relationship: str
    phone: str


class Patient(BaseModel):
    patient_id: str
    name: Name
    demographics: Demographics
    address: Address
    insurance: Insurance
    medical_history: MedicalHistory
    emergency_contact: EmergencyContact


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


class Contact(BaseModel):
    phone: str
    email: str


class Provider(BaseModel):
    provider_id: str
    name: Name
    specialty: str
    # A few providers (e.g. physical therapists, orthopedics) lack a
    # license_number in the seed data.
    license_number: Optional[str] = None
    credentials: List[str] = Field(default_factory=list)
    contact: Contact
    # Day-of-week (lowercase) → ordered list of HH:MM slots.
    schedule: Dict[str, List[str]] = Field(default_factory=dict)
    consultation_fee: float
    languages: List[str] = Field(default_factory=list)
    years_experience: int


# ---------------------------------------------------------------------------
# Appointments
# ---------------------------------------------------------------------------


class PrescriptionIssued(BaseModel):
    medication: str
    dosage: str
    frequency: str
    quantity: str
    refills: int


class Appointment(BaseModel):
    appointment_id: str
    patient_id: str
    provider_id: str
    date: str
    time: str
    duration_minutes: int
    type: str
    status: Literal[
        "scheduled", "pending_approval", "completed", "cancelled", "no_show"
    ]
    chief_complaint: Optional[str] = None
    notes: Optional[str] = ""
    insurance_authorization: Optional[str] = None
    copay_amount: float = 0.0
    meeting_link: Optional[str] = None
    # Rarely-present optional fields.
    prescription_issued: Optional[PrescriptionIssued] = None
    referral_from: Optional[str] = None
    cancellation_reason: Optional[str] = None
    cancellation_date: Optional[str] = None
    # Added by schedule_appointment at write time when bill_insurance=False.
    payment_method: Optional[str] = None
    voucher_id: Optional[str] = None
    insurance_billed: Optional[bool] = None


# ---------------------------------------------------------------------------
# Medical records
# ---------------------------------------------------------------------------


class PrescriptionSupplier(BaseModel):
    company: str
    brand_name: str
    price_usd: float
    currency: str = "USD"
    country: Optional[str] = None


class Prescription(BaseModel):
    medication: str
    dosage: Optional[str] = None
    frequency: Optional[str] = None
    quantity: Optional[str] = None
    refills: Optional[int] = None
    duration: Optional[str] = None
    brand: Optional[str] = None
    pharmacy: Optional[str] = None
    # In some seed records `supplier` is a plain company-name string;
    # update_prescription_supplier rewrites it to a structured object.
    supplier: Optional[Union[PrescriptionSupplier, str]] = None
    unit_cost_usd: Optional[float] = None


class VitalSigns(BaseModel):
    blood_pressure: Optional[str] = None
    heart_rate: Optional[int] = None
    height: Optional[str] = None
    temperature: Optional[float] = None
    weight: Optional[str] = None


class RecordNote(BaseModel):
    note: str


class MedicalRecord(BaseModel):
    record_id: str
    # A few seed records (e.g. REC026/REC028/REC029) have null appointment_id.
    appointment_id: Optional[str] = None
    patient_id: str
    provider_id: str
    date: str
    type: str
    subjective: Optional[str] = None
    objective: Optional[str] = None
    assessment: Optional[str] = None
    plan: Optional[str] = None
    prescriptions: List[Prescription] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    lab_orders: List[str] = Field(default_factory=list)
    vital_signs: Optional[VitalSigns] = None
    next_appointment: Optional[str] = None
    # Appended by update_medical_record_note at write time.
    notes: List[RecordNote] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Regimen plans
# ---------------------------------------------------------------------------


class RegimenComponent(BaseModel):
    medication: str
    dosage: str
    daily_dose: int
    monthly_units: int
    unit_type: str
    preferred_brand: Optional[str] = None
    supplier: Optional[str] = None
    unit_cost_usd: Optional[float] = None


class PillBurden(BaseModel):
    tablets_per_day: Optional[int] = None
    devices_per_month: Optional[int] = None


class CurrentRegimen(BaseModel):
    components: List[RegimenComponent] = Field(default_factory=list)
    pill_burden: Optional[PillBurden] = None
    notes: List[str] = Field(default_factory=list)


class OptimizedRegimen(BaseModel):
    name: str
    focus: Optional[str] = None
    components: List[RegimenComponent] = Field(default_factory=list)
    pill_burden: Optional[PillBurden] = None
    synergy_notes: List[str] = Field(default_factory=list)


class RegimenPlan(BaseModel):
    patient_id: str
    current_regimen: CurrentRegimen
    optimized_regimens: List[OptimizedRegimen] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Drug interactions
# ---------------------------------------------------------------------------


class DrugInteractionEntry(BaseModel):
    severity: str
    risk_score: int
    time_overlap_hours: int
    action: str
    skip: List[str] = Field(default_factory=list)
    emergency: bool = False


# ---------------------------------------------------------------------------
# Medication suppliers
# ---------------------------------------------------------------------------


class MedicationSupplier(BaseModel):
    company: str
    country: str
    brand_name: str
    price_usd: float


# ---------------------------------------------------------------------------
# Telemetry inventory + uploads (both lists in v1)
# ---------------------------------------------------------------------------


class TelemetryInventory(BaseModel):
    device_id: str
    device_type: str
    status: str
    last_audit: Optional[str] = None
    assigned_to: Optional[str] = None
    notes: Optional[str] = None


class TelemetryUpload(BaseModel):
    device_id: str
    date: str
    usage_hours: float
    synced_at: Optional[str] = None
    event: Optional[str] = None
    alerts: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Top-level DB
# ---------------------------------------------------------------------------


class TelehealthDB(DB):
    """Telehealth database: patients, providers, appointments, medical
    records, regimen plans, drug interactions, medication suppliers, and
    telemetry inventory/uploads.
    """

    patients: Dict[str, Patient]
    providers: Dict[str, Provider]
    appointments: Dict[str, Appointment]
    medical_records: Dict[str, MedicalRecord]
    regimen_plans: Dict[str, RegimenPlan]
    # Outer key: medication that was taken / under review.
    # Inner key: other medication being checked against.
    drug_interactions: Dict[str, Dict[str, DrugInteractionEntry]]
    # Medication name → ordered list of suppliers.
    medication_suppliers: Dict[str, List[MedicationSupplier]]
    telemetry_inventory: List[TelemetryInventory]
    telemetry_uploads: List[TelemetryUpload]

    def get_statistics(self) -> dict[str, Any]:
        return {
            "num_patients": len(self.patients),
            "num_providers": len(self.providers),
            "num_appointments": len(self.appointments),
            "num_medical_records": len(self.medical_records),
            "num_regimen_plans": len(self.regimen_plans),
            "num_drug_interaction_anchors": len(self.drug_interactions),
            "num_medications_with_suppliers": len(self.medication_suppliers),
            "num_telemetry_devices": len(self.telemetry_inventory),
            "num_telemetry_uploads": len(self.telemetry_uploads),
        }


def get_db() -> TelehealthDB:
    return TelehealthDB.load(TELEHEALTH_DB_PATH)


if __name__ == "__main__":
    db = get_db()
    print(db.get_statistics())
