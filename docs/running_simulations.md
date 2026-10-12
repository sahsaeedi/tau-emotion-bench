# Running Simulations

This guide covers the `tau_emotion.runner` API for running simulations at different levels of control. Whether you want a one-liner CLI command or full programmatic control over every component, the runner framework has you covered.

## Architecture Overview

The runner framework is organized into three layers:

| Layer | Module | Purpose |
|-------|--------|---------|
| **Layer 1** | `runner.simulation` | Execute a pre-built orchestrator. No config; scoring looks the domain up in the registry. |
| **Layer 2** | `runner.build` | Build instances (environment, agent, user, orchestrator) from names/config via the registry. |
| **Layer 3** | `runner.batch` | Batch execution with concurrency, checkpointing, retries, logging, and side effects. |

Each layer builds on the one below it, but you can enter at any level depending on your needs.

---

## Level 1: CLI (Simplest)

The fastest way to run simulations is through the `tau-emotion run` command:

```bash
# Run all airline test tasks with GPT-4.1
tau-emotion run \
  --domain airline \
  --agent llm_agent \
  --agent-llm openai/gpt-4.1

# Run specific tasks with multiple trials
tau-emotion run \
  --domain retail \
  --agent llm_agent \
  --agent-llm openai/gpt-4.1 \
  --task-ids retail_test_0000 retail_test_0003 \
  --num-trials 3

# Run with concurrency and auto-resume
tau-emotion run \
  --domain telecom \
  --agent llm_agent \
  --agent-llm openai/gpt-4.1 \
  --max-concurrency 4 \
  --auto-resume
```

See `tau-emotion run --help` or [CLI Reference](cli-reference.md) for all options.

---

## Level 2: Config-Based Python API (Intermediate)

For programmatic use, create a `TextRunConfig` and call `run_domain()`:

### Text (half-duplex) simulations

```python
from tau_emotion import TextRunConfig
from tau_emotion.runner import run_domain

config = TextRunConfig(
    domain="airline",
    agent="llm_agent",
    llm_agent="openai/gpt-4.1",
    llm_user="openai/gpt-4.1-mini",
    num_trials=3,
    max_concurrency=4,
    seed=42,
)

results = run_domain(config)
# compute_metrics() returns an AgentMetrics object with avg_reward, pass_hat_ks, etc.
from tau_emotion.metrics.agent_metrics import compute_metrics
metrics = compute_metrics(results)
print(f"Average reward: {metrics.avg_reward}")
```

`TextRunConfig` extends `BaseRunConfig`, which holds shared fields like `domain`, `task_split_name`, `num_trials`, `seed`, etc. `RunConfig` is an alias for `TextRunConfig`. Unset fields take the same defaults as the CLI (`config.py`); `llm_user` defaults to `qwen3-235b-a22b-instruct-2507`.

This handles everything: task loading, filtering, concurrency, checkpointing, metrics display. Results are saved to `data/simulations/<save_to>/results.json`. Without `save_to`, the folder is `make_run_name(config)`: `<domain>/<agent model>`, plus suffixes for a non-default agent, thinking/reasoning settings, a non-default user model, the train split and `no_emotion`. For the config above that is `airline/openai_gpt-4.1_user-openai_gpt-4.1-mini`.

### Train tasks

```python
config = TextRunConfig(
    domain="bank",
    task_split_name="train",   # tasks_train.json; each task runs on db_train.json
    llm_agent="openai/gpt-4.1",
)
results = run_domain(config)
```

`task_split_name` is `"base"` (default) or `"test"` for the benchmark tasks, and `"train"` for the train tasks. The train database is picked per task (`task.split == "train"`), so nothing else needs to change.

### Running specific tasks

```python
from pathlib import Path
from tau_emotion import TextRunConfig
from tau_emotion.runner import get_tasks, run_tasks

config = TextRunConfig(
    domain="airline",
    agent="llm_agent",
    llm_agent="openai/gpt-4.1",
)

# Load and filter tasks manually
tasks = get_tasks("airline", task_ids=["airline_test_0000", "airline_test_0003"])

# Run with custom save path
results = run_tasks(
    config,
    tasks,
    save_path=Path("my_results/results.json"),
    save_dir=Path("my_results/"),
)
```

### Running a single task

```python
from tau_emotion import TextRunConfig
from tau_emotion.runner import run_single_task, get_tasks

config = TextRunConfig(domain="airline", agent="llm_agent", llm_agent="openai/gpt-4.1")
tasks = get_tasks("airline")

result = run_single_task(config, tasks[0], seed=42)
print(f"Task {result.task_id}: reward={result.reward_info.reward}")
```

---

## Level 3: Instance-Based Python API (Power User)

For maximum control, build instances yourself and use `run_simulation()`. This is ideal for:
- Custom agents not in the registry
- Fine-grained control over agent/user construction
- Testing and development
- Integration into custom pipelines

### Using build helpers with the registry

```python
from tau_emotion.runner import (
    build_environment,
    build_agent,
    build_user,
    build_orchestrator,
    run_simulation,
    get_tasks,
)
from tau_emotion.evaluator.evaluator import EvaluationType

# Load a task
tasks = get_tasks("airline")
task = tasks[0]

# Option A: Build orchestrator from config (uses registry)
from tau_emotion import TextRunConfig
config = TextRunConfig(domain="airline", agent="llm_agent", llm_agent="openai/gpt-4.1")
orchestrator = build_orchestrator(config, task, seed=42)
result = run_simulation(orchestrator, evaluation_type=EvaluationType.ALL)

# Option B: Build components individually
env = build_environment("airline")
agent = build_agent("llm_agent", env, llm="openai/gpt-4.1")
user = build_user("user_simulator", env, task, llm="openai/gpt-4.1-mini")
```

For a train task, the environment must use the train database: `build_environment("airline", env_kwargs={"db_split": "train"})` (`build_orchestrator` already does this for a task whose `split` is `"train"`). Pass the same `env_kwargs` to `run_simulation()` as well, so the run is scored against that database. `run_single_task` and `run_domain` handle both steps.

### Fully custom instances (no build helpers)

```python
from tau_emotion.runner import run_simulation
from tau_emotion.orchestrator.orchestrator import Orchestrator
from tau_emotion.user.user_simulator import UserSimulator

# Your custom environment and agent
env = MyCustomEnvironment()
agent = MyCustomAgent(tools=env.get_tools(), domain_policy=env.get_policy())

# Standard user simulator; the instructions include the task's emotion instruction.
# The benchmark domains give the user no tools; pass env.get_user_tools() only
# if your environment has user tools (it raises ValueError otherwise).
user = UserSimulator(
    tools=None,
    instructions=task.user_scenario.to_tau_bench_instruction(),
    llm="openai/gpt-4.1-mini",
)

# Wire everything into an orchestrator
orchestrator = Orchestrator(
    domain="my_domain",
    agent=agent,
    user=user,
    environment=env,
    task=task,
    max_steps=200,
    max_errors=200,
    seed=42,
)

# Run and evaluate
result = run_simulation(orchestrator)
print(f"Reward: {result.reward_info.reward}")
```

`run_simulation()` scores the run through the registry, looking the domain up by `env.get_domain_name()`, so the environment's domain must be registered for scoring to work.

---

## API Reference

### Layer 1: Execution

- **`run_simulation(orchestrator, *, evaluation_type=EvaluationType.ALL, env_kwargs=None)`** -- Run a pre-built orchestrator and evaluate the result. Returns `SimulationRun` with `reward_info` attached.

### Layer 2: Build

- **`build_environment(domain, *, solo_mode=False, env_kwargs=None)`** -- Build an environment from a domain name.
- **`build_agent(agent_name, environment, *, llm, llm_args, task, solo_mode)`** -- Build an agent from a registered name.
- **`build_user(user_name, environment, task, *, llm, llm_args, solo_mode, no_emotion)`** -- Build a half-duplex user from a registered name.
- **`build_text_orchestrator(config, task, *, seed, simulation_id)`** -- Build a half-duplex `Orchestrator` from a `TextRunConfig`.
- **`build_orchestrator(config, task, *, seed, simulation_id)`** -- Same as `build_text_orchestrator`.

### Layer 3: Batch Execution

- **`run_domain(config)`** -- Run all tasks for a domain from a `RunConfig`. Handles task loading, filtering, save paths, metrics.
- **`run_tasks(config, tasks, *, save_path, save_dir, evaluation_type=EvaluationType.ALL, console_display=True, results_format="json")`** -- Run a list of tasks with concurrency, checkpointing, and retries.
- **`run_single_task(config, task, *, seed, evaluation_type=EvaluationType.ALL, save_dir, ...)`** -- Run one task with logging and optional side effects (auto-review).

### Helpers

- **`get_options()`** -- List available domains, agents, users, and task sets.
- **`get_tasks(task_set_name, task_split_name, task_ids, num_tasks)`** -- Load tasks with optional filtering.
- **`load_tasks(task_set_name, task_split_name)`** -- Load raw tasks from the registry.
- **`load_task_splits(task_set_name)`** -- Split name -> task ids for a task set.
- **`get_environment_info(domain_name, include_tool_info, env_kwargs)`** -- Describe a domain's environment.
- **`get_info(config, **overrides)`** -- Create run metadata (`Info` object).
- **`make_run_name(config)`** -- Generate the default run name: `<domain>/<agent model>`, plus suffixes for a non-default agent (as a prefix), thinking/reasoning settings, a non-default user model (`user-<model>`), the train split (`train`) and `no_emotion` (`no-emotion`).

---

## Choosing the Right Level

| Scenario | Recommended Level |
|----------|------------------|
| Quick evaluation from the command line | Level 1 (CLI) |
| Running evals in a Python script | Level 2 (Config-based) |
| Custom agent development and testing | Level 3 (Instance-based) |
| Integrating into a larger pipeline | Level 3 (Instance-based) |
| Hyperparameter sweeps | Level 2 (Config-based) |
| Contributing a new domain/agent | Level 3 for testing, Level 2 for benchmarking |
