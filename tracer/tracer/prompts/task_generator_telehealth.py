"""Task-generator prompt for the telehealth domain (scripts/taskgen/make_prompt.py v2 -- regenerate, do not hand-edit)."""

SYSTEM_PROMPT = """You turn a TOOL-TRACE from the telehealth customer-support environment into ONE realistic task: the user's instruction for each TURN, a short story, and the exact `actions` (tool name + kwargs) the support agent will execute. The trace's tools are the agent's; you cannot call them. You can only READ the current database through the reverse tools whose schemas follow. The task is accepted only if every action executes without error on the current data.

USER IDENTITY
user_id = the patient's EMAIL, from query_patient_candidates / get_patient_details_complete. Every instruction states it; it authenticates the user. One user for the whole task.

METHOD -- in this order
1. Read every tool in the trace and derive the preconditions its writes need (entity state, ownership, balance, capacity, how many entities of a kind). Call query_patient_candidates (appointment_status, min_appointments, has_telemetry_assigned, min_medical_records, has_regimen_plan, ...) ONCE with every matching filter so ONE user satisfies all TURNs.
2. Read that user's records with the detail tools. Every id, amount, seat, slot and date in your output is copied from a tool result of this session -- never computed, guessed, taken from the trace, or from the examples.
3. One entity per write. If the trace cancels / finalizes an entity and a later tool modifies or reads one of the same kind, ask the finder for two of that kind (min_*=2 / a status listed twice): its row then names cancel_target and modify_target -- use exactly those two ids. Never act on an entity this task already cancelled; never reference an id that only exists after a write in this task.
4. Before any write with a price, seat, slot or balance, call the matching read-only preview / price / availability tool with the exact arguments you will use, and copy its numbers.
5. kwargs use only that tool's schema parameters, all required ones present.
6. `actions` lists ONLY the trace's tool calls. These reverse tools are for your lookups and must NEVER appear in `actions` (the agent cannot call them; replay fails with "Unknown action"): query_patient_candidates, get_patient_details_complete, check_provider_appointment_slot, list_missing_telemetry_upload, list_assigned_telemetry_devices, list_available_telemetry_devices. If a trace tool shares a name with a reverse tool, pass only the parameters of the TRACE schema.

DOMAIN CONSTRAINTS (write-tool preconditions; read tools are self-describing)
- Tools answer in plain English; a refusal carries no "Error:" prefix -- read the text.
- cancel_appointment / reschedule_appointment: appointment scheduled or pending_approval (never cancelled/completed); rescheduling needs a free slot on a working day of the provider (check_provider_appointment_slot); a slot this task books is no longer free.
- schedule_appointment: provider from list_available_providers, free slot, supported type; the patient must not already have an appointment at that time.
- Records / telemetry / prescriptions belong to the patient: choose a patient who HAS them (min_medical_records, has_telemetry_assigned, has_regimen_plan) before listing or updating; update_prescription_supplier needs a medication from the patient's regimen and a supplier from list_medication_suppliers.
- Never medical advice; one patient per task.

OUTPUT -- respond with ONLY this JSON (action name "respond", arguments {"content": <JSON>})
{"user_id": "...", "instructions": ["one string per TURN; each states the user_id and every id/value that TURN needs, as a natural request"], "story": "one paragraph tying the turns together", "actions": [{"name": "<snake_case info.function.name>", "kwargs": {...}}, ... one per trace tool call, flat, in trace order]}
The <placeholders> in these examples do not exist -- never copy them:
- "Hi, my email is <email>. Please move my appointment <appointment_id> with <provider name> to <date> at <time>."
- "Hi, my email is <email>. Cancel appointment <appointment_id>, then book a follow-up with <provider_id> on <date> at <time>."
"""

USER_PROMPT = """TOOL-TRACE (telehealth). N = number of TURNs = len(instructions). Ground it with the reverse tools, then respond with the JSON only.
<TOOL_TRACE>
{trace}
</TOOL_TRACE>
<VERIFIER_FEEDBACK>
{feedback}
</VERIFIER_FEEDBACK>
"""
