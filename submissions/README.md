# Leaderboard submissions

Each accepted submission is a folder here, `<model>_<organization>_<date>/submission.json`
(lowercase letters, digits, hyphens and underscores, e.g. `qwen3-8b_qwen_2026-10-20`).
The leaderboard is built from these files.

Submitters don't add folders here themselves; they open a
[submission issue](https://github.com/sahsaeedi/tau-emotion-bench/issues/new?template=leaderboard_submission.yml)
(see the [submission guide](../docs/leaderboard-submission.md)).

## Accepting a submission

1. Download the trajectories from the issue's link and save its submission.json.
2. Check them (optional; any submission can be accepted without it):

   ```bash
   tau-emotion submit validate submission.json <trajectory folders>
   tau-emotion submit validate submission.json <trajectory folders> --check-user-sim
   ```

   The first command checks the runs against the requirements and scores every
   conversation again. `--check-user-sim` also has the user simulators score a
   sample of user turns, through `OPENAI_API_BASE` (the ASU API).
3. Add `submissions/<model>_<organization>_<date>/submission.json`, commit it to
   `main`, and close the issue.
