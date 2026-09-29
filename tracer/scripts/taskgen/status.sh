#!/usr/bin/env bash
# One-screen status of task generation.  bash scripts/taskgen/status.sh
cd "$(dirname "$0")/../.." || exit 1
source scripts/taskgen/common.sh
LOG=output/taskgen_logs

echo "tmux session : $(tmux has-session -t taskgen 2>/dev/null && echo RUNNING '(tmux attach -t taskgen)' || echo 'not running')"
for pf in "$LOG"/driver.*.pid; do [ -f "$pf" ] || continue
  pid=$(cat "$pf")
  echo "driver pid   : $pid $(kill -0 "$pid" 2>/dev/null && echo alive || echo "(stale)")"
done
echo
printf '%-12s %8s %8s %8s   %s\n' domain ok failed target log_tail
target=$(python3 -c "import json;c=json.load(open('$CONFIG'));print((c['end_index']-c['start_index'])*c['tasks_per_trace'])")
for d in $DOMAINS_ALL; do
  out=$(output_path "$d")
  [ -f "$out" ] || continue
  read -r ok failed <<<"$(python3 - "$out" <<'PY'
import json, sys
try:
    rows = json.load(open(sys.argv[1]))
    ok = sum(1 for r in rows if not r.get("failed", False))
    print(ok, len(rows) - ok)
except Exception:
    print(0, 0)
PY
)"
  tail=$(tail -n 1 "$LOG/${d}.log" 2>/dev/null | cut -c1-60)
  printf '%-12s %8s %8s %8s   %s\n' "$d" "$ok" "$failed" "$target" "$tail"
done
echo
echo "recent events:"; tail -n 6 "$LOG/STATUS.md" 2>/dev/null
