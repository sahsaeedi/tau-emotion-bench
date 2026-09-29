# Copyright Sierra
"""Read-only reverse tools for telehealth task generation (grounding without mutating state)."""

from tracer.envs.airline.reverse_tools.think import Think  # no-op scratchpad, shared

from .check_drug_interactions import CheckDrugInteractions
from .check_provider_appointment_slot import CheckProviderAppointmentSlot
from .get_appointment_details import GetAppointmentDetails
from .get_medical_record import GetMedicalRecord
from .get_patient_details_complete import GetPatientDetailsComplete
from .get_provider_details import GetProviderDetails
from .get_regimen_options import GetRegimenOptions
from .list_assigned_telemetry_devices import ListAssignedTelemetryDevices
from .list_available_providers import ListAvailableProviders
from .list_available_telemetry_devices import ListAvailableTelemetryDevices
from .list_medication_suppliers import ListMedicationSuppliers
from .list_missing_telemetry_upload import ListMissingTelemetryUpload
from .list_patient_appointments import ListPatientAppointments
from .list_patient_medical_records import ListPatientMedicalRecords
from .list_telemetry_uploads import ListTelemetryUploads
from .query_patient_candidates import QueryPatientCandidates

ALL_TOOLS = [
    QueryPatientCandidates,
    GetPatientDetailsComplete,
    ListPatientAppointments,
    GetAppointmentDetails,
    ListPatientMedicalRecords,
    GetMedicalRecord,
    ListAvailableProviders,
    GetProviderDetails,
    CheckProviderAppointmentSlot,
    ListMedicationSuppliers,
    GetRegimenOptions,
    CheckDrugInteractions,
    ListTelemetryUploads,
    ListMissingTelemetryUpload,
    ListAssignedTelemetryDevices,
    ListAvailableTelemetryDevices,
    Think,
]

__all__ = ["ALL_TOOLS"]
