# Emotions

Generates persona instructions for simulated customers using the OpenAI Batch API.

## Configuration (`config.json`)

Key fields to change:

| Field | Description |
|---|---|
| `model` | OpenAI model to use (e.g. `gpt-4.1`) |
| `instructions_per_spec` | Number of instruction variants per persona spec |
| `temperature` | Generation temperature (ignored for `gpt-5.*` models, forced to `1.0`) |
| `max_specs` | Cap number of specs (set to a small number for testing, `null` for all) |

## Usage

```bash
# Submit batch job
python emotions/build_emotion_persona_instructions_batch.py submit

# Check status
python emotions/build_emotion_persona_instructions_batch.py status

# Wait for completion and download results
python emotions/build_emotion_persona_instructions_batch.py wait-download
```

Output is written to `emotions/output/emotion_persona_instructions.json`.
Batch jobs can take up to 24 hours to complete.
