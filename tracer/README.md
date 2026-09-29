# TRACER

TRACER generates the benchmark's tasks. It turns each domain's tools into tasks
with verified ground-truth actions and an emotion for the simulated user, in the
format the benchmark reads (`../data/tau_emotion/domains/<domain>/tasks*.json`).
It covers all 10 domains: airline, retail, telecom, telehealth, bank, basketball,
movie, restaurant, school and travel.

Tasks are generated and verified in TRACER's own environments,
`tracer/envs/<domain>/`: the tools, the policy (`wiki.md`) and the database of each
domain, following τ-bench's conventions. The benchmark's tools in
`../src/tau_emotion/domains/` reproduce these environments, so a task that is
solvable here is solvable in the benchmark.

No generated outputs ship with it: no tool graphs, traces, emotion bank or trained
models. Each run creates its own under `output/`, `emotions/output/` and
`emotion_analysis/output/`, which git ignores.

## Overview

```
tool graph ─► traces ─► tasks ─► quality ─► emotions ─► export ─► benchmark
                        (verified) audit
```

| Step | What happens |
|---|---|
| 1. Tool graph | An LLM decides which tools can follow which, and which can start a conversation |
| 2. Traces | Random walks over the graph give tool-call sequences |
| 3. Tasks | An LLM writes a task for each trace; its ground-truth actions are replayed in the domain's environment, and a checker confirms it is solvable and in-domain |
| 4. Quality evaluation | Four checks per task ([below](#quality-criteria)); only tasks that pass all four move on |
| 5. Emotion bank | Emotion personas from the Atlas of Emotions hierarchy, built once for all domains |
| 6. Emotions for tasks | Each task gets the persona that fits it best |
| 7. Export | Tasks are converted into the benchmark's task files |

Separately, the [data extenders](#adding-users-to-a-database) add synthetic users to
the telecom and telehealth databases, and `export_db.py` writes a domain's database
into the benchmark.

## Layout

| Path | What it is |
|---|---|
| `graph_builder.py` | Step 1: builds a tool graph per domain with an LLM |
| `build_trace.py`, `trace_utils.py` | Step 2: samples tool-call traces from a graph |
| `tracer/` | Step 3: the task generator package: `generator.py`, agents, prompts, and `envs/<domain>/` with each domain's tools, reverse tools, policy (`wiki.md`) and databases |
| `scripts/taskgen/` | Batch drivers for step 3, a filter for valid tasks, and the generator's shared config |
| `evaluator/` | Step 4: the four-criteria quality audit |
| `emotions/` | Step 5: builds the emotion persona bank |
| `emotion_analysis/` | Step 6: assigns an emotion to each task, and plots the emotion space |
| `export_to_tau2.py` | Step 7: writes tasks into the benchmark |
| `data_extender/` | Adds synthetic customers to the telecom and telehealth databases ([below](#adding-users-to-a-database)) |
| `export_db.py` | Writes a domain's TRACER database into the benchmark's `db.json` / `db_train.json` |

Each domain's database is in `tracer/envs/<domain>/data/`: catalog files shared by
both splits at the top, and each split's own records (users, orders, ...) in
`test/` and `train/`. Merged, they are identical to the benchmark's `db.json` and
`db_train.json`, so generated tasks refer to records the benchmark has. Pick a
split with `--split`.

## Setup

TRACER has its own dependencies. Use a separate environment (Python 3.10+), and run
every command from this folder:

```bash
cd tracer
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Put a `.env` in `tracer/` with the keys you need:

```bash
OPENAI_API_KEY=...        # OpenAI models, embeddings, the emotion Batch API job
HOSTED_VLLM_API_KEY=...   # configs that use the hosted_vllm provider
VLLM_API_KEY=...          # graph_builder.py --provider vllm
OPENAI_COMPATIBLE_API_KEY=...  # the telehealth extender with --provider openai-compatible
```

Every LLM step also runs on an OpenAI-compatible server (vLLM or a hosted provider):
`graph_builder.py --provider vllm --base-url <url>`, and `--api-base <url>` with
`--generator-model-provider openai` or `--eval-model-provider openai` (and
`OPENAI_API_KEY` set to that server's key) for the generator and the evaluator.

## Pipeline

The example builds `bank` test tasks. Use `--split train` throughout to build train
tasks against the train database instead.

```bash
# 1. Tool graphs: one LLM pass per domain
#    -> output/graphs/<provider>_<model>/<domain>_adjacency_matrix_<temperature>.json
python graph_builder.py --provider openai --model gpt-5.2 --temperature 0.0 \
  --domains airline retail telecom telehealth bank basketball movie restaurant school travel

# 2. Traces: random walks over one graph
#    -> output/traces/<graph name>_traces.json
python build_trace.py \
  --graph_json_path output/graphs/openai_gpt-5.2/bank_adjacency_matrix_0.0.json \
  --num-traces 1000 --walk-steps 2 3 4 --walk-steps-dist 0.5 0.3 0.2 \
  --num-intents 1 2 3 --num-intents-dist 0.6 0.3 0.1 --random-seed 10

# 3. Tasks: generate, replay the ground-truth actions, check solvability (resumable)
python -m tracer.generator --env bank --split test \
  --trace-path output/traces/bank_adjacency_matrix_0.0_traces.json \
  --output-path output/tasks/test/bank_test_tasks.json \
  --generator-model-provider openai --generator-model gpt-5.2 --tasks-per-trace 2
#    or with the shared settings in scripts/taskgen/configs/generator.json:
#      python -m tracer.generator --config scripts/taskgen/configs/generator.json --env bank \
#        --trace-path output/traces/bank_adjacency_matrix_0.0_traces.json \
#        --output-path output/tasks/test/bank_test_tasks.json
#    or several domains in sequence: bash scripts/taskgen/run_all.sh bank movie
python scripts/taskgen/filter_valid_tasks.py --split test
#    -> output/tasks/test_valid/bank_test_tasks_valid.json

# 4. Quality audit (four criteria below), a summary, and the tasks that passed
python -m evaluator.runner --domain bank \
  --input-path output/tasks/test_valid/bank_test_tasks_valid.json \
  --eval-model gpt-4.1 --eval-model-provider openai --workers 8
#    -> output/evaluations/bank_test_eval.json (resumable)
#    or every domain with valid tasks, one task per domain in turn:
#      python -m evaluator.multi_runner --domains all --split test \
#        --eval-model gpt-4.1 --eval-model-provider openai
#      (evaluator/config/eval_config_<domain>.json hold the same settings per domain)
python -m evaluator.orchestrator \
  --eval-path output/evaluations/bank_test_eval.json \
  --markdown-out output/evaluations/bank_test_report.md
python -m evaluator.get_passed_tasks \
  --eval-path output/evaluations/bank_test_eval.json \
  --input-path output/tasks/test_valid/bank_test_tasks_valid.json \
  --output-path output/evaluations/bank_test_passed_tasks.json

# 5. Emotion persona bank: an OpenAI Batch API job (up to 24 h), once for all domains
python emotions/build_emotion_persona_instructions_batch.py submit
python emotions/build_emotion_persona_instructions_batch.py status
python emotions/build_emotion_persona_instructions_batch.py wait-download
#    -> emotions/output/emotion_persona_instructions.json

# 6. Emotions for the tasks. First set inputs.task_paths in emotion_analysis/config.json
#    to ["output/evaluations/bank_test_passed_tasks.json"], then:
python emotion_analysis/run_all.py --config emotion_analysis/config.json
#    -> output/evaluations/bank_test_passed_tasks_with_emotion_predictions.json,
#       plus the trained encoder and emotion-space plots under emotion_analysis/output/

# 7. Export into the benchmark. Run it with the benchmark's environment, so each task
#    is checked against the benchmark's task schema and the domain's tools:
cd ..
uv run python tracer/export_to_tau2.py \
  tracer/output/evaluations/bank_test_passed_tasks_with_emotion_predictions.json \
  --domain bank --split test --dry-run
#    then run it again with --overwrite to replace data/tau_emotion/domains/bank/tasks.json
#    (--split train writes tasks_train.json; --output <path> writes somewhere else)
```

Step 5 is independent of steps 1–4 and only needs to run once. Step 6 needs its
output.

The export skips failed rows, rows without a `user_id`, and rows without an emotion
from step 6. It numbers the tasks `<domain>_<split>_0000` onward.

## Adding users to a database

The data extenders grow a domain's database with synthetic records, so there are
more users for new tasks to be about. They read one split of
`tracer/envs/<domain>/data/` and write an output directory with the same layout,
holding the existing records plus the new ones, so you can review it and copy it
over the original.

```bash
# Telecom: add 200 customers, with billing and support tickets, to the test split.
# Deterministic (Faker, --seed); the ranges and weights are in
# data_extender/telecom/telecom_config.yaml.
python -m data_extender.telecom 200 --split test
#    -> data_extender/generated_telecom/test/{customers,billing,support_tickets}.json
python -m data_extender.telecom.telecom_stats --path data_extender/generated_telecom --split test
cp data_extender/generated_telecom/test/*.json tracer/envs/telecom/data/test/

# Telehealth: new patients (some in family groups), providers and telemetry devices
# are generated deterministically; an LLM then writes the scenario text for them.
# Counts, model and output paths are in the config; any flag overrides it.
python -m data_extender.telehealth.extend_telehealth \
  --config data_extender/telehealth/extend_telehealth_config.json --split test
#    for an OpenAI-compatible server (key from OPENAI_COMPATIBLE_API_KEY), add
#    --provider openai-compatible --base-api <url> --model <name> --enable-thinking false
#    -> data_extender/generated_telehealth/ (providers.json and the other catalog
#       files at the top, the split's files in test/)
cp -r data_extender/generated_telehealth/* tracer/envs/telehealth/data/
```

New ids, account numbers and ticket numbers continue after the existing ones.
Telehealth providers are catalog records, so new ones appear in both splits.

Then write the database into the benchmark:

```bash
python export_db.py --domain telecom --split test --dry-run
#    then run it again with --overwrite to replace ../data/tau_emotion/domains/telecom/db.json
#    (--split train writes db_train.json)
```

Existing tasks keep working: records are only added, never changed.

## Quality criteria

`evaluator/` scores every generated task and passes it only if all four hold.
Criteria 1 and 2 look at the rewritten `preference_instruction`. Criteria 3 and 4
use deterministic checks first and fall back to the judge LLM only when those are
inconclusive.

| # | Criterion | Violated when |
|---|---|---|
| 1 | Goal-oriented | The instruction is procedural: the agent would have to draw information out of the user before it could act |
| 2 | Template | The instruction lacks a concrete tool-calling task or a user preference |
| 3 | Solvable by ground truth | The ground-truth actions fail in the environment, or `solvable` is `false` |
| 4 | No domain violation | The task is out of domain, but the ground truth acts instead of transferring to a human agent |

## Batch generation

`scripts/taskgen/` runs step 3 at scale:

- `configs/generator.json`: the settings every domain shares: split, temperatures,
  `tasks_per_trace` and the trace range. The model defaults to the generator's own
  (`openai`, `gpt-5.2`); to use another, add `generator_model_provider`,
  `generator_model` and, for an OpenAI-compatible server, `api_base` to this file, or
  pass `--generator-model-provider`, `--generator-model` and `--api-base`. Any flag on
  the command line overrides the file.
- `run_all.sh <domains...>`: runs the domains one after another; resumable, and
  meant to run inside `tmux`. `run_window.sh <domain> <log_dir>` runs one domain, as
  one tmux window.
- `status.sh`: one-screen progress.
- `make_prompt.py`: regenerates `tracer/prompts/task_generator_<domain>.py`.

The drivers find each domain's files by name (see `common.sh`): the traces file is
the one file in `output/traces/` named `<domain>_*traces.json`, and tasks go to
`output/tasks/<split>/<domain>_<split>_tasks.json`. Change the split, config or
traces folder with environment variables:

```bash
SPLIT=train TRACE_DIR=output/traces_final bash scripts/taskgen/run_all.sh bank movie
```
