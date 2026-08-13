#!/usr/bin/env bash
# Smoke Extra High handoff/return path without creating a live cloud agent.
# Usage:
#   scripts/cloud/smoke-handoff.sh           # dry-run register + AK notify
#   CLOUD_SMOKE_LIVE=1 scripts/cloud/smoke-handoff.sh  # optional live launch (needs CURSOR_API_KEY)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${GCS_ROOT:-$SCRIPT_DIR/../..}" && pwd)"
STATE_DIR="${GCS_A2A_STATE:-$ROOT/.a2a-state}"
SEAT="${GCS_DIRECTOR_SEAT:-${CLOUD_OWNER_SEAT:-ops}}"
FAKE_ID="${CLOUD_SMOKE_BC_ID:-bc-smoke-handoff-$$}"
RUN_ID="${CLOUD_SMOKE_RUN_ID:-run-smoke-$$}"

export GCS_ROOT="$ROOT"
export GCS_A2A_STATE="$STATE_DIR"
export GCS_DIRECTOR_SEAT="$SEAT"
export PATH="${HOME}/.local/bin:${PATH:-}"

echo "CLOUD_SMOKE_START seat=$SEAT id=$FAKE_ID dry=$([[ "${CLOUD_SMOKE_LIVE:-0}" == "1" ]] && echo 0 || echo 1)"

# 1) Ledger register (dry waiter — register + AK notify, no detached wait)
CLOUD_WAITER_DRY=1 bash "$ROOT/scripts/cloud/spawn-waiter.sh" --id "$FAKE_ID" --run "$RUN_ID" --seat "$SEAT" --name "smoke-handoff"

# 2) AK observer event (best-effort; spawn-waiter also notifies)
if [[ -f "$ROOT/scripts/studio/agent-kanban/notify-event.sh" ]]; then
  bash "$ROOT/scripts/studio/agent-kanban/notify-event.sh" launch "$FAKE_ID" "seat=$SEAT" "run_id=$RUN_ID" "source=smoke" || true
fi

# 3) Simulate FLEET_DONE via ledger complete (does not require cloud API)
python3 "$ROOT/scripts/cloud/fleet_ledger.py" complete \
  --id "$FAKE_ID" \
  --seat "$SEAT" \
  --notified-by "smoke" \
  --payload-file - <<JSON || true
{"id":"$FAKE_ID","runStatus":"FINISHED","status":"FINISHED","name":"smoke-handoff","prUrl":"none","url":"https://cursor.com/agents/$FAKE_ID"}
JSON

# 4) Assert fleet.jsonl row exists
python3 - "$STATE_DIR/$SEAT/fleet.jsonl" "$FAKE_ID" <<'PY'
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
want = sys.argv[2]
if not path.is_file():
    print("CLOUD_SMOKE_FAIL missing fleet.jsonl", path)
    raise SystemExit(1)
rows = []
for line in path.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line:
        continue
    try:
        rec = json.loads(line)
    except json.JSONDecodeError:
        continue
    if str(rec.get("bc_id")) == want:
        rows.append(rec)
if not rows:
    print("CLOUD_SMOKE_FAIL bc_id not in fleet.jsonl")
    raise SystemExit(1)
row = rows[-1]
print(f"CLOUD_SMOKE_FLEET status={row.get('status')} notified={row.get('notified')} notified_by={row.get('notified_by')}")
print("CLOUD_SMOKE_OK register_path")
PY

if [[ "${CLOUD_SMOKE_LIVE:-0}" == "1" ]]; then
  echo "CLOUD_SMOKE_LIVE launching Extra High (requires CURSOR_API_KEY)"
  bash "$ROOT/scripts/launch-cloud-extra-high.sh" --name "smoke-handoff" \
    "Smoke handoff only: open a no-op PR that adds docs/studio/directors/SMOKE_HANDOFF.md with one line OK, then stop."
else
  echo "CLOUD_SMOKE_SKIP_LIVE set CLOUD_SMOKE_LIVE=1 to launch a real Extra High"
fi

for s in followup-cloud-agent.sh result-cloud-agent.sh status-cloud-agent.sh; do
  if [[ -f "$ROOT/scripts/cloud/$s" ]]; then
    echo "CLOUD_SMOKE_SCRIPT_OK $s"
  else
    echo "CLOUD_SMOKE_SCRIPT_MISSING $s" >&2
  fi
done

echo "CLOUD_SMOKE_DONE"
