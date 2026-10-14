# Leaderboard submissions

Submit your model's results to the τ-Emotion-Bench leaderboard. You run the
benchmark, `tau-emotion submit prepare` turns the results into a `submission.json`,
and you open a pull request with it. The flow follows
[τ²-bench's](https://github.com/sierra-research/tau2-bench/blob/main/docs/leaderboard-submission.md).

## Requirements

`tau-emotion submit` checks all of these and rejects a submission that misses one.

- **Every domain:** all 10 domains, each run once.
- **Every task:** the full test split (`--task-split-name base`, the default). Don't
  use `--num-tasks` or `--task-ids`.
- **At least 3 trials:** `--num-trials 3` or more. Pass^1–3 are computed the same
  way for any number of trials; more trials only make them less noisy.
- **200 steps:** the default `--max-steps`.
- **The benchmark's user simulator:** `qwen3-235b-a22b-instruct-2507` at temperature
  0.0, the default when you leave out `--user-llm` and `--user-llm-args`. You may also
  run every domain a second time with `glm-5.2` (same settings), which fills the GLM
  tab of the leaderboard.
- **Unchanged benchmark:** the tasks, policies and user simulator prompt as released;
  no `--no-emotion`.
- **The same agent everywhere:** the same agent, model and arguments in every run.

## Standard and custom submissions

Like τ²-bench, a submission is **standard** or **custom**.

- **Standard:** any model, open weights or API, run through the default agent
  (`llm_agent`) with nothing changed.
- **Custom:** anything else on the agent side, such as your own agent (a ReAct loop,
  a planner, a router or ensemble), extra tools, or changed agent prompts. A model
  trained or fine-tuned on τ-Emotion-Bench or Tracer tasks is also custom. Custom
  submissions need notes on what changed and a link to the code or paper, and the
  leaderboard labels them.

No submission may change the tasks, the policies, the user simulator or the scoring.

## 1. Run the benchmark

Run each domain with the same settings
([models](models.md) explains how to reach the user simulator):

```bash
for domain in airline retail telecom telehealth bank basketball travel movie restaurant school; do
  tau-emotion run \
    --domain $domain \
    --agent-llm <your model> \
    --num-trials 3 \
    --user-api-base <url> --user-api-key <key>
done
```

Results are saved in `data/simulations/<domain>/<run>/`.

## 2. Prepare the submission

```bash
tau-emotion submit prepare data/simulations/*/<run> --output my_submission
```

It checks the runs against the requirements, computes Pass^1–3 and the average
reward for every domain and overall, and asks for the model name, organizations,
contact, where you will share the trajectories, and who served the user simulator.
It writes `my_submission/submission.json`.

## 3. Share the trajectories

The trajectories are the run folders from step 1. Upload them to a public place,
preferably a Hugging Face dataset, at the link you gave in step 2. They don't go in
the pull request. After review we copy them to the `tau-emotion-bench` Hugging Face
organization, so the leaderboard keeps linking to them.

## 4. Check it

```bash
tau-emotion submit validate my_submission/submission.json data/simulations/*/<run>
```

This repeats the checks and confirms the scores in `submission.json` match the
trajectories. We run the same command on the trajectories you share.

## 5. Open a pull request

Copy `submission.json` to `submissions/<model>_<organization>_<date>/submission.json`
(lowercase letters, digits, hyphens and underscores, e.g.
`qwen3-8b_qwen_2026-10-20`) and open a pull request with only that file. In the
description, describe the model, link the trajectories, and for a custom submission
explain what you changed.
