# Models and endpoints

Every model call goes through [LiteLLM](https://github.com/BerriAI/litellm), so any
provider it supports works for the agent, the user simulator and the review judge.

## API keys

Put the keys you need in `.env` (copy `.env.example`):

```bash
OPENAI_API_KEY=...        # OpenAI models, and the key for OPENAI_API_BASE
ANTHROPIC_API_KEY=...     # Claude models (e.g. the default review judge)
OPENAI_API_BASE=...       # optional: an OpenAI-compatible server, see below
```

## OpenAI-compatible servers

Open-weight models are usually served by vLLM or a hosted provider behind an
OpenAI-compatible API. Set `OPENAI_API_BASE` to that server's URL: model names
LiteLLM doesn't know (e.g. `qwen3-235b-a22b-instruct-2507`) are sent there.

To put the agent and the user simulator on different servers, pass them per run:

| Flag | What it does |
|---|---|
| `--agent-api-base`, `--user-api-base` | The server's URL, e.g. `http://localhost:8000/v1` |
| `--agent-api-key`, `--user-api-key` | The key for that server. Never saved in the results |

## The user simulator

The benchmark's user simulator is `qwen3-235b-a22b-instruct-2507` at temperature
0.7, the default when you leave out `--user-llm`. Use it when you compare against
reported scores. OpenAI and Anthropic don't serve it, so it needs
`OPENAI_API_BASE` (or `--user-api-base`) pointing at a server that does.

## Reasoning models

- `--agent-enable-thinking` / `--no-agent-enable-thinking` (and the same for the
  user) set vLLM's `chat_template_kwargs.enable_thinking`, and the agent's setting
  is added to the run's folder name. Without either flag, the model's own default
  applies.
- Models whose chat template uses a different switch take it through
  `--agent-llm-args`, e.g. `'{"extra_body": {"chat_template_kwargs": {...}}}'`.
- If the server runs no reasoning parser, the reasoning stays in the reply text.
  A leading `<think>…</think>` block is removed before the other side reads the
  reply. Gemma 4's markers are special tokens, so they need
  `"extra_body": {"skip_special_tokens": false}` to be found and removed.
