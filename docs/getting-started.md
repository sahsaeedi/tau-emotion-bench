# Getting Started

This guide walks you through installing τ-emotion-bench, configuring API keys, and running your first evaluation.

## Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/) — Python package and project manager
- Python 3.12+ (uv will download it automatically if not present)

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/sahsaeedi/tau-emotion-bench.git
cd tau-emotion-bench
```

### 2. Install τ-emotion-bench

```bash
uv sync                        # core: all 10 domains (+ the mock test fixture)
```

This creates a virtual environment, installs core dependencies from the lockfile, and enables the `tau-emotion` command. The Python version is pinned via `.python-version` (3.12) — uv will download it automatically if needed.

In Python, the package is imported as `tau_emotion` (for example `from tau_emotion import TextRunConfig`).

#### Optional extras

Install the extras you need:

```bash
uv sync --extra dev            # + pytest, pytest-xdist, ruff, pre-commit (required for contributing)
uv sync --all-extras           # everything
```

> **Note:** If you install without `-e` mode (e.g., `uv pip install .`), you'll need to set the `TAU_EMOTION_DATA_DIR` environment variable to point to your data directory:
> ```bash
> export TAU_EMOTION_DATA_DIR=/path/to/tau-emotion-bench/data
> ```

### 3. Verify your installation

```bash
uv run tau-emotion check-data
```

This prints the data directory the package will use and checks that it exists.

## Setting Up API Keys

We use [LiteLLM](https://github.com/BerriAI/litellm) to manage LLM APIs, so you can use any LLM provider supported by LiteLLM.

Copy `.env.example` as `.env` and edit it to include your API keys:

```bash
cp .env.example .env
```

Set `OPENAI_API_KEY` (and `ANTHROPIC_API_KEY` for Claude models). Model names litellm doesn't know are sent to `OPENAI_API_BASE`, so add `OPENAI_API_BASE=<url>` to use an OpenAI-compatible server, or pass `--agent-api-base` / `--user-api-base` per run.

## The Benchmark in Brief

- **Domains (10):** `airline`, `retail`, `telecom`, `telehealth`, `bank`, `basketball`, `movie`, `restaurant`, `school`, `travel`. The `mock` domain is a small fixture used only by the tests.
- **Test tasks:** 580 in `data/tau_emotion/domains/<domain>/tasks.json` (70 each for airline, retail, telecom and telehealth; 50 each for the others). They run against `db.json`. The `base` split (the default) and the `test` split are this same set.
- **Train tasks:** 2,723 in `tasks_train.json`, selected with `--task-split-name train`. They run against `db_train.json`, which is loaded automatically. They are the tasks a Qwen3.8-27B (thinking) agent solved with reward 1; see [Train tasks](train_tasks.md).
- **Emotion:** every task's `user_scenario` has an `emotion_instruction` the user simulator acts out, and `emotion_metadata` labels used only for analysis.
- **Scoring:** all 10 domains score with `reward_basis: [DB, COMMUNICATE]`. A run the simulated user abandons with `###UNSATISFIED###` gets reward -1. See [Task Schema & Evaluation](evaluation.md).

## Running Your First Evaluation

### Standard text-based evaluation (half-duplex)

```bash
tau-emotion run --domain airline --agent-llm gpt-4.1 --user-llm gpt-4.1 \
  --num-trials 1 --num-tasks 5
```

Leave out `--user-llm` to use the benchmark's user simulator (`qwen3-235b-a22b-instruct-2507` at temperature 0.7). Reported scores use it, so use it when comparing against them. OpenAI and Anthropic don't serve it, so set `OPENAI_API_BASE` (or `--user-api-base`) to an OpenAI-compatible server that does, such as your own vLLM server or a hosted provider.

To run specific tasks, pass their ids:

```bash
tau-emotion run --domain retail --task-ids retail_test_0000 retail_test_0003 \
  --agent-llm gpt-4.1 --user-llm gpt-4.1
```

Results are saved to `data/simulations/<domain>/<agent model>/results.json` (or `data/simulations/<save_to>/results.json` with `--save-to`). Running the same command again resumes that run.

## Simulation Output Structure

Results are stored in one of two formats:

### Monolithic JSON (default)

Runs produce a single file containing all data:

```
data/simulations/<run_name>/
└── results.json             # Metadata, tasks, and all simulation data
```

### Directory-based format

The directory-based format splits simulation data into individual files for efficient checkpointing and streaming:

```
data/simulations/<run_name>/
├── results.json                        # Metadata and task definitions only
├── simulations/                        # Individual simulation data files
│   ├── sim_0.json
│   ├── sim_1.json
│   └── ...
└── artifacts/                          # Runtime artifacts (with --verbose-logs)
    └── task_<task_id>/
        └── sim_<uuid>/
            ├── sim_status.json         # Simulation status
            ├── task.log                # Per-task log
            └── llm_debug/
                └── *.json              # LLM call logs
```

### Format conversion

You can convert between formats using `tau-emotion convert-results`:

```bash
# Convert a monolithic JSON to directory format
tau-emotion convert-results data/simulations/my_run --to dir

# Convert a directory format back to monolithic JSON
tau-emotion convert-results data/simulations/my_run --to json
```

Both formats are fully supported by `Results.load()`, which auto-detects the format on disk.

## Viewing Results

```bash
tau-emotion view
```

This allows you to browse simulation files, view agent performance metrics, inspect individual simulations, and view task details.

## Configuration

The framework is configured via [`src/tau_emotion/config.py`](../src/tau_emotion/config.py). Besides the CLI defaults, it holds the `TAU_BENCH_*` switches that make runs follow τ-bench's conventions (all on by default; see [Harness conventions](evaluation.md#how-a-conversation-runs)).

### LLM Call Caching

LLM call caching is disabled by default. To enable it:

1. Install the `redis` Python package: `uv pip install redis`
2. Make sure a Redis server is running
3. Update the redis config in `config.py` if necessary
4. Set `LLM_CACHE_ENABLED` to `True` in `config.py`

## Cleanup

To remove all generated files and the virtual environment:

```bash
make clean
```

## Next Steps

- [CLI Reference](cli-reference.md) — all `tau-emotion` commands and options
- [Running Simulations](running_simulations.md) — the Python runner API
- [Task Schema & Evaluation](evaluation.md) — how a task is scored, what `actions`/`communicate_info`/`reward_basis` actually do
- [Train tasks](train_tasks.md) — where the train tasks come from
- [Agent Developer Guide](../src/tau_emotion/agent/README.md) — build and evaluate your own agent
- [Domain Documentation](../src/tau_emotion/domains/README.md) — understand the available domains
- [Communication Modes](../src/tau_emotion/orchestrator/README.md) — half-duplex (turn-based) orchestration
- [TRACER](../tracer/README.md) — the pipeline that generates the tasks
