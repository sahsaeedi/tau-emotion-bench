# emotion_analysis

## Config (`config.json`)

| Field | Description |
|---|---|
| `inputs.task_paths` | List of task JSON files to predict and visualize (one per domain) |
| `inputs.emotion_persona_instructions_path` | Path to emotion persona instructions JSON |
| `embedding_model.model` | LiteLLM model string, e.g. `"openai/text-embedding-3-small"` |
| `outputs.root_dir` | Root directory for all outputs |
| `training.epochs` / `lr` / `hidden_dim` / `knn_k` | Training hyperparameters |
| `inference.task_output_suffix` | Suffix for output task files, e.g. `"_with_emotion_predictions.json"` |
| `visualization.max_tasks` | Cap on tasks per plot (`null` = no cap) |

## Run

```bash
python emotion_analysis/run_all.py --config emotion_analysis/config.json
```

**Outputs** (under `outputs.root_dir/llm/{provider}/{model}/`):

- `emotion_embeddings.json` — encoded emotion instruction vectors
- `trained_encoder.pt` / `knn_models.pt` — trained classifier + kNN models
- `task_prediction_outputs.json` — list of written prediction file paths
- `<task_stem>_with_emotion_predictions.json` — original task file with `novel_emotion_prediction` added to each task (written next to the input file)
- `analysis/instruction_model_output_tsne.png` — t-SNE of instructions only, colored by emotion family
- `analysis/instruction_vs_<task_stem>_tsne_knn_regions.png` — one plot per task file: t-SNE with kNN decision regions in 2D (task colors match the field)
