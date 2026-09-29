# =============================================================================
# SIMULATION DEFAULTS (overridable via CLI)
# =============================================================================
DEFAULT_MAX_STEPS = 200
# τ-bench puts no cap on tool errors: a run ends at its step limit, when the
# user stops, or when the agent transfers. tau2-bench's cap counts every tool
# error in the run (not consecutive ones) and scores the run 0 when it is
# reached, so a model that keeps sending a badly typed argument is cut off where
# τ-bench lets it recover. DEFAULT_MAX_STEPS bounds the tool calls anyway, so
# this default leaves the cap out of reach; lower it with --max-errors to get it
# back.
DEFAULT_MAX_ERRORS = DEFAULT_MAX_STEPS
DEFAULT_SEED = 300
DEFAULT_MAX_CONCURRENCY = 3
DEFAULT_NUM_TRIALS = 1
DEFAULT_SAVE_TO = None
DEFAULT_LOG_LEVEL = "ERROR"

# =============================================================================
# LLM DEFAULTS (overridable via CLI)
# =============================================================================
# Follow τ-bench's prompting, which TRACER verified the tasks with, so runs here
# match that setting: the agent's system prompt is the domain policy alone, the
# user simulator uses τ-bench's prompt and instruction format (as in
# tracer/tracer/envs/user.py), and the agent's context starts at the user's
# first message rather than the greeting it is seeded with. Set False for
# upstream tau2-bench behavior.
TAU_BENCH_PROMPTS = True

# Tools whose call ends the conversation, as τ-bench's `terminate_tools` do
# (tracer/tracer/envs/*/env.py): τ-bench runs the call, then scores the run on
# the database as it stands. Upstream tau2-bench instead waits for the user
# simulator to answer ###TRANSFER###, which τ-bench's user prompt never mentions,
# so without this the conversation runs on after a transfer and can still reach
# reward 1.
# Set to an empty frozenset for upstream tau2-bench behavior.
TAU_BENCH_TERMINATE_TOOLS = frozenset(
    {"transfer_to_human_agents", "transfer_to_human_support"}
)

# τ-bench's tool-calling agent keeps only the first of several tool calls sent
# in one message, in what it executes and in the history it carries forward
# (tracer/tracer/agents/tool_calling_agent.py: `tool_calls[:1]`).
# Set False to execute every call, as upstream tau2-bench does.
TAU_BENCH_SINGLE_TOOL_CALL = True

# τ-bench carries the assistant's own reasoning forward in the request history
# (it replays litellm's message dump, `reasoning_content` included), which
# changes the prompt for models whose chat template renders past reasoning.
# Set False for servers that reject the field.
TAU_BENCH_SEND_REASONING = True

# τ-bench turns an empty model reply into an empty message to the user and
# carries on (`message["content"] or ""`). tau2-bench raises instead, and the
# runner retries the whole conversation and finally records an infrastructure
# error, which is left out of the metrics. Set False to raise.
TAU_BENCH_EMPTY_AGENT_REPLY = True

DEFAULT_AGENT_IMPLEMENTATION = "llm_agent"
DEFAULT_USER_IMPLEMENTATION = "user_simulator"
DEFAULT_LLM_AGENT = "gpt-4.1-2025-04-14"
DEFAULT_LLM_USER = "qwen3-235b-a22b-instruct-2507"
DEFAULT_LLM_TEMPERATURE_AGENT = 0.0
DEFAULT_LLM_TEMPERATURE_USER = 0.7
DEFAULT_LLM_ARGS_AGENT = {"temperature": DEFAULT_LLM_TEMPERATURE_AGENT}
DEFAULT_LLM_ARGS_USER = {"temperature": DEFAULT_LLM_TEMPERATURE_USER}

DEFAULT_LLM_NL_ASSERTIONS = "gpt-4.1-2025-04-14"
DEFAULT_LLM_NL_ASSERTIONS_TEMPERATURE = 0.0
DEFAULT_LLM_NL_ASSERTIONS_ARGS = {"temperature": DEFAULT_LLM_NL_ASSERTIONS_TEMPERATURE}

DEFAULT_LLM_ENV_INTERFACE = "gpt-4.1-2025-04-14"
DEFAULT_LLM_ENV_INTERFACE_TEMPERATURE = 0.0
DEFAULT_LLM_ENV_INTERFACE_ARGS = {"temperature": DEFAULT_LLM_ENV_INTERFACE_TEMPERATURE}

DEFAULT_LLM_EVAL_USER_SIMULATOR = "claude-opus-4-5"

# LLM debug logging
DEFAULT_LLM_LOG_MODE = "latest"  # Options: "all", "latest"

# =============================================================================
# LLM INFRASTRUCTURE (fixed operational constants)
# =============================================================================
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_ATTEMPTS = 3
DEFAULT_RETRY_MIN_WAIT = 1.0  # seconds
DEFAULT_RETRY_MAX_WAIT = 10.0  # seconds
DEFAULT_RETRY_MULTIPLIER = 1.0  # exponential backoff multiplier

# LiteLLM cache
LLM_CACHE_ENABLED = False
DEFAULT_LLM_CACHE_TYPE = "redis"

# Redis (fixed infrastructure config)
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_PASSWORD = ""
REDIS_PREFIX = "tau_emotion"
REDIS_CACHE_VERSION = "v1"
REDIS_CACHE_TTL = 60 * 60 * 24 * 30

# Langfuse
USE_LANGFUSE = False

# =============================================================================
# API SERVICE (fixed)
# =============================================================================
API_PORT = 8000

# =============================================================================
# DISPLAY
# =============================================================================
TERM_DARK_MODE = True
