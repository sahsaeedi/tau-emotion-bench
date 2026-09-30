# emotion_analysis

Gives each task an emotion. It embeds the persona instructions from step 5, trains
a small classifier on them (emotion family, leaf, politeness, urgency, trust),
predicts those labels from each task's `feeling` (else its `instruction`), and
picks one persona instruction written for exactly the predicted spec
(`novel_emotion_prediction.selected_instruction`, which `export_tasks.py` reads).

## Config (`config.json`)

| Field | Description |
|---|---|
| `inputs.task_paths` | List of task JSON files to predict and visualize (one per domain) |
| `inputs.emotion_persona_instructions_path` | Path to emotion persona instructions JSON |
| `inputs.emotion_schema_path` | The persona schema from step 5 |
| `embedding_model.model` | LiteLLM model string, e.g. `"openai/text-embedding-3-small"` |
| `embedding_model.api_base` | Embedding endpoint; for an OpenAI-compatible server (vLLM or a hosted provider) set its URL and use `openai/<model>` (key: `OPENAI_API_KEY`) or `hosted_vllm/<model>` (key: `HOSTED_VLLM_API_KEY`) |
| `outputs.root_dir` | Root directory for all outputs |
| `training.epochs` / `lr` / `hidden_dim` / `knn_k` | Training hyperparameters |
| `inference.task_output_suffix` | Suffix for output task files, e.g. `"_with_emotion_predictions.json"` |
| `visualization.max_tasks` | Cap on tasks per plot (`null` = no cap) |

Relative paths are relative to `tracer/`. Keys are read from `tracer/.env` or the
environment. Training uses a GPU when torch finds one, else the CPU.

## Run

```bash
python emotion_analysis/run_all.py --config emotion_analysis/config.json
```

**Outputs** (under `outputs.root_dir/llm/{provider}/{model}/`):

- `emotion_embeddings.json` — encoded emotion instruction vectors
- `trained_encoder.pt` / `knn_models.pt` — trained classifier + kNN models
- `label_maps.json`, `training_metadata.json`, `training_metrics.json`, `learning_curves.{csv,png}` — training record
- `task_prediction_outputs.json` — list of written prediction file paths
- `<task_stem>_with_emotion_predictions.json` — original task file with `novel_emotion_prediction` added to each task (written next to the input file)
- `analysis/instruction_model_output_tsne.png` — t-SNE of instructions only, colored by emotion family
- `analysis/instruction_vs_<task_stem>_tsne_knn_regions.png` — one plot per task file: t-SNE with kNN decision regions in 2D (task colors match the field)

A task whose predicted spec has no instruction in the bank (only when step 5 was
capped with `max_specs`) gets `selected_instruction: null` and is skipped at export.

Each stage also runs on its own, with the same `--config`: `encode_emotions.py`,
`train_encoder.py`, `encode_task_feelings.py`, `visualize_instruction_tsne.py`,
`visualize_instruction_vs_task_tsne_knn_regions.py`.

## Optional plots

To combine the per-task-file region plots into one figure (one panel per file in
`inputs.task_paths`), run after `run_all.py`:

```bash
python emotion_analysis/visualize_combined_grid.py --config emotion_analysis/config.json
```

It writes `analysis/instruction_vs_task_tsne_knn_regions_grid.{png,pdf}`.

A t-SNE of the classifier's hidden space, with every task file's tasks on it:

```bash
python emotion_analysis/visualize_learned_tsne.py --config emotion_analysis/config.json
```

It writes `analysis/learned_space_tsne.png`.
