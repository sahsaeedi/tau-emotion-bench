# Tau-Emotion Domains

This folder contains the domains for the Tau-Emotion project: the 10 benchmark domains, ported from TRACER's environments (`tracer/tracer/envs/`), and the `mock` domain used by the tests.

## Domain Structure

Each domain has its own folder with the following structure:

- `data_model.py`: Defines the data models for the domain. 
    - Implements a subclass of `DB` (e.g. `FlightDB(DB)`) which is the base class for all domain databases (defined in `src/tau_emotion/environment/db.py`).
- `user_data_model.py`: Defines the data models for the user data for the domain. (Optional; only `mock` has one)
    - Implements a subclass of `DB` for the domain's user database.
- `tools.py`: Defines the tools for the domain. 
    - Implements a subclass of `ToolKitBase` (e.g. `AirlineTools(ToolKitBase)`) which is the base class for all domain toolkits (defined in `src/tau_emotion/environment/toolkit.py`). 
- `user_tools.py`: Defines the user tools for the domain. (Optional; only `mock` has one)
    - Implements a subclass of `ToolKitBase` for user-facing tools. 
- `environment.py`: Defines the environment for the domain. 
    - Implements `get_environment()` function that returns an `Environment` instance for the domain. In the 10 benchmark domains it takes `db_split` (`"test"` for `db.json`, the default, or `"train"` for `db_train.json`).
    - Implements `get_tasks()` function that returns a list of tasks for the domain.
    - Implements `get_tasks_split()` function that returns a dictionary mapping split names to lists of task IDs.
- `utils.py`: Defines the utility functions for the domain (e.g. data paths).

The 10 benchmark domains share the task and database loading in [`task_loading.py`](task_loading.py).

## Data Storage

All the data for the domain is stored in `data/tau_emotion/domains/<domain_name>` folder.
For the 10 benchmark domains it contains:
- `policy.md`: The domain policy. It is the only policy the agent sees.
- `db.json`: The database the test tasks run against.
- `db_train.json`: The database the train tasks run against. For airline, retail, telecom and telehealth it is the same database as `db.json`.
- `tasks.json`: The test tasks, the benchmark (70 each for airline, retail, telecom and telehealth; 50 each for the others; 580 in total).
- `tasks_train.json`: The train tasks (2,723 in total), the tasks a Qwen3.8-27B (thinking) agent solved with reward 1. See [`docs/train_tasks.md`](../../../docs/train_tasks.md).

Splits are derived from these files, with no split file:
- `base` (the default) and `test`: the tasks in `tasks.json`, run on `db.json`.
- `train`: the tasks in `tasks_train.json`, run on `db_train.json`, which the runner selects automatically.

The `mock` domain keeps the upstream layout: `tasks.json`, `split_tasks.json` (split name -> task IDs, with a `base` split), `policy.md`, `policy_solo.md`, `db.json` and `user_db.json`.

## Task Schema and Evaluation

Each entry in `tasks.json` is a `Task` (see
[`src/tau_emotion/data_model/tasks.py`](../data_model/tasks.py)) with a
`user_scenario` and an `evaluation_criteria` block. Every task's
`user_scenario` carries an `emotion_instruction`, which the user simulator
acts out, and `emotion_metadata` labels, used only for analysis. All 10
domains score with `reward_basis: ["DB", "COMMUNICATE"]`, and a run the
simulated user ends with `###UNSATISFIED###` gets reward -1.

Note: `evaluation_criteria.actions` is
*one* reference trajectory used to derive the target DB end state, not
a per-call requirement on the agent (unless `RewardType.ACTION` is in
`reward_basis`, which no task of the 10 domains uses). See [`docs/evaluation.md`](../../../docs/evaluation.md) for
the full breakdown.


## Tests
All the tests for the domain are stored in the `tests/test_domains/test_<domain_name>` folder.
- `test_tools_<domain_name>.py`: Contains tests for the tools for the domain.
- `mock` is the only domain with user tools; `test_mock/test_tools_mock.py` tests them too.

`tests/test_domains/test_emotion_tasks.py` checks the task files shared by the 10 domains.

To run tests:
```sh
pytest tests/test_domains/test_<domain_name>
```

## Available Domains

| Domain | Description |
|--------|-------------|
| `airline` | Flight booking, cancellation, and customer support |
| `retail` | Order management, returns, and product inquiries |
| `telecom` | Telecom account management and troubleshooting (TRACER's account-management domain, not τ²-bench's telecom domain) |
| `telehealth` | Patient appointments, prescriptions, and provider scheduling |
| `bank` | Account, card, loan and beneficiary management, and transfers |
| `basketball` | Club, player and game lookup, scoring, and statistics |
| `movie` | Showtimes, seat booking, and ticket cancellation |
| `restaurant` | Ticket lookup, order modification, cancellation, and tips |
| `school` | Course registration, schedule changes, and tuition payments |
| `travel` | Package search, trip booking, and itinerary changes |
| `mock` | Lightweight test fixture, used only by the tests |

## Registering your domain
To make it easy for people to use your domain, you need to register your `get_environment`, `get_tasks`, and `get_tasks_split` functions in Tau-Emotion `registry.py` file.

In `registry.py`:
```python
from tau_emotion.domains.your_domain.environment import get_environment as your_domain_get_environment
from tau_emotion.domains.your_domain.environment import get_tasks as your_domain_get_tasks
from tau_emotion.domains.your_domain.environment import get_tasks_split as your_domain_get_tasks_split
...
registry.register_domain(your_domain_get_environment, "your_domain_name")
registry.register_tasks(your_domain_get_tasks, "your_domain_name", get_task_splits=your_domain_get_tasks_split)
```
