# Leaderboard submissions

Submit your model's results to the τ-Emotion-Bench leaderboard. You run the
benchmark, `tau-emotion submit prepare` turns the results into a `submission.json`,
and you paste it into a submission form on GitHub. The flow follows
[τ²-bench's](https://github.com/sierra-research/tau2-bench/blob/main/docs/leaderboard-submission.md).

## Requirements

`tau-emotion submit` checks all of these and rejects a submission that misses one.

- **Every domain:** all 10 domains, each run once per user simulator.
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

For the optional GLM tab, run every domain again with `--user-llm glm-5.2` (and that
model's `--user-api-base` and `--user-api-key`). These runs are saved in their own
folders, `data/simulations/<domain>/<run>_user-glm-5.2/` (the user model's name as
you passed it, with `/` replaced by `_`).

## 2. Prepare the submission

```bash
tau-emotion submit prepare data/simulations/*/<run> --output my_submission
```

With GLM runs, pass those folders too:
`data/simulations/*/<run> data/simulations/*/<run>_user-glm-5.2`.

It checks the runs against the requirements, computes Pass^1–3 and the average
reward for every domain, and Avg@3 (the mean of the domains' Pass^1) and Avg^3
(the mean of their Pass^3), and asks for the model name, organizations, contact,
and who served the user simulator. It writes `my_submission/submission.json` and
your trajectories, every conversation behind the scores, as
`my_submission/trajectories.zip`: about 15 MB for a full run. When they are over
GitHub's 25 MB limit for an attachment, it splits them into `trajectories-1.zip`,
`trajectories-2.zip`, and so on.

## 3. Check it

```bash
tau-emotion submit validate my_submission/submission.json my_submission/*.zip
```

This repeats the checks, scores every conversation again, and confirms the scores
in `submission.json` match.

## 4. Submit

Open the [submission form](https://github.com/sahsaeedi/tau-emotion-bench/issues/new?template=leaderboard_submission.yml),
paste `submission.json` into it, and drag in the zip files. For a custom
submission, also say what you changed.

Within about 15 minutes a check runs the same validation on your zip files and
comments the result on the issue. If it finds problems, fix them and edit the
issue (new zip files or `submission.json`) to check it again. We also check a
sample of the user turns against the user simulator, then add the model to the
leaderboard, with your trajectories downloadable from it.

`prepare` tells you if a single zip is still over 25 MB, which takes far longer
conversations than usual. Upload that one somewhere public instead and put its
direct-download link in the form's *Trajectories link* field.
