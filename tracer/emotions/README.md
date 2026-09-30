# Emotions

Generates persona instructions for simulated customers: one request per persona
spec (emotion family and leaf from `emotion_persona_schema.json`, times every
politeness, urgency and trust value; 594 specs), each asking for
`instructions_per_spec` variants.

Two ways to send the requests:

- **OpenAI Batch API** (`submit` / `status` / `wait-download`): asynchronous,
  batch pricing, up to 24 hours.
- **Direct** (`run`): the same requests through chat completions, in parallel.
  Use it with any OpenAI-compatible server (vLLM or a hosted provider), which
  usually lacks the Batch API.

Both write the same merged file.

## Configuration (`config.json`)

Key fields to change:

| Field | Description |
|---|---|
| `model` | Model to use (e.g. `gpt-4.1`) |
| `instructions_per_spec` | Number of instruction variants per persona spec |
| `temperature` | Generation temperature (ignored for `gpt-5.*` models, forced to `1.0`) |
| `max_specs` | Cap number of specs (set to a small number for testing, `null` for all) |
| `api_base` | `run` only: OpenAI-compatible base URL (`null` = OpenAI, or `OPENAI_BASE_URL`) |
| `workers` | `run` only: parallel requests |

Every field can also be passed as a flag (`--model`, `--max-specs`, `--api-base`, ...).

## Usage

Run from `tracer/`. `OPENAI_API_KEY` must hold the key of the server you call.

```bash
# OpenAI Batch API
python emotions/build_emotion_persona_instructions_batch.py submit
python emotions/build_emotion_persona_instructions_batch.py status
python emotions/build_emotion_persona_instructions_batch.py wait-download

# Direct, on an OpenAI-compatible server
python emotions/build_emotion_persona_instructions_batch.py run \
  --api-base <url> \
  --model <model> \
  --workers 16
```

Output is written to `emotions/output/emotion_persona_instructions.json`
(`--output` to change it); `run` also keeps the raw responses next to the request
JSONL in `emotions/output/`.

Step 6 gives each task an instruction written for exactly its predicted spec, so
build the bank over all specs (`max_specs: null`) before exporting tasks; a
capped bank is only good for testing.
