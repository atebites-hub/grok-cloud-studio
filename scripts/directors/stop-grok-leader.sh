#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STATE_DIR="${GCS_A2A_STATE:-$ROOT/.a2a-state}"
PID_FILE="$STATE_DIR/grok-leader.pid"
SOCK="${HOME}/.grok/leader.sock"
pid="$(tr -d '[:space:]' <"$PID_FILE" 2>/dev/null || true)"
if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
  kill "$pid" 2>/dev/null || true
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.2
  done
  kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null || true
  echo "GROK_LEADER_STOP pid=$pid"
else
  echo "GROK_LEADER_STOP already-down"
fi
rm -f "$PID_FILE"
# leave sock for grok to clean; remove if stale
[[ -S "$SOCK" ]] && ! kill -0 "$pid" 2>/dev/null && rm -f "$SOCK" || true
