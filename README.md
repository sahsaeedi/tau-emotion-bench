# τ-emotion-bench

[![python](https://img.shields.io/badge/Python-3.12%2B-blue.svg?style=flat&logo=python&logoColor=white)](https://www.python.org)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

A benchmark for customer-service agents talking to **emotional users**. Every task
pairs a tool-use goal (cancel a reservation, move a loan payment, reschedule an
appointment) with an emotional persona the simulated user acts out: curt, anxious,
distrustful, in a hurry. It measures whether an agent still completes the task when
the user is hard to deal with.

The tasks were generated with [TRACER](tracer/README.md), which is also in this
repository.

## Domains and tasks

| Domain | Read tools | Write tools | Total tools | Emotions (family/subfamily) | Test tasks | Train tasks |
|---|---|---|---|---|---|---|
| airline    |  8 | 6 | 14 | 5/16 |  70 |  143 |
| retail     |  9 | 7 | 16 | 4/11 |  70 |  585 |
| telecom    | 13 | 6 | 19 | 5/13 |  70 |  186 |
| telehealth | 18 | 5 | 23 | 3/8  |  70 |  584 |
| school     | 10 | 4 | 14 | 4/10 |  50 |  133 |
| basketball | 17 | 3 | 20 | 1/2  |  50 |  346 |
| restaurant |  9 | 6 | 15 | 4/8  |  50 |  163 |
| travel     |  9 | 7 | 16 | 3/8  |  50 |  124 |
| movie      | 13 | 3 | 16 | 4/10 |  50 |  231 |
| bank       | 13 | 9 | 22 | 3/8  |  50 |  228 |
| **total**  |    |   |    |      | **580** | **2,723** |

- **Read tools** are every tool that does not change the database, including
  `think`, `calculate` and the transfer to a human agent.
- **Emotions** counts the distinct emotion families and subfamilies across a
  domain's test tasks.

- **Test tasks** (`tasks.json`) are the benchmark. They run against `db.json`.
- **Train tasks** (`tasks_train.json`) are separate tasks for training models, run
  against `db_train.json` ([docs/train_tasks.md](docs/train_tasks.md)).
- Each domain's files are in `data/tau_emotion/domains/<domain>/`, and its
  `policy.md` is the only policy the agent sees.

## Emotions and scoring

Each task's `user_scenario` has an `emotion_instruction`, a behaviour description
the user simulator acts out ("You're eager and insistent..."), and
`emotion_metadata` labels (`emotion_family`, `emotion_leaf`, politeness, urgency,
trust in the agent) used only for analysis.

A conversation is scored on the final database state. The simulated user ends it
in one of two ways:

- `###STOP###`: the task is done, and the run scores 1 or 0.
- `###UNSATISFIED###`: the user gave up because the agent ignored their emotional
  needs, eroded trust, or created friction. The run scores **-1**, below the 0 of a
  run that simply failed.

[docs/evaluation.md](docs/evaluation.md) explains the scoring and how a
conversation runs.

## Installation

Requires Python 3.12. With [uv](https://docs.astral.sh/uv/getting-started/installation/):

```bash
git clone https://github.com/sahsaeedi/tau-emotion-bench.git
cd tau-emotion-bench
uv sync
source .venv/bin/activate
cp .env.example .env           # then set your API keys
tau-emotion check-data
```

Without uv, create the environment with
`python3.12 -m venv .venv && source .venv/bin/activate && pip install -e .` instead
of `uv sync`.

**The benchmark's user simulator is `qwen3-235b-a22b-instruct-2507` at temperature
0.7**, the default when you leave out `--user-llm`. Use it when you compare against
reported scores. OpenAI and Anthropic don't serve it, so run it on an
OpenAI-compatible server that does (your own vLLM server or a hosted provider) and
pass `--user-api-base <url> --user-api-key <key>`. Setting `OPENAI_API_BASE` instead
sends every OpenAI model, `gpt-4.1` included, to that server.
[docs/models.md](docs/models.md) covers keys, servers and reasoning models.

## Running the benchmark

Five airline tasks, with only an OpenAI key:

```bash
tau-emotion run --domain airline --agent-llm gpt-4.1 --user-llm gpt-4.1 \
  --num-trials 1 --num-tasks 5
```

A full domain, three trials, with a `gpt-4.1` agent and the benchmark's user
simulator on another server:

```bash
tau-emotion run --domain airline --agent-llm gpt-4.1 --num-trials 3 \
  --user-api-base <url> --user-api-key <key>
```

| Flag | What it does |
|---|---|
| `--domain` | One of the 10 domains |
| `--agent-llm`, `--user-llm` | The agent's and the user simulator's models |
| `--agent-llm-args`, `--user-llm-args` | Sampling arguments as JSON, e.g. `'{"temperature": 0.0}'`; they replace the defaults |
| `--task-split-name` | `base` (the default) or `test`, the same benchmark tasks, or `train` |
| `--num-trials`, `--num-tasks`, `--task-ids` | How many runs of which tasks |
| `--max-concurrency` | Simulations run in parallel |
| `--save-to` | Results folder under `data/simulations/` |
| `--no-emotion` | Leave out the emotion instructions: the same tasks with a neutral user |

All flags are in the [CLI reference](docs/cli-reference.md).

`run_eval.sh` wraps a full run of one domain and one model (3 resumable trials; add
`--num-tasks N` for a quick check). Edit the settings block at the top, or pass
flags:

```bash
./run_eval.sh --domain bank --output runs/qwen3-8b/bank --agent-model qwen3-8b
```

It sets the user simulator to temperature 0.0; pass `--user-temperature 0.7` for the
benchmark's usual setting.

To benchmark your own agent instead of a model behind the built-in one, see
[examples/agents/](examples/agents/README.md).

## Results

Each finished conversation is saved to `data/simulations/<run>/results.json` as soon
as it ends, and the run prints its metrics when all are done.

- **Run folder:** without `--save-to`, `<run>` is `<domain>/<agent model>`, extended
  with a non-default agent's name, the thinking or reasoning setting, a user model
  other than the benchmark's (`user-<model>`), the train split (`train`) and
  `--no-emotion` (`no-emotion`).
- **Resuming:** running the same command again offers to resume the run
  (`--auto-resume` skips the prompt) and retries its infrastructure errors. A higher
  `--num-trials` adds the missing trials.
- **Metrics:** Pass^k and Pass@k for k = 1 up to the number of trials (only reward 1
  counts as a success), the average reward, database matches, and how the
  conversations ended.

```bash
tau-emotion view                                         # browse runs and conversations
tau-emotion review data/simulations/<run>/results.json   # LLM judge of agent and user errors
```

`review` has an LLM judge label each conversation's agent and user errors by
severity. The judge is `claude-opus-4-5` unless you pick another with `--judge-llm`.

## Documentation

- [Getting started](docs/getting-started.md)
- [CLI reference](docs/cli-reference.md)
- [Models and endpoints](docs/models.md)
- [Scoring and how a conversation runs](docs/evaluation.md)
- [Running simulations from Python](docs/running_simulations.md)
- [Train tasks](docs/train_tasks.md)
- [Custom agents](examples/agents/README.md)
- [TRACER: generating and evaluating tasks](tracer/README.md)

## Development

```bash
uv sync --extra dev   # or: pip install -e ".[dev]"
make test          # the tests that call an LLM are skipped without OPENAI_API_KEY
make check-all     # ruff lint and format
```

Set `TAU_EMOTION_TEST_LLM` to run the LLM tests on a model other than `gpt-4.1-mini`.
With `OPENAI_API_BASE` set, that model must be one the server there serves.

## License and acknowledgements

This repository is released under the [Apache License 2.0](LICENSE).

We thank the authors of [τ-bench](https://github.com/sierra-research/tau-bench) and
[τ²-bench](https://github.com/sierra-research/tau2-bench). τ-emotion-bench follows
τ-bench's conventions for running and scoring conversations, and its code is
organized in τ²-bench's format. TRACER's domain environments and model utilities
build on [τ-trait](https://github.com/collinear-ai/tau-trait). All three are
MIT-licensed; their licence notices, and which parts of this repository use them,
are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
