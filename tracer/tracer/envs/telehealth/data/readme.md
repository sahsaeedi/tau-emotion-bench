# Telehealth Mock Data

Shared by both splits (at the top of `data/`):
- `providers.json`: healthcare providers, their specialties, schedules, and availability
- `medication_suppliers.json`: supplier brands and prices for each medication
- `drug_interactions.json`: interaction rules (severity, required action) for high-risk medications

Per split (in `test/` and `train/`):
- `patients.json`: patients with their demographics, medical history, and insurance information
- `appointments.json`: telehealth appointments that can be scheduled, modified, or cancelled
- `medical_records.json`: consultation notes, prescriptions, and test results
- `telemetry_inventory.json`: telemetry devices, their status, and who they are assigned to
- `telemetry_uploads.json`: readings uploaded from those devices
- `regimen_plans.json`: patients' current medication regimens

`load_data(split)` in `__init__.py` merges the shared files with one split's files.
Check `../tools` for mock APIs on top of this data.

To add patients, providers and devices, see the telehealth data extender
([`data_extender/telehealth/README.md`](../../../../data_extender/telehealth/README.md)).
