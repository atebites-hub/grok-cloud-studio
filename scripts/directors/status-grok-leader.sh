#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STATE_DIR="${GCS_A2A_STATE:-$ROOT/.a2a-state}"
PID_FILE="$STATE_DIR/grok-leader.pid"
SOCK="${HOME}/.grok/leader.sock"
pid="$(tr -d '[:space:]' <"$PID_FILE" 2>/dev/null || true)"
if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null && [[ -S "$SOCK" ]]; then
  echo "GROK_LEADER_STATUS state=up pid=$pid sock=$SOCK"
  exit 0
fi
echo "GROK_LEADER_STATUS state=down pid=${pid:-none} sock=$SOCK"
exit 1
