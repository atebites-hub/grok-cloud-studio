#!/usr/bin/env bash
# Inner loop for board-writer. Must be started with argv0=cursor-agent:
#   exec -a cursor-agent bash board-writer-loop.sh
# Never runs `ak start`.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${GCS_ROOT:-$SCRIPT_DIR/../../..}" && pwd)"
STATE_DIR="${GCS_A2A_STATE:-$ROOT/.a2a-state}"
AK_DIR="$STATE_DIR/agent-kanban"
POLL_RAW="${AK_BRIDGE_POLL_SEC:-${GCS_AK_POLL_SEC:-60}}"
# Floor: never poll faster than 60s (RAM / API light).
POLL_SEC="$POLL_RAW"
if ! [[ "$POLL_SEC" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  POLL_SEC=60
fi
if awk "BEGIN {exit !($POLL_SEC < 60)}" >/dev/null 2>&1; then
  POLL_SEC=60
fi

export PATH="${HOME}/.local/bin:${PATH:-}"
export CURSOR_AGENT=1
export GCS_ROOT="$ROOT"
export GCS_A2A_STATE="$STATE_DIR"
export AGENT_KANBAN_BOARD_ID="${AGENT_KANBAN_BOARD_ID:-${GCS_AGENT_KANBAN_BOARD_ID:-zl2g1hym}}"

mkdir -p "$AK_DIR"

echo "AK_WRITER_LOOP_START poll=${POLL_SEC}s board=${AGENT_KANBAN_BOARD_ID} argv0=$(ps -p $$ -o comm= 2>/dev/null || echo unknown)"

if [[ -f "$SCRIPT_DIR/configure-ak.sh" ]]; then
  bash "$SCRIPT_DIR/configure-ak.sh" || echo "AK_WRITER_WARN configure-ak failed (continuing)" >&2
fi

if command -v ak >/dev/null 2>&1; then
  if ak auth login --leader-agent --username donald --name "Donald" >/tmp/ak-leader-login.out 2>/tmp/ak-leader-login.err; then
    echo "AK_WRITER_LEADER_OK"
  else
    python3 - <<'PYRED' || true
from pathlib import Path
import re
p = Path("/tmp/ak-leader-login.err")
t = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
t = re.sub(r"(?i)(api[_-]?key|authorization|bearer)\s*[:=]\s*\S+", r"\1=[REDACTED]", t)
print("AK_WRITER_LEADER_FAIL", t[-400:].replace("\n", " | "))
PYRED
  fi
else
  echo "AK_WRITER_ERR ak_missing" >&2
fi

BRIDGE="$SCRIPT_DIR/fleet-bridge.py"
while true; do
  if [[ -f "$BRIDGE" ]]; then
    python3 "$BRIDGE" --once --force || echo "AK_WRITER_WARN bridge_once_failed" >&2
  else
    echo "AK_WRITER_ERR missing $BRIDGE" >&2
  fi
  sleep "$POLL_SEC"
done
