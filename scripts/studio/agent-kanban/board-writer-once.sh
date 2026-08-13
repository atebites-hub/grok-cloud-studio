#!/usr/bin/env bash
# One-shot board write under argv0=cursor-agent (invoked by board-writer.sh once).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${GCS_ROOT:-$SCRIPT_DIR/../../..}" && pwd)"
STATE_DIR="${GCS_A2A_STATE:-$ROOT/.a2a-state}"
export PATH="${HOME}/.local/bin:${PATH:-}"
export CURSOR_AGENT=1
export GCS_ROOT="$ROOT"
export GCS_A2A_STATE="$STATE_DIR"
export AGENT_KANBAN_BOARD_ID="${AGENT_KANBAN_BOARD_ID:-${GCS_AGENT_KANBAN_BOARD_ID:-zl2g1hym}}"

bash "$SCRIPT_DIR/configure-ak.sh" || true
if command -v ak >/dev/null 2>&1; then
  if ak auth login --leader-agent --username donald --name "Donald" >/tmp/ak-leader-once.out 2>/tmp/ak-leader-once.err; then
    echo "AK_WRITER_LEADER_OK"
  else
    echo "AK_WRITER_LEADER_FAIL"
    python3 - <<'PYRED' || true
from pathlib import Path
import re
p = Path("/tmp/ak-leader-once.err")
t = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
t = re.sub(r"(?i)(api[_-]?key|authorization|bearer)\s*[:=]\s*\S+", r"\1=[REDACTED]", t)
print(t[-400:])
PYRED
  fi
fi
python3 "$SCRIPT_DIR/fleet-bridge.py" --once --force
