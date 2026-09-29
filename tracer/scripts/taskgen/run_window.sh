#!/usr/bin/env bash
# One domain run of tracer.generator, meant to be one tmux window.
#
#   bash scripts/taskgen/run_window.sh <domain> <log_dir>
#
# Settings (config, split, traces folder) come from scripts/taskgen/common.sh.
# The pane shows the progress bar and failures (stderr); the --debug per-step agent
# output goes to <log_dir>/<domain>.log. Resumable: re-running the same command skips
# completed (task_id, run) pairs in the domain's output file.
set -u
cd "$(dirname "$0")/../.." || exit 1
source scripts/taskgen/common.sh

d=$1
logdir=$2
PY=${PY:-python}  # override with PY=/path/to/python
args=$(generator_args "$d") || exit 1
read -ra args <<<"$args"
mkdir -p "$(dirname "$(output_path "$d")")"

mkdir -p "$logdir"
STATUS=$logdir/STATUS.md
log_event() { printf '| %s | %s | %s |\n' "$(date '+%F %T')" "$d" "$1" >> "$STATUS"; }
[ -s "$STATUS" ] || printf '| time | domain | event |\n|---|---|---|\n' > "$STATUS"

log_event "started pid=$$ split=$SPLIT"
"$PY" -u -m tracer.generator "${args[@]}" --debug > "$logdir/$d.log"
rc=$?
log_event "exited rc=$rc"

echo
echo "[$d] generator exited rc=$rc  (log: $logdir/$d.log)"
echo "re-run to resume: bash scripts/taskgen/run_window.sh $d $logdir"
exec bash
