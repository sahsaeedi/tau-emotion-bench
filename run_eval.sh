#!/usr/bin/env bash
# Run one tau-emotion evaluation: one domain, one agent model.
#
# Edit the defaults below, or override any of them on the command line:
#
#   ./run_eval.sh --domain bank --output runs/qwen3-235b/bank
#   ./run_eval.sh --domain school --output runs/qwen3-8b/school \
#       --agent-model qwen3-8b --agent-thinking on --agent-temperature 0.0
#
# Results go to <output>/results.json, with the console log in <output>/run.log.
# A relative --output is taken from the directory you run the script in.
# Rerunning with the same --output resumes: finished rows are kept and only
# infrastructure-error rows are rerun. A higher --trials or --num-tasks adds
# trials or tasks. A changed model, temperature, seed or max steps is refused on
# resume, and so are removed tasks (a lower --num-tasks, another --split): use a
# new --output for those.
set -euo pipefail

# ---- settings --------------------------------------------------------------
DOMAIN=""                                   # bank, restaurant, movie, school, ...
OUTPUT=""                                   # results directory

AGENT_MODEL="qwen3-235b-a22b-instruct-2507"
AGENT_API_BASE=""                           # empty: OPENAI_API_BASE from .env, or the provider
AGENT_API_KEY=""                            # empty: OPENAI_API_KEY from .env
AGENT_TEMPERATURE="0.0"                     # empty: send no temperature
AGENT_THINKING=""                           # on, off, or empty for the model default

USER_MODEL="qwen3-235b-a22b-instruct-2507"
USER_API_BASE=""                            # empty: OPENAI_API_BASE from .env, or the provider
USER_API_KEY=""                             # empty: OPENAI_API_KEY from .env
USER_TEMPERATURE="0.0"                      # empty: send no temperature

TRIALS=3
NUM_TASKS=""                                # empty: every task in the split
CONCURRENCY=4
MAX_STEPS=200
SPLIT="test"                                # test or train
# ----------------------------------------------------------------------------

while [ $# -gt 0 ]; do
    case "$1" in -h|--help) sed -n '2,16p' "$0"; exit 0 ;; esac
    [ $# -ge 2 ] || { echo "$1 needs a value" >&2; exit 2; }
    case "$1" in
        --domain)            DOMAIN=$2 ;;
        --output)            OUTPUT=$2 ;;
        --agent-model)       AGENT_MODEL=$2 ;;
        --agent-api-base)    AGENT_API_BASE=$2 ;;
        --agent-api-key)     AGENT_API_KEY=$2 ;;
        --agent-temperature) AGENT_TEMPERATURE=$2 ;;
        --agent-thinking)    AGENT_THINKING=$2 ;;
        --user-model)        USER_MODEL=$2 ;;
        --user-api-base)     USER_API_BASE=$2 ;;
        --user-api-key)      USER_API_KEY=$2 ;;
        --user-temperature)  USER_TEMPERATURE=$2 ;;
        --trials)            TRIALS=$2 ;;
        --num-tasks)         NUM_TASKS=$2 ;;
        --concurrency)       CONCURRENCY=$2 ;;
        --max-steps)         MAX_STEPS=$2 ;;
        --split)             SPLIT=$2 ;;
        *) echo "unknown option: $1 (see --help)" >&2; exit 2 ;;
    esac
    shift 2
done

[ -n "$DOMAIN" ] || { echo "--domain is required" >&2; exit 2; }
[ -n "$OUTPUT" ] || { echo "--output is required" >&2; exit 2; }

case "$AGENT_THINKING" in
    on)  THINKING=(--agent-enable-thinking) ;;
    off) THINKING=(--no-agent-enable-thinking) ;;
    "")  THINKING=() ;;
    *)   echo "--agent-thinking must be on, off or empty" >&2; exit 2 ;;
esac

case "$SPLIT" in
    test|train) ;;
    *) echo "--split must be test or train" >&2; exit 2 ;;
esac

mkdir -p "$OUTPUT"
OUTPUT=$(cd "$OUTPUT" && pwd)   # before the cd below, so relative means "from here"

HERE=$(cd "$(dirname "$0")" && pwd)
cd "$HERE"

# .env can't be sourced (it has <placeholder> values), so read the key directly.
env_value() { { grep -m1 "^$1=" .env 2>/dev/null || true; } | cut -d= -f2- | tr -d '"'; }
AGENT_API_KEY=${AGENT_API_KEY:-$(env_value OPENAI_API_KEY)}
USER_API_KEY=${USER_API_KEY:-$(env_value OPENAI_API_KEY)}

# An empty temperature sends {}, so the server's own default applies.
llm_args() { if [ -n "$1" ]; then echo "{\"temperature\": $1}"; else echo "{}"; fi; }

# With an api base, always pass the key too: base without key sends "EMPTY".
# An empty base passes neither, so OPENAI_API_BASE / OPENAI_API_KEY from .env apply.
AGENT_ENDPOINT=()
USER_ENDPOINT=()
if [ -n "$AGENT_API_BASE" ]; then
    AGENT_ENDPOINT=(--agent-api-base "$AGENT_API_BASE" --agent-api-key "$AGENT_API_KEY")
fi
if [ -n "$USER_API_BASE" ]; then
    USER_ENDPOINT=(--user-api-base "$USER_API_BASE" --user-api-key "$USER_API_KEY")
fi

TASKS=()
if [ -n "$NUM_TASKS" ]; then
    TASKS=(--num-tasks "$NUM_TASKS")
fi

echo "[$(date '+%F %T')] domain=$DOMAIN agent=$AGENT_MODEL temp=${AGENT_TEMPERATURE:-unset} thinking=${AGENT_THINKING:-default} user=$USER_MODEL temp=${USER_TEMPERATURE:-unset} trials=$TRIALS tasks=${NUM_TASKS:-all} concurrency=$CONCURRENCY max_steps=$MAX_STEPS split=$SPLIT -> $OUTPUT" \
    | tee -a "$OUTPUT/run.log"

# The repo's .venv, else the tau-emotion on PATH (e.g. a pip-installed environment).
TAU_EMOTION="$HERE/.venv/bin/tau-emotion"
[ -x "$TAU_EMOTION" ] || TAU_EMOTION=$(command -v tau-emotion)

"$TAU_EMOTION" run \
    --domain "$DOMAIN" \
    --task-split-name "$SPLIT" \
    --agent-llm "$AGENT_MODEL" \
    --agent-llm-args "$(llm_args "$AGENT_TEMPERATURE")" \
    ${AGENT_ENDPOINT[@]+"${AGENT_ENDPOINT[@]}"} \
    ${THINKING[@]+"${THINKING[@]}"} \
    --user-llm "$USER_MODEL" \
    --user-llm-args "$(llm_args "$USER_TEMPERATURE")" \
    ${USER_ENDPOINT[@]+"${USER_ENDPOINT[@]}"} \
    --num-trials "$TRIALS" \
    ${TASKS[@]+"${TASKS[@]}"} \
    --max-concurrency "$CONCURRENCY" \
    --max-steps "$MAX_STEPS" \
    --auto-resume \
    --save-to "$OUTPUT" 2>&1 | tee -a "$OUTPUT/run.log"
