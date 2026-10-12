# TRACER

TRACER generates the benchmark's tasks. It turns each domain's tools into tasks
with verified ground-truth actions and an emotion for the simulated user, in the
format the benchmark reads (`../data/tau_emotion/domains/<domain>/tasks*.json`).
It covers all 10 domains: airline, retail, telecom, telehealth, bank, basketball,
movie, restaurant, school and travel. The last six build on the ToolScale domains
of [ToolOrchestra](https://github.com/NVlabs/ToolOrchestra) (see
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)).

Tasks are generated and verified in TRACER's own environments,
`tracer/envs/<domain>/`: the tools, the policy (`wiki.md`) and the database of each
domain, following τ-bench's conventions. The benchmark's tools in
`../src/tau_emotion/domains/` reproduce these environments, with the same tools in
every domain, so a task that is solvable here is solvable in the benchmark.

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

Optionally, the [DB extender](#db-extender-optional) adds synthetic users to
the telecom and telehealth databases before step 3, and `export_db.py` writes a domain's database
into the benchmark.

## Layout

| Path | What it is |
|---|---|
| `graph_builder.py` | Step 1: builds a tool graph per domain with an LLM |
| `build_trace.py`, `trace_utils.py` | Step 2: samples tool-call traces from a graph |
| `tracer/` | Step 3: the task generator package: `generator.py`, agents, prompts, and `envs/<domain>/` with each domain's tools, reverse tools, policy (`wiki.md`) and databases |
| `scripts/taskgen/` | Step 3 helpers: the filter for valid tasks, and the prompt builder |
| `evaluator/` | Step 4: the four-criteria quality audit |
| `emotions/` | Step 5: builds the emotion persona bank |
| `emotion_analysis/` | Step 6: assigns an emotion to each task, and plots the emotion space |
| `export_tasks.py` | Step 7: writes tasks into the benchmark |
| `data_extender/` | Adds synthetic customers to the telecom and telehealth databases ([DB extender](#db-extender-optional)) |
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
OPENAI_API_KEY=...        # OpenAI models, embeddings, the emotion bank (steps 5-6)
HOSTED_VLLM_API_KEY=...   # --generator-model-provider / --eval-model-provider hosted_vllm
VLLM_API_KEY=...          # graph_builder.py --provider vllm
OPENAI_COMPATIBLE_API_KEY=...  # the telehealth extender with --provider openai-compatible
```

Every LLM step also runs on an OpenAI-compatible
server (vLLM or a hosted provider):
`graph_builder.py --provider vllm --base-url <url>`, and `--api-base <url>` with
`--generator-model-provider openai` or `--eval-model-provider openai` (and
`OPENAI_API_KEY` set to that server's key) for the generator and the evaluator.

The generator's and the evaluator's agents cap each LLM reply at 4096 tokens, so a
model that keeps repeating its Thought/Action blocks does not run into the timeout.
Set `TRACER_MAX_TOKENS` to change the cap (`0` removes it), e.g. for a reasoning
model whose reasoning tokens count toward it.
The emotion bank (step 5) uses `run --api-base <url>` in place of the Batch API,
and step 6 takes the embedding server's URL in its config.

## Pipeline

Examples build `bank` test tasks. For train, use `--split train` and `train` in the paths.

### DB extender (optional)

Adds synthetic users to telecom or telehealth. Run before step 3.

```bash
# telecom
python -m data_extender.telecom 200 --split test
python -m data_extender.telecom.telecom_stats \
  --path data_extender/generated_telecom \
  --split test
cp data_extender/generated_telecom/test/*.json tracer/envs/telecom/data/test/

# telehealth (LLM writes scenario text; settings in the config)
python -m data_extender.telehealth.extend_telehealth \
  --config data_extender/telehealth/extend_telehealth_config.json \
  --split test
cp -r data_extender/generated_telehealth/* tracer/envs/telehealth/data/

# then copy the database into the benchmark (telehealth: both splits)
python export_db.py \
  --domain telecom \
  --split test \
  --dry-run
```

- Output goes to `data_extender/generated_*` first; check it before `cp`.
- Same `--seed` (default 1337), same records; the telehealth scenario text comes
  from the LLM, so it varies.
- Only adds records, so existing tasks keep working. One exception: telehealth's
  new appointments take free provider slots, from two weeks after the latest
  existing appointment; a task that books one of those slots no longer can.
- Telehealth's new providers go into `providers.json`, which both splits share.
- `export_db.py` writes `../data/tau_emotion/domains/<domain>/db.json` (test) or
  `db_train.json` (train): `--dry-run` lists the changes, `--overwrite` replaces
  the file, `--output <path>` writes elsewhere. Skip it and the benchmark lacks the
  new users.
- OpenAI-compatible server: `--provider openai-compatible --base-api <url> --model <name>`,
  with `OPENAI_COMPATIBLE_API_KEY` in `.env`.

### Step 1: Tool graphs

One LLM pass per domain decides which tools can follow which.

```bash
python graph_builder.py \
  --provider openai \
  --model gpt-5.2 \
  --temperature 0.0 \
  --domains airline retail telecom telehealth bank basketball movie restaurant school travel
```

Output: `output/graphs/<provider>_<model>/<domain>_adjacency_matrix_<temperature>.json`

- One LLM call per tool; `think` and `calculate` are left out of the graph.
- `--provider openai` takes `gpt-4.1`, `gpt-4o`, `gpt-5`, `gpt-5.1` or `gpt-5.2`.
  For an OpenAI-compatible server: `--provider vllm --base-url <url> --model <name>`
  (key in `VLLM_API_KEY`).
- Without `--domains` it builds airline, retail, telecom and telehealth only.

### Step 2: Traces

Random walks over one domain's graph give tool-call sequences.

```bash
python build_trace.py \
  --graph_json_path output/graphs/openai_gpt-5.2/bank_adjacency_matrix_0.0.json \
  --num-traces 1000 \
  --walk-steps 2 3 4 \
  --walk-steps-dist 0.5 0.3 0.2 \
  --num-intents 1 2 3 \
  --num-intents-dist 0.6 0.3 0.1 \
  --random-seed 10
```

Output: `output/traces/<graph name>_traces.json`, and the settings in
`<graph name>_traces_config.json`. Duplicate traces are dropped, so there can be
fewer than `--num-traces`. The file is named after the graph file only, so graphs of
one domain from two models write the same traces file.

### Step 3: Tasks

Writes and verifies a task per trace. Once per domain; always pass `--split` (default `train`).
Each task takes four LLM passes: a ReAct agent reads the split's database through the
domain's reverse tools and writes the task, then a pass writes the user's `feeling`,
one rewrites the instructions into a single `preference_instruction`, and a checker
replays the ground-truth actions in the domain's environment
(`task_checker_action_replay`) and labels the task `solvable` and `in_domain`.
Expect several minutes per task.

```bash
python -m tracer.generator \
  --env bank \
  --split test \
  --trace-path output/traces/bank_adjacency_matrix_0.0_traces.json \
  --output-path output/tasks/test/bank_test_tasks.json \
  --generator-model-provider openai \
  --generator-model gpt-5.2 \
  --tasks-per-trace 2
```

Collect valid tasks:

```bash
python scripts/taskgen/filter_valid_tasks.py \
  --split test \
  --domains bank
```

Output: `output/tasks/test_valid/bank_test_tasks_valid.json`. A task is valid when
it has ground-truth actions and a `preference_instruction`, every action replays
without an error, and the checker marked it solvable and not out of domain.

### Step 4: Quality audit

Score tasks on the [four criteria](#quality-criteria).

```bash
python -m evaluator.runner \
  --domain bank \
  --input-path output/tasks/test_valid/bank_test_tasks_valid.json \
  --eval-model gpt-4.1 \
  --eval-model-provider openai \
  --workers 8
```

Output: `output/evaluations/bank_test_eval.json`. Re-running resumes: evaluated
tasks are skipped, and tasks left inconclusive are retried.
`--config evaluator/config/eval_config_<domain>.json` sets a domain's test paths.

Or all domains at once:

```bash
python -m evaluator.multi_runner \
  --domains all \
  --split test \
  --eval-model gpt-4.1 \
  --eval-model-provider openai
```

Report:

```bash
python -m evaluator.orchestrator \
  --eval-path output/evaluations/bank_test_eval.json \
  --markdown-out output/evaluations/bank_test_report.md
```

Output: `output/evaluations/bank_test_eval_summary.json` and the Markdown report.
Add `--eval-model <model>` to have an LLM group the failure reasons into themes.

Passed tasks:

```bash
python -m evaluator.get_passed_tasks \
  --eval-path output/evaluations/bank_test_eval.json \
  --input-path output/tasks/test_valid/bank_test_tasks_valid.json \
  --output-path output/evaluations/bank_test_passed_tasks.json
```

Output: the full records of the tasks that passed, the input of step 6. Re-running
appends only newly passed tasks (tracked in `.passed_tasks_registry.json`).

### Step 5: Emotion persona bank

Run once for all domains; independent of steps 1–4. With the OpenAI Batch API
(up to 24 h):

```bash
python emotions/build_emotion_persona_instructions_batch.py submit
python emotions/build_emotion_persona_instructions_batch.py status
python emotions/build_emotion_persona_instructions_batch.py wait-download
```

Or directly, on an OpenAI-compatible server without the Batch API:

```bash
python emotions/build_emotion_persona_instructions_batch.py run \
  --api-base <url> \
  --model <model> \
  --workers 16
```

Output: `emotions/output/emotion_persona_instructions.json`. Settings (model,
variants per spec, `max_specs` for a test run) are in `emotions/config.json`; see
[`emotions/README.md`](emotions/README.md).

### Step 6: Emotions for the tasks

Set `inputs.task_paths` in `emotion_analysis/config.json` to the passed-tasks file
first, and `embedding_model` to your embedding model (`model`, `api_base`; see
[`emotion_analysis/README.md`](emotion_analysis/README.md)).

```bash
python emotion_analysis/run_all.py --config emotion_analysis/config.json
```

Output: `output/evaluations/bank_test_passed_tasks_with_emotion_predictions.json`,
plus the trained classifier and t-SNE plots under `emotion_analysis/output/`.

### Step 7: Export into the benchmark

From the repo root, with the benchmark's environment.

```bash
cd ..
deactivate && source .venv/bin/activate
python tracer/export_tasks.py \
  tracer/output/evaluations/bank_test_passed_tasks_with_emotion_predictions.json \
  --domain bank \
  --split test \
  --dry-run
```

Then `--overwrite` to write `data/tau_emotion/domains/bank/tasks.json`
(`tasks_train.json` for `--split train`), or `--output <path>` to write elsewhere.
Rows without a `user_id` or an emotion are skipped. Before writing, every task is
checked against the benchmark's `Task` schema and the domain's tool names.

## Quality criteria

`evaluator/` scores every generated task and passes it only if all four hold.
Criteria 1 and 2 look at the rewritten `preference_instruction`. Criteria 3 and 4
are always decided by the judge LLM, which sees the ground-truth actions together
with the generator's replay of them (criterion 3) or its `in_domain` label and the
domain's rules (criterion 4). A task the judge gives no verdict on (an error or a
malformed answer) is inconclusive: it does not pass, and a re-run retries it.

| # | Criterion | Violated when |
|---|---|---|
| 1 | Goal-oriented | The instruction is procedural: the agent would have to draw information out of the user before it could act |
| 2 | Template | The instruction lacks a concrete tool-calling task or a user preference |
| 3 | Solvable by ground truth | The judge finds that the ground-truth actions, and their replay, do not accomplish the instruction |
| 4 | No domain violation | The task is out of domain, but the ground truth acts instead of transferring to a human agent |

Every domain has a transfer tool (`transfer_to_human_support` in telehealth,
`transfer_to_human_agents` elsewhere), and calling it ends the conversation, in
TRACER and in the benchmark alike.

## Task generation helpers

`scripts/taskgen/` holds two helpers for step 3:

- `filter_valid_tasks.py --split <split>`: collects the valid tasks of every domain
  (or of `--domains ...`) from `output/tasks/<split>/<domain>_<split>_tasks*.json`
  into `output/tasks/<split>_valid/`. Name the generator's output that way so it is
  found. An existing output file is only replaced with `--overwrite`.
- `make_prompt.py`: regenerates `tracer/prompts/task_generator_<domain>.py`
  (`--all`, or one domain). Edit the prompts there, not in the generated files.

Generator flags:

| Flag | Default | Purpose |
|---|---|---|
| `--env` | `airline` | Domain |
| `--split` | `train` | `train` or `test` |
| `--trace-path` | airline traces | Traces file from step 2 |
| `--output-path` | next to the traces | Use `output/tasks/<split>/<domain>_<split>_tasks.json` |
| `--generator-model-provider` | `openai` | LLM provider (a LiteLLM provider name) |
| `--generator-model` | `gpt-5.2` | LLM model, used by all four passes |
| `--generator-temperature` | `0.2` | Temperature of the task writer (`gpt-5*`: 1) |
| `--feeling-temperature` | `0.9` | Temperature of the feeling pass |
| `--api-base` | — | OpenAI-compatible server URL |
| `--tasks-per-trace` | `3` | Tasks per trace |
| `--start-index` / `--end-index` | all | Trace range |
| `--task-ids` | — | Only these trace indices |
| `--config` | — | JSON file of flag defaults (keys are the flag names with `_`) |
| `--debug` | off | Every agent step on stdout |
| `--print-thoughts` | off | With `--debug`, also the agent's thoughts |

Re-running the same command resumes. For several domains, loop:

```bash
for d in bank movie; do
  python -m tracer.generator \
    --env $d \
    --split test \
    --trace-path output/traces/${d}_adjacency_matrix_0.0_traces.json \
    --output-path output/tasks/test/${d}_test_tasks.json \
    --tasks-per-trace 2
done
```
