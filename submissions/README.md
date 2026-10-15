# Leaderboard submissions

Each accepted submission is a folder here, `<model>_<organization>_<date>/submission.json`,
and `leaderboard.json` gathers them all for the leaderboard page. Each submission's
trajectories are a zip on the [`submissions` release](https://github.com/sahsaeedi/tau-emotion-bench/releases/tag/submissions),
linked from its `trajectories_url`.

Submitters open a
[submission issue](https://github.com/sahsaeedi/tau-emotion-bench/issues/new?template=leaderboard_submission.yml)
with `submission.json` and their trajectory zips (see the
[submission guide](../docs/leaderboard-submission.md)).

## What runs by itself

- **Check** (`.github/workflows/submission-check.yml`): when a submission issue is
  opened or edited, it runs `tau-emotion submit validate` on the attached zips,
  comments the problems and scores, and labels the issue `valid` or `needs-changes`.
- **Accept** (`.github/workflows/submission-accept.yml`): adding the `accepted`
  label adds the submission folder here, uploads its trajectories to the release,
  rebuilds `leaderboard.json`, and closes the issue. It works whether or not the
  check passed; `validated` in submission.json records which.
- **Leaderboard** (`.github/workflows/leaderboard.yml`): rebuilds `leaderboard.json`
  when a submission.json here is added, changed or removed by hand.

## Reviewing a submission

1. Read the check's comment on the issue.
2. Optionally, check the user simulator, which the workflow can't (it needs the
   ASU API): download the zips and run

   ```bash
   tau-emotion submit validate submission.json trajectories*.zip --check-user-sim
   ```

   with `OPENAI_API_BASE` and `OPENAI_API_KEY` set for the ASU API.
3. Add the `accepted` label, or comment what has to change.

To add or change a submission by hand instead, commit its folder here; the
leaderboard workflow rebuilds `leaderboard.json`, or run `tau-emotion submit leaderboard`.
