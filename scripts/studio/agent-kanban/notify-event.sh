#!/usr/bin/env bash
# Append one observer event to .a2a-state/agent-kanban/events.jsonl (+ kanban/).
# Usage: notify-event.sh <event> <bc-id> [key=value ...]
# Never prints secrets. Best-effort from spawn-waiter.sh on Extra High launch.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${GCS_ROOT:-$SCRIPT_DIR/../../..}" && pwd)"
STATE_DIR="${GCS_A2A_STATE:-$ROOT/.a2a-state}"
AK_DIR="$STATE_DIR/agent-kanban"
KANBAN_DIR="$STATE_DIR/kanban"

event="${1:-}"
bc_id="${2:-}"
if [[ -z "$event" || -z "$bc_id" ]]; then
  echo "usage: notify-event.sh <event> <bc-id> [key=value ...]" >&2
  exit 2
fi
shift 2

mkdir -p "$AK_DIR" "$KANBAN_DIR"

python3 - "$AK_DIR/events.jsonl" "$KANBAN_DIR/events.jsonl" "$event" "$bc_id" "$@" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

paths = [Path(sys.argv[1]), Path(sys.argv[2])]
event = sys.argv[3]
bc_id = sys.argv[4]
row = {
    "event": event,
    "bc_id": bc_id,
    "ts": datetime.now(timezone.utc).isoformat(),
}
skip = ("key", "token", "secret", "password", "authorization", "api_key")
for item in sys.argv[5:]:
    if "=" not in item:
        continue
    name, value = item.split("=", 1)
    name = name.strip()
    if not name:
        continue
    lower = name.lower()
    if any(part in lower for part in skip):
        continue
    row[name] = value
line = json.dumps(row, ensure_ascii=False) + "\n"
for path in paths:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)
print(f"AK_EVENT_OK event={event} id={bc_id}")
PY
