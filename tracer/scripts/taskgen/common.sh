# Shared settings for the taskgen scripts; source it after cd-ing to tracer/.
#
#   CONFIG     generator settings shared by every domain   (default scripts/taskgen/configs/generator.json)
#   SPLIT      test or train                                (default test)
#   TRACE_DIR  where each domain's traces file is           (default output/traces)
#
# Per domain, the traces file is the one file in $TRACE_DIR named <domain>_*traces.json
# (build_trace.py names it after the graph), and tasks go to
# output/tasks/$SPLIT/<domain>_$SPLIT_tasks.json.

CONFIG=${CONFIG:-scripts/taskgen/configs/generator.json}
SPLIT=${SPLIT:-test}
TRACE_DIR=${TRACE_DIR:-output/traces}
DOMAINS_ALL="airline retail telecom telehealth bank basketball movie restaurant school travel"

trace_path() {  # <domain> -> prints the traces file, or fails if there isn't exactly one
  local matches=("$TRACE_DIR/$1"_*traces.json)
  if [ ! -e "${matches[0]}" ]; then
    echo "no traces for $1 in $TRACE_DIR (expected $TRACE_DIR/$1_*traces.json)" >&2; return 1
  fi
  if [ "${#matches[@]}" -gt 1 ]; then
    echo "several traces for $1 in $TRACE_DIR: ${matches[*]}" >&2; return 1
  fi
  echo "${matches[0]}"
}

output_path() { echo "output/tasks/$SPLIT/$1_${SPLIT}_tasks.json"; }

generator_args() {  # <domain> -> the generator's per-domain flags
  local trace; trace=$(trace_path "$1") || return 1
  echo --config "$CONFIG" --env "$1" --split "$SPLIT" --trace-path "$trace" --output-path "$(output_path "$1")"
}
