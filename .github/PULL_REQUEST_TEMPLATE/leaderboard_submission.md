## Leaderboard submission

**Model:** <name, organization, link to the model card or API docs>
**Submission type:** standard / custom
**User simulators:** Qwen3-235B-A22B-Instruct-2507 / + GLM-5.2

### Trajectories

Link: <Hugging Face dataset or other public link>

Upload every run folder from `data/simulations/` that you passed to
`tau-emotion submit prepare`, keeping the folder structure.

### Checklist

- [ ] Only `submissions/<model>_<org>_<date>/submission.json` is in this PR
- [ ] `tau-emotion submit validate` passes on the uploaded trajectories
- [ ] The trajectories link is public and matches `trajectories_url` in submission.json
- [ ] All 10 domains, every task, at least 3 trials
- [ ] The model was not trained on τ-Emotion-Bench or Tracer tasks (or this is a custom submission)

### Custom submissions only

What changed and why:

Link to the code or paper (at a fixed commit):
