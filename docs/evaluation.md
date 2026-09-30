# Task Schema and Evaluation

This page explains how a task is scored in τ-emotion-bench and — most importantly —
**what `evaluation_criteria.actions` actually does**. If you have looked at
`data/tau_emotion/domains/airline/tasks.json` and assumed those listed actions are
required of the agent, this page is for you.

## TL;DR

- A run the simulated user abandons with `###UNSATISFIED###` gets reward
  **-1**, before any other check runs. A run that ends any other way than
  the agent or user stopping (step limit, error cap, timeout, error) gets
  **0**.
- Otherwise the task's reward is the **product** of the components listed
  in `evaluation_criteria.reward_basis`.
- Every task of the 10 domains (airline, retail, telecom, telehealth,
  bank, basketball, movie, restaurant, school, travel), test and train,
  uses `reward_basis: ["DB", "COMMUNICATE"]`. None of them lists
  `communicate_info`, so COMMUNICATE always gives 1.0 and the database
  check decides the score.
- `evaluation_criteria.actions` is **one reference trajectory** that
  solves the task — not the only correct one. It is replayed on a fresh
  "gold" environment to derive a target DB end state, which is then
  compared (by hash) to the predicted environment's DB end state. The
  agent is **not** required to take this specific path; any sequence of
  tool calls that produces an equivalent DB end state passes the DB
  check.
- The agent is required to match `actions` *only* when `RewardType.ACTION`
  is in `reward_basis`. No task of the 10 domains uses it; only a few
  `mock` test fixtures do. When that flag is set, the listed actions are
  treated as the assumed-unique correct trajectory — which is a strong
  assumption and is why the benchmark tasks deliberately do not use it.
- This was a deliberate design choice upstream in τ²-bench (see
  [issue #224][issue-224] and [RFC #129][issue-129] for the discussion).
  We surface this here so it is harder to miss.

[issue-224]: https://github.com/sierra-research/tau2-bench/issues/224
[issue-129]: https://github.com/sierra-research/tau2-bench/issues/129

## The task schema, in plain English

A task (see
[`src/tau_emotion/data_model/tasks.py`](../src/tau_emotion/data_model/tasks.py))
has an `id` (e.g. `airline_test_0029`), a `split` (`test` or `train`), a
`user_scenario` and `evaluation_criteria`.

The `user_scenario` holds what the user simulator gets:

| Field | What it is | Used by |
|-------|-----------|---------|
| `instructions` | The user's goal and the facts they know. | The user simulator |
| `emotion_instruction` | How the user behaves, e.g. "You're tired of delays and make that clear." | The user simulator, which acts it out |
| `emotion_metadata` | Labels: `emotion_family`, `emotion_leaf`, `dimension_politeness`, `dimension_urgency`, `dimension_trust_in_agent`. | Analysis only; never shown to the simulator |

The `evaluation_criteria` has five fields:

| Field | What it is | When it gates the reward |
|-------|-----------|--------------------------|
| `actions` | A list of `Action`s recording **one** reference trajectory of tool calls that solves the task. Always replayed on a fresh "gold" environment to derive the target DB end state. Other trajectories may produce an equivalent end state and also pass. | Only when `RewardType.ACTION` is in `reward_basis` (then each entry must also appear among the agent's tool calls — i.e., this list is treated as the only acceptable trajectory). |
| `env_assertions` | A list of assertions to run against the predicted environment after the simulation. | Only when `RewardType.ENV_ASSERTION` is in `reward_basis`. |
| `communicate_info` | A list of strings the agent must say to the user (case-insensitive substring match). | Only when `RewardType.COMMUNICATE` is in `reward_basis`. |
| `nl_assertions` | Natural-language assertions judged by an LLM. | Only when `RewardType.NL_ASSERTION` is in `reward_basis`. (Experimental / WIP.) |
| `reward_basis` | The list of `RewardType`s that gate the final reward. | Always. Default is `[DB, COMMUNICATE]`. |

The reward components are evaluated by:

| `RewardType` | Evaluator | What it checks |
|--------------|-----------|----------------|
| `DB` | `EnvironmentEvaluator` | After the simulation, does the predicted environment's DB hash match the target DB hash (target = fresh env + replay of `evaluation_criteria.actions`)? Any agent trajectory that produces an equivalent end state passes. |
| `ENV_ASSERTION` | `EnvironmentEvaluator` | Do all `env_assertions` pass on the predicted environment? |
| `COMMUNICATE` | `CommunicateEvaluator` | Does every string in `communicate_info` appear in the agent's messages? |
| `NL_ASSERTION` | `NLAssertionsEvaluator` | Does an LLM judge return true for every entry in `nl_assertions`? (WIP) |
| `ACTION` | `ActionEvaluator` | For every entry in `actions`, did the agent produce a matching tool call (per `Action.compare_with_tool_call`)? Use this only when you are confident `actions` enumerates the only acceptable trajectory. |

The final reward is the product. So if `reward_basis = [DB, COMMUNICATE]`,
the reward is `db_reward * communicate_reward`. `actions` is consumed
silently by `EnvironmentEvaluator` to set up the target environment, but
the agent's tool-call trajectory is never directly compared to it.

In the shipped tasks `communicate_info` is empty, so `communicate_reward`
is always 1.0 and the score comes down to the DB check.

### Train tasks

Train tasks (`tasks_train.json`, `split: "train"`) reference records that
exist only in `db_train.json`. The runner builds both the predicted and
the gold environment on that database for them, so they are scored the
same way as test tasks.

## How a run ends, and what it scores

The evaluator first looks at why the conversation ended
(`simulation.termination_reason`, see
[`src/tau_emotion/evaluator/evaluator.py`](../src/tau_emotion/evaluator/evaluator.py)):

| Termination | Reward |
|-------------|--------|
| `user_unsatisfied`: the simulated user wrote `###UNSATISFIED###`, giving up because the agent ignored their emotional needs, eroded trust, or created friction | **-1** (`USER_UNSATISFIED_REWARD`), no other check runs |
| `user_stop` (`###STOP###` and the other user stop tokens) or `agent_stop` (including a call to a transfer tool such as `transfer_to_human_agents`, which ends the conversation) | scored with `reward_basis` as described above |
| anything else (`max_steps`, `too_many_errors`, `timeout`, errors) | **0** |

The -1 sits below the 0 of a run that simply failed or ran out of steps,
so an agent that drives an emotional user away scores worse than one that
leaves the task unfinished.

## How a conversation runs

The benchmark follows [τ-bench](https://github.com/sierra-research/tau-bench)'s
conventions:

- the agent's system prompt is the domain policy alone;
- the user simulator uses τ-bench's user prompt, with the task's instructions
  followed by its `Emotion Instruction:`;
- the saved conversation opens with the fixed greeting "Hi! How can I help you
  today?" as the user simulator's cue, but the agent's context starts at the
  user's first message;
- a transfer to a human agent ends the conversation;
- of several tool calls in one message, only the first runs;
- an empty agent reply reaches the user as an empty message;
- the agent's reasoning goes back to the model with the next request;
- a run ends after 200 steps by default (`--max-steps`).

## Why `actions` looks like a requirement (and isn't)

`evaluation_criteria.actions` records *one* sequence of tool calls that
solves the task — typically how a task author or annotator solved it.
There is generally no claim that this is the only correct sequence, and
in many tasks several distinct trajectories produce an equivalent DB
end state (e.g., looking up a user before or after looking up a
reservation, or skipping a read-only lookup the agent doesn't actually
need). We keep this reference trajectory in the task because, for many
tasks, the target DB state is easier to express as "play these actions
on a fresh env" than to spell out by hand.

But because this list is also rendered to the agent in some debug views
and reads like a checklist, it is easy to misread as a list of *required*
agent actions. In practice, the only thing that matters for scoring is
whether the predicted DB end state matches the target DB end state (and,
for tasks that list `communicate_info`, whether those strings were said; no
shipped task lists any). An agent that takes a different (correct) path
through the tools — or no tool calls at all when the right answer is to
refuse — can still receive full reward.

This is **intended**: τ-bench scores on outcomes (`DB + COMMUNICATE`), not
on whether the agent followed a particular script. Switching the reward to
gate on `actions` would penalize correct-but-different solutions.

## A worked example: airline task `airline_test_0029`

From [`data/tau_emotion/domains/airline/tasks.json`](../data/tau_emotion/domains/airline/tasks.json)
(instructions shortened):

```json
{
  "id": "airline_test_0029",
  "split": "test",
  "user_scenario": {
    "instructions": "You are assisting Anya Sanchez (user_id: anya_sanchez_5251), who had a business class one-way flight from DFW to LAX on 2024-05-12 under reservation KDNMCS, which was cancelled. You want to issue a compensation certificate for this cancelled flight ...",
    "emotion_instruction": "You’re tired of delays and make that clear. You speak plainly, omitting unnecessary words. You want a resolution soon, without making threats or demands. You keep your expectations low about the agent’s help.",
    "emotion_metadata": {
      "emotion_family": "anger",
      "emotion_leaf": "exasperation",
      "dimension_politeness": "neutral",
      "dimension_urgency": "moderate",
      "dimension_trust_in_agent": "cautious"
    }
  },
  "evaluation_criteria": {
    "actions": [
      {
        "action_id": "29_0",
        "name": "send_certificate",
        "arguments": { "user_id": "anya_sanchez_5251", "amount": 100 }
      }
    ],
    "communicate_info": [],
    "reward_basis": ["DB", "COMMUNICATE"]
  }
}
```

What this means in practice:

- If the exasperated user gives up and writes `###UNSATISFIED###`, the
  reward is -1 whatever the database looks like.
- Otherwise `reward_basis = ["DB", "COMMUNICATE"]` → reward =
  `db_reward * communicate_reward`.
- `actions = [send_certificate(anya_sanchez_5251, 100)]`. `send_certificate`
  is a **write** tool (per its `tools.py` decorator), so replaying it on a
  fresh environment adds one $100 certificate to that user. The target DB
  hash is the initial DB plus that certificate.
- `db_reward = 1.0` iff the predicted DB ends in the same state: the agent
  issued exactly that certificate and made no other writes. A certificate
  of a different amount, a second certificate, or any other change (e.g.
  cancelling or modifying reservation `KDNMCS`) makes the hashes differ
  and `db_reward = 0.0`.
- Read-only lookups (`get_user_details`, `get_reservation_details`) are
  not in `actions` but don't change the DB, so the agent may make as many
  as it needs to check the policy before issuing the certificate.
- `communicate_info = []` → `communicate_reward = 1.0` automatically
  (nothing required to be said).

Net effect: the agent passes by reaching the right end state while keeping
an impatient, distrustful user in the conversation, whatever path it takes
through the tools.

## How to inspect action correctness anyway

Even when `ACTION` is not in `reward_basis`, the `ActionEvaluator` still
runs for diagnostic purposes:

- The CLI runner uses `EvaluationType.ALL` by default, which runs the
  `ActionEvaluator` on every run that is scored (not on `-1` or `0`
  terminations), so `action_checks` are populated on `RewardInfo`, and
  `partial_action_reward` summarizes how many of the listed reference
  actions were matched. These are surfaced by `tau-emotion view` (look for
  `Partial Action Reward: m/n`) and by the metrics functions in
  `src/tau_emotion/metrics/agent_metrics.py`. Note that this is a similarity
  signal against *one* reference trajectory, not a correctness verdict —
  an agent can score `0/n` on `partial_action_reward` and still be fully
  correct if it solved the task via a different sequence of tool calls.
- For a "did the agent reproduce this specific reference trajectory?"
  score, use `EvaluationType.ALL_IGNORE_BASIS` (or
  `ALL_WITH_NL_ASSERTIONS_IGNORE_BASIS`). These multiply ENV, ACTION,
  COMMUNICATE (and optionally NL) into a single number regardless of
  `reward_basis`. Same caveat: this measures similarity to one reference
  path, not whether the agent's behavior was correct. See
  [`src/tau_emotion/evaluator/evaluator.py`](../src/tau_emotion/evaluator/evaluator.py).
- The `partial_action_reward` property on `RewardInfo` further breaks
  down the action match rate by `ToolType.READ` vs `ToolType.WRITE`,
  which is useful for spotting "DB-passes-but-no-write-was-attempted"
  scenarios.

The benchmark score uses the task's `reward_basis` (and the -1/0
termination rules above) and is not changed by these diagnostic options.

## When does `RewardType.ACTION` get used?

None of the 10 domains' tasks put `ACTION` in `reward_basis`; their
evaluation is end-state only, by design. It appears only in a few tasks
of the `mock` test fixture.

If you build your own domain or task and want the agent's tool calls to
be a hard requirement (not just a side-effect on the DB), you can put
`RewardType.ACTION` in your task's `reward_basis`. Be aware that doing
so promotes `actions` from "one reference trajectory" to "the only
acceptable trajectory", so it should be reserved for tasks where you
have actually enumerated all valid solutions (or where there genuinely
is only one).

## Pointers

- Schema definitions: [`src/tau_emotion/data_model/tasks.py`](../src/tau_emotion/data_model/tasks.py)
- Evaluator source: [`src/tau_emotion/evaluator/`](../src/tau_emotion/evaluator/)
- Reward shape (`RewardInfo`, `ActionCheck`, etc.):
  [`src/tau_emotion/data_model/simulation.py`](../src/tau_emotion/data_model/simulation.py)
- User simulator rules for `###STOP###` and `###UNSATISFIED###`:
  `TAU_BENCH_SYSTEM_PROMPT` in [`src/tau_emotion/user/user_simulator.py`](../src/tau_emotion/user/user_simulator.py)
- Discussion of the `actions`-vs-`reward_basis` confusion:
  [issue #224][issue-224] and [RFC #129][issue-129].
