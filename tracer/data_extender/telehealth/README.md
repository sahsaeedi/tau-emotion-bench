# Telehealth data extender

Adds patients (some in family groups), providers and telemetry devices to the
telehealth database, then has an LLM write scenario text (appointments, medical
records) for them. Settings are in `extend_telehealth_config.json`; command-line
flags override them. See [DB extender](../../README.md#db-extender-optional)
for how to run it and install its output.

| File | Stage |
|---|---|
| `extend_telehealth.py` | Runs the whole pipeline |
| `master_data_extender.py` | 1. New patients, providers and devices (deterministic, seeded) |
| `pack_telehealth_seed.py` | 2. Merges new records into a validated dataset |
| `scenario_blueprints.py` | 3. Scenario blueprints for the new records (deterministic) |
| `thinking_fill_blueprints.py`, `telehealth_seed_prompts.py` | 4. LLM fills in the scenario text |
| `common.py` | Loading, validation and writing shared by the stages |

Each stage file can also be run on its own (`python -m data_extender.telehealth.<stage> --help`).
Providers, medication suppliers and drug interactions are shared by both splits, so
new providers land in the shared `providers.json`: after installing the output,
export both splits' databases.
