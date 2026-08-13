#!/usr/bin/env bash
# Start shared `grok agent leader` so one-shot grok -p clients can attach.
# ACP `serve` cannot use --leader (CLI exits immediately); seats stay --no-leader.
set -euo pipefail
export PATH="${HOME}/.grok/bin:${PATH:-}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STATE_DIR="${GCS_A2A_STATE:-$ROOT/.a2a-state}"
mkdir -p "$STATE_DIR"
PID_FILE="$STATE_DIR/grok-leader.pid"
LOG_FILE="$STATE_DIR/grok-leader.log"
SOCK="${HOME}/.grok/leader.sock"

pid_alive() { [[ -n "${1:-}" ]] && kill -0 "$1" 2>/dev/null; }

old=""
if [[ -f "$PID_FILE" ]]; then
  old="$(tr -d '[:space:]' <"$PID_FILE" || true)"
fi
if pid_alive "$old" && [[ -S "$SOCK" ]]; then
  echo "GROK_LEADER_ALREADY pid=$old sock=$SOCK"
  exit 0
fi
if [[ -S "$SOCK" ]] && ! pid_alive "$old"; then
  rm -f "$SOCK" || true
fi

if ! command -v grok >/dev/null 2>&1; then
  echo "GROK_LEADER_FAIL grok not on PATH" >&2
  exit 1
fi

{
  echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) START grok agent leader ====="
} >>"$LOG_FILE"

nohup grok agent leader --no-exit-on-disconnect --no-auto-update \
  >>"$LOG_FILE" 2>&1 &
echo $! >"$PID_FILE"
pid="$(tr -d '[:space:]' <"$PID_FILE")"

ok=0
for _ in $(seq 1 40); do
  if ! pid_alive "$pid"; then
    echo "GROK_LEADER_FAIL died during start; see $LOG_FILE" >&2
    exit 1
  fi
  if [[ -S "$SOCK" ]]; then
    ok=1
    break
  fi
  sleep 0.25
done
if [[ "$ok" != "1" ]]; then
  echo "GROK_LEADER_FAIL sock not ready; see $LOG_FILE" >&2
  exit 1
fi
echo "GROK_LEADER_START pid=$pid sock=$SOCK log=$LOG_FILE"
