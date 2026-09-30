# CLI Reference

The `tau-emotion` command provides a unified interface for all τ-emotion-bench functionality. Use `tau-emotion <command> --help` to see full details for any command.

Run `tau-emotion intro` (or just `tau-emotion`) to see an overview of available domains, commands, and a quick-start guide directly in the terminal.

## `tau-emotion run` — Run Evaluations

Run an agent on a domain's tasks against the emotional user simulator.

### Basic Usage

```bash
tau-emotion run \
  --domain <domain> \
  --agent-llm <llm_name> \
  --user-llm <llm_name> \
  --num-trials <trial_count> \
  --num-tasks <task_count>
```

### Common Options

| Option | Description |
|--------|-------------|
| `--domain`, `-d` | Domain to evaluate: `airline`, `retail`, `telecom`, `telehealth`, `bank`, `basketball`, `movie`, `restaurant`, `school`, `travel` (`mock` is a test fixture) |
| `--agent-llm` | LLM model for the agent (default: `gpt-4.1-2025-04-14`) |
| `--user-llm` | LLM model for the user simulator (default: `qwen3-235b-a22b-instruct-2507`) |
| `--agent-llm-args` | JSON dict of extra args for the agent LLM (default: `'{"temperature": 0.0}'`) |
| `--user-llm-args` | JSON dict of extra args for the user LLM (default: `'{"temperature": 0.7}'`) |
| `--agent-temperature` | The agent LLM's temperature. Overrides the temperature in `--agent-llm-args` (default `0.0`) |
| `--agent-api-base`, `--user-api-base` | Base URL of that side's OpenAI-compatible server, e.g. `http://localhost:8000/v1`. Default: the provider's (`OPENAI_API_BASE` for bare and `openai/` model names) |
| `--agent-api-key`, `--user-api-key` | API key for that side's server. Default: the provider's env var (`OPENAI_API_KEY` for bare and `openai/` model names), or no key when the matching `--*-api-base` is given, so the key isn't sent to another server. Not saved in the results |
| `--agent-enable-thinking` / `--no-agent-enable-thinking` | Turn the agent model's thinking on or off through its chat template (vLLM `chat_template_kwargs.enable_thinking`). Default: the model's own default |
| `--user-enable-thinking` / `--no-user-enable-thinking` | Same, for the user model |
| `--agent` | Agent implementation to use: `llm_agent` (default), `llm_agent_gt`, `llm_agent_solo` |
| `--user` | User simulator implementation to use: `user_simulator` (default), `dummy_user` |
| `--no-emotion` | Leave the task's emotion instruction out of the user simulator's prompt (an ablation: the same tasks with a neutral user). Adds `no-emotion` to the default run folder |
| `--num-trials` | Number of times each task is run (default: `1`) |
| `--num-tasks` | Number of tasks to evaluate (omit for all tasks) |
| `--task-ids` | Only run the tasks with these ids (e.g. `airline_test_0000 airline_test_0003`) |
| `--task-split-name` | Task split: `base` (default) or `test`, the same 580-task benchmark set run on `db.json`; or `train`, the train tasks run on `db_train.json` |
| `--task-set-name` | Task set to use (default: the domain's own) |
| `--max-steps` | Maximum simulation steps (default: `200`) |
| `--max-errors` | Maximum number of tool errors in a run before it is stopped (default: `200`, equal to `--max-steps`, so the cap is effectively off) |
| `--max-concurrency` | Maximum concurrent simulations (default: `3`) |
| `--seed` | Random seed for reproducibility (default: `300`) |
| `--save-to` | Output directory name, saved as `data/simulations/<save_to>/results.json`. Default: `<domain>/<agent model>`, plus suffixes for a non-default agent, thinking/reasoning settings, a non-default user model (`user-<model>`), the train split (`train`) and `--no-emotion` (`no-emotion`), e.g. `airline/gpt-4.1_user-gpt-4.1`. An absolute path is used as is. If the file already exists, the run is resumed |
| `--log-level` | Log level (default: `ERROR`) |
| `--verbose-logs` | Save detailed logs (LLM calls, per-task logs) |
| `--llm-log-mode` | LLM log mode when `--verbose-logs` is on: `all` or `latest` (default: `latest`) |
| `--max-retries` | Max retries for failed tasks (default: `3`) |
| `--retry-delay` | Delay in seconds between retries (default: `1.0`) |
| `--enforce-communication-protocol` | Enforce protocol rules (e.g. no mixed text + tool call messages) |
| `--auto-resume` | Automatically resume from existing save file without prompting |
| `--auto-review` | Automatically run LLM conversation review after each simulation. The judge is always `claude-opus-4-5` (needs `ANTHROPIC_API_KEY`); for another judge, run `tau-emotion review --judge-llm ...` after the run |
| `--review-mode` | Review mode when `--auto-review` is on: `full` or `user` (default: `full`) |
| `--timeout` | Maximum wallclock time in seconds per simulation (no timeout by default) |

### Examples

```bash
# Standard text evaluation on five test tasks
tau-emotion run --domain airline --agent-llm gpt-4.1 --user-llm gpt-4.1 --num-trials 1 --num-tasks 5

# Specific tasks, three trials each
tau-emotion run --domain retail --task-ids retail_test_0000 retail_test_0003 \
  --agent-llm gpt-4.1 --user-llm gpt-4.1 --num-trials 3

# Train tasks (db_train.json is loaded automatically)
tau-emotion run --domain bank --task-split-name train \
  --agent-llm gpt-4.1 --user-llm gpt-4.1 --num-tasks 5

# A model served locally by an OpenAI-compatible server, with thinking off
tau-emotion run --domain telehealth --agent-llm <served_model_name> \
  --agent-api-base http://localhost:8000/v1 --no-agent-enable-thinking \
  --user-llm gpt-4.1 --max-concurrency 8 --auto-resume
```

---

## `tau-emotion view` — View Results

Browse and analyze simulation results. It lists every `results.json` under `data/simulations/` (or `--dir`), at any depth.

```bash
tau-emotion view
```

| Option | Description |
|--------|-------------|
| `--dir` | Directory containing simulation files (defaults to `data/simulations/`) |
| `--file` | Path to a specific results file to view |
| `--only-show-failed` | Only show failed tasks |
| `--only-show-all-failed` | Only show tasks that failed in all trials |

---

## `tau-emotion domain` — View Domain Documentation

View domain policy and API documentation.

```bash
tau-emotion domain <domain>
```

Then visit http://127.0.0.1:8004/redoc to see the domain policy and available tools.

---

## `tau-emotion check-data` — Check Data Configuration

Print the data directory in use and check that it exists.

```bash
tau-emotion check-data
```

---

## `tau-emotion start` — Start All Servers

Start the tau-emotion API server (`src/tau_emotion/api_service`) on port 8001.

```bash
tau-emotion start
```

---

## `tau-emotion evaluate-trajs` — Evaluate Trajectories

Re-evaluate trajectory files and optionally update rewards.

```bash
tau-emotion evaluate-trajs <paths...>
```

| Option | Description |
|--------|-------------|
| `<paths>` | Paths to trajectory files, directories, or glob patterns |
| `-o`, `--output-dir` | Directory to save the re-scored results in, one file per input named after its run folder (`updated_<run folder>_results.json`). If omitted, only displays metrics |

---

## `tau-emotion review` — LLM Conversation Review

Run LLM-based review on simulation results to detect agent and/or user errors. Reviews are written next to the input as `results_reviewed.json` unless `-o` is given.

```bash
tau-emotion review <path>
```

| Option | Description |
|--------|-------------|
| `<path>` | Path to a `results.json` file or directory containing them |
| `-m`, `--mode` | Review mode: `full` (agent + user, default) or `user` (user simulator only) |
| `-o`, `--output` | Output path for reviewed results (single file only) |
| `--show-details` | Show detailed review for each simulation |
| `-c`, `--max-concurrency` | Max concurrent reviews (default: `32`) |
| `--limit` | Limit review to first N simulations |
| `--task-ids` | Only review simulations for these task IDs |
| `--failed-only` | Only review failed simulations (reward not 1). Default: review all |
| `--judge-llm` | The LLM used as the review judge (default: `claude-opus-4-5`). A bare model name (e.g. `qwen3-235b-a22b-instruct-2507`) goes to `OPENAI_API_BASE` |
| `--judge-llm-args` | The arguments to pass to the judge LLM, as JSON (default: `'{}'`) |
| `--judge-api-base` | Base URL of the judge's OpenAI-compatible server. Default: the provider's (`OPENAI_API_BASE` for bare and `openai/` model names) |
| `--judge-api-key` | API key for the judge's server. Default: the provider's env var, or no key when `--judge-api-base` is given |
| `--judge-enable-thinking` / `--no-judge-enable-thinking` | Turn the judge model's thinking on or off through its chat template. Default: the model's own default |
| `--log-llm` | Log LLM request/response for each review call |

Example:

```bash
tau-emotion review data/simulations/airline/gpt-4.1 --failed-only \
  --judge-llm qwen3-235b-a22b-instruct-2507
```

---

## `tau-emotion convert-results` — Convert Results Format

Convert simulation results between monolithic JSON and directory-based formats.

```bash
tau-emotion convert-results <path> [--to {json,dir}] [--no-backup]
```

| Option | Description |
|--------|-------------|
| `<path>` | Path to a `results.json` file or directory containing one |
| `--to` | Target format: `json` (monolithic) or `dir` (directory with individual sim files). If omitted, converts to the opposite of the current format |
| `--no-backup` | Skip creating a backup before conversion |

Runs default to monolithic JSON. Use this command to convert between formats when needed.

---

## Environment CLI (beta)

An interactive CLI for directly querying and testing domain environments. An LLM (`DEFAULT_LLM_ENV_INTERFACE` in `config.py`) turns your questions into tool calls, so it needs an API key.

```bash
make env-cli
```

**Commands:**
- `:q` — quit
- `:d` — change domain
- `:n` — start new session (clears history)

**Example:**
```bash
$ make env-cli

Welcome to the Interface Agent CLI!
Connected to airline domain.

Query (:n new session, :d change domain, :q quit)> What flights are available from JFK to SEA on 2024-05-20?
Assistant: Let me check the flight availability for you...
```

Useful for testing domain tools, debugging environment responses, and exploring domain functionality without starting the full server stack.

---

## Running Tests

```bash
make test              # Core tests (requires: uv sync --extra dev)
make test-all          # All tests (requires: uv sync --all-extras)
```

Tests that call an LLM are marked `llm` and skipped when `OPENAI_API_KEY` is not
set. They use `gpt-4.1-mini`; set `TAU_EMOTION_TEST_LLM` to use another model.

---

## Advanced: Ablation Studies

### Oracle-plan mode

The agent is given the task's reference actions as resolution steps, removing the need for action planning. It runs on tasks that list at least one action, which includes the tasks of all 10 domains:

```bash
tau-emotion run \
  --domain airline \
  --agent llm_agent_gt \
  --agent-llm gpt-4.1 \
  --user-llm gpt-4.1
```

### No-user mode

The agent is given a task ticket and all tools up front, with no user (`--agent llm_agent_solo --user dummy_user`). Only the `mock` domain supports it: the 10 benchmark domains don't support solo mode and their tasks carry no ticket.
