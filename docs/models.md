# Models and endpoints

Every model call goes through [LiteLLM](https://github.com/BerriAI/litellm), so any
provider it supports works for the agent, the user simulator and the review judge.

## API keys

Put the keys you need in `.env` (copy `.env.example`):

```bash
OPENAI_API_KEY=...        # OpenAI models (and the key sent to OPENAI_API_BASE)
ANTHROPIC_API_KEY=...     # Claude models (e.g. the default review judge)
OPENAI_API_BASE=...       # optional: sends every OpenAI model elsewhere, see below
```

## OpenAI-compatible servers

Open-weight models are usually served by vLLM or a hosted provider behind an
OpenAI-compatible API. Model names LiteLLM doesn't know (e.g.
`qwen3-235b-a22b-instruct-2507`) are sent to the OpenAI provider, and you point
each side at its server per run:

| Flag | What it does |
|---|---|
| `--agent-api-base`, `--user-api-base` | The server's URL, e.g. `http://localhost:8000/v1` |
| `--agent-api-key`, `--user-api-key` | The key for that server. Never saved in the results |

With `--<side>-api-base` and no `--<side>-api-key`, the placeholder key `EMPTY` is
sent, so your OpenAI key never reaches that server.

`OPENAI_API_BASE` redirects **every** OpenAI model to that server, the names
LiteLLM knows (`gpt-4.1`, `gpt-4.1-mini`) as well, together with `OPENAI_API_KEY`.
Set it only when all the OpenAI-provider models of a run are on that server. To use
OpenAI models and another server in the same run, leave `OPENAI_API_BASE` unset and
pass `--user-api-base`/`--user-api-key` (or `--agent-api-base`/`--agent-api-key`)
for the side on the other server:

```bash
tau-emotion run --domain airline --agent-llm gpt-4.1 \
  --user-api-base <url> --user-api-key <key>
```

## The user simulator

The benchmark's user simulator is `qwen3-235b-a22b-instruct-2507` at temperature
0.7, the default when you leave out `--user-llm`. Use it when you compare against
reported scores. OpenAI and Anthropic don't serve it, so it needs
`--user-api-base` (or `OPENAI_API_BASE`, see above) pointing at a server that does.

## Reasoning models

- `--agent-enable-thinking` / `--no-agent-enable-thinking` (and the same for the
  user) set vLLM's `chat_template_kwargs.enable_thinking`, and the agent's setting
  is added to the run's folder name. Without either flag, the model's own default
  applies.
- Models whose chat template uses a different switch take it through
  `--agent-llm-args`, e.g.
  `'{"temperature": 0.0, "extra_body": {"chat_template_kwargs": {...}}}'`.
  `--agent-llm-args` replaces the default args, so keep the temperature in it (or
  add `--agent-temperature 0`).
- If the server runs no reasoning parser, the reasoning stays in the reply text.
  A leading `<think>…</think>` block is removed before the other side reads the
  reply. Gemma 4's markers are special tokens, so they need
  `"extra_body": {"skip_special_tokens": false}` to be found and removed.
