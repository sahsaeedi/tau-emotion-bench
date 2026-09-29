#!/usr/bin/env bash
# Sequential, resumable task-generation driver.
#
#   bash scripts/taskgen/run_all.sh airline retail telecom telehealth
#
# Designed to outlive whatever shell launched it: run it inside tmux
#   tmux new-session -d -s taskgen "bash scripts/taskgen/run_all.sh <domains...>"
# and attach with `tmux attach -t taskgen` (Ctrl-b d to detach).
#
# tracer.generator checkpoints after every trace and skips completed (task_id, run)
# pairs on restart, so re-running this script after a crash resumes rather than
# repeats. Nothing here needs to be re-derived if the job dies mid-way.
#
# Settings (config, split, traces folder): scripts/taskgen/common.sh, e.g.
#   SPLIT=train bash scripts/taskgen/run_all.sh bank
#
# Per-domain output:  output/tasks/<split>/<domain>_<split>_tasks.json
# Per-domain log:     output/taskgen_logs/<domain>.log
# Event log:          output/taskgen_logs/STATUS.md
set -u
cd "$(dirname "$0")/../.." || exit 1
source scripts/taskgen/common.sh

LOG=output/taskgen_logs
STATUS=$LOG/STATUS.md
mkdir -p "$LOG"
echo $$ > "$LOG/driver.$$.pid"

count_ok() {  # successful (non-failed) tasks in a domain's output file
  python3 - "$1" <<'PY' 2>/dev/null || echo 0
import json, sys
try:
    rows = json.load(open(sys.argv[1]))
    print(sum(1 for r in rows if not r.get("failed", False)))
except Exception:
    print(0)
PY
}

log_event() { printf '| %s | %s | %s |\n' "$(date '+%F %T')" "$1" "$2" >> "$STATUS"; }

[ -s "$STATUS" ] || printf '| time | domain | event |\n|---|---|---|\n' > "$STATUS"
log_event "driver" "started pid=$$ domains=[$*]"

for d in "$@"; do
  if ! args=$(generator_args "$d"); then
    log_event "$d" "SKIPPED: no traces file in $TRACE_DIR"
    continue
  fi
  read -ra args <<<"$args"
  out=$(output_path "$d")
  mkdir -p "$(dirname "$out")"
  before=$(count_ok "$out")
  log_event "$d" "started (resuming from $before done)"

  # stdout (--debug: every agent step) -> log file; stderr (progress bar, failures) -> the tmux pane
  python -u -m tracer.generator "${args[@]}" --debug > "$LOG/${d}.log"
  rc=$?

  after=$(count_ok "$out")
  if [ $rc -eq 0 ]; then
    log_event "$d" "FINISHED ok tasks=$after (+$((after - before)) this run)"
  else
    log_event "$d" "EXITED rc=$rc tasks=$after -- re-run the same command to resume"
  fi
done

log_event "driver" "done"
rm -f "$LOG/driver.$$.pid"
