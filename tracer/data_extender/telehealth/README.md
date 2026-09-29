# Telehealth data extender

Adds patients (some in family groups), providers and telemetry devices to the
telehealth database, then has an LLM write scenario text for them. Settings are in
`extend_telehealth_config.json`. See [Adding users to a database](../../README.md#adding-users-to-a-database)
for how to run it and install its output.

| File | Stage |
|---|---|
| `extend_telehealth.py` | Runs the whole pipeline |
| `master_data_extender.py` | 1. New patients, providers and devices (deterministic) |
| `pack_telehealth_seed.py` | 2. Merges new records into a validated dataset |
| `scenario_blueprints.py` | 3. Scenario blueprints for the new records (deterministic) |
| `generate_telehealth_seed.py`, `thinking_fill_blueprints.py`, `telehealth_seed_prompts.py` | 4. LLM fills in the scenario text |
| `common.py` | Loading, validation and writing shared by the stages |
