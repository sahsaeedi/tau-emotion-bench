# Training tasks

The benchmark's test tasks are in `tasks.json`. Each domain also ships training
tasks in `tasks_train.json`, 2,723 in total, for training agents. None of them
matches a test task, so evaluation still measures a model that has never seen
the test set.

## Where they come from

The training tasks were generated with [TRACER](../tracer/README.md), like the
test tasks, and converted into the same task format, so a training task is shaped
exactly like a benchmark task. The set was then filtered in three steps:

1. **Duplicates.** Tasks are compared on the user's instructions, the emotion
   instruction, the gold actions and the expected outputs, and exact matches
   are dropped. Two tasks that differ only in emotion are kept: the simulated
   user behaves differently, so they are different training signal.
2. **Unsolvable tasks.** Each task's gold actions were replayed against the
   train database. A task whose gold actions fail can never be solved, so it
   was dropped.
3. **Solved tasks only.** Only the tasks that a Qwen3.8-27B (thinking) agent
   solved with reward 1, in one run, are shipped.

### 40 tasks restored with a ground-truth fix

40 tasks that step 2 dropped were solved with reward 1 anyway, so they were
added back. For the 31 retail and bank tasks the gold actions were edited: each
fix removes calls that failed in TRACER's environment and changed nothing there,
so the gold actions reach the state the solved run was scored against. The 9
telecom tasks needed no edit. Every restored task was checked by replaying that
run's successful tool calls on the train database: the final database equals
the gold's, and the agent said every output TRACER's task expects (the shipped
tasks don't score this).

| Domain | tasks | why they were dropped | fix |
|---|---|---|---|
| retail  | 23 | returned and exchanged the same unit on one order, which the policy rejects | drop the second call of that pair (17 returns, 6 exchanges) |
| telecom |  9 | created a ticket and then used its id, which the check got wrong because it replayed them on a different database | none: they replay on the train database |
| bank    |  8 | used a made-up beneficiary id after `add_beneficiary`, which assigns its own | drop the `get_beneficiary_details` / `verify_beneficiary` calls on that id |

In 8 of the retail tasks the user still asks for the dropped return, so the
policy makes the agent refuse it.

## What is in the set

| Domain | train tasks |
|---|---|
| airline    |  143 |
| retail     |  585 |
| telecom    |  186 |
| telehealth |  584 |
| bank       |  228 |
| basketball |  346 |
| movie      |  231 |
| restaurant |  163 |
| school     |  133 |
| travel     |  124 |
| **total**  | **2723** |

A task id is `<domain>_train_<source>_<index>`. `source` (also a field on the
task) names the TRACER generation batch the task came from, `original` for
airline, retail, telecom and telehealth and `new` for the other six, and the index
is the task's position in that batch.

## The train database

Each domain has a second database file, `db_train.json`, that its train tasks
run on:

- **airline, retail, telecom, telehealth:** a copy of `db.json`. Their test and
  train tasks were written against the same database.
- **bank, basketball, movie, restaurant, school, travel:** TRACER's train database
  (`tracer/tracer/envs/<domain>/data/train/`), since their train tasks reference
  customers that exist only there.

Loading follows the task:

```python
registry.get_tasks_loader("airline")(task_split_name="train")   # train tasks
registry.get_env_constructor("airline")(db_split="train")       # their database
```

A run with `--task-split-name train` picks `db_train.json` for every train
task, and the evaluator replays the gold actions against the same database.
Nothing else changes: `base` and `test` still load the shipped tasks and
`db.json`.
