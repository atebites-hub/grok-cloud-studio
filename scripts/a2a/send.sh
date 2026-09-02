#!/usr/bin/env bash
# Send an A2A text message to a Grok Cloud Studio seat via the local hub.
# Usage: send.sh [--from SEAT] <seat> "<text>" [optional-data-json]
# Env: GCS_A2A_HUB (default http://127.0.0.1:8732)
#      GCS_A2A_FROM (caller seat; --from wins)
# Enqueue only: hub returns TASK_STATE_SUBMITTED. Mail stays queued until
# the Grok Build mind harvests the inbox line and the runner exits 0.
# send.sh does not wait for that turn and does not fake ACP HANDOFF.
# A2A ACK / stdout kind=receipt is a protocol receipt, not mind-turn done.
# Stdout binds kind=receipt from the hub receipt artifact (not the mind-turn log).
set -euo pipefail

FROM_SEAT="${GCS_A2A_FROM:-}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --from)
      FROM_SEAT="${2:-}"
      shift 2
      ;;
    --from=*)
      FROM_SEAT="${1#--from=}"
      shift
      ;;
    --)
      shift
      break
      ;;
    -*)
      echo "usage: $0 [--from SEAT] <seat> \"<text>\" [optional-data-json]" >&2
      exit 2
      ;;
    *)
      break
      ;;
  esac
done

SEAT="${1:-}"
TEXT="${2:-}"
DATA_JSON="${3:-}"
HUB="${GCS_A2A_HUB:-http://127.0.0.1:8732}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${GCS_ROOT:-$SCRIPT_DIR/../..}" && pwd)"

if [[ -z "$SEAT" || -z "$TEXT" ]]; then
  echo "usage: $0 [--from SEAT] <seat> \"<text>\" [optional-data-json]" >&2
  echo "seats:" >&2
  python3 "$ROOT/scripts/a2a/lib.py" launch-seats >&2 || true
  exit 2
fi

MSG_ID=$(python3 - <<'PY'
import uuid; print(uuid.uuid4())
PY
)

BODY=$(TEXT_VAL="$TEXT" MSG_ID="$MSG_ID" DATA_JSON="$DATA_JSON" FROM_SEAT="$FROM_SEAT" python3 - <<'PY'
import json, os
parts = [{"kind": "text", "text": os.environ["TEXT_VAL"]}]
raw = os.environ.get("DATA_JSON") or ""
data = {}
if raw.strip():
    data = json.loads(raw)
from_seat = (os.environ.get("FROM_SEAT") or "").strip()
if from_seat:
    if not isinstance(data, dict):
        data = {"payload": data}
    data.setdefault("from", from_seat)
if data:
    parts.append({"kind": "data", "data": data})
body = {
    "from": from_seat or None,
    "message": {
        "messageId": os.environ["MSG_ID"],
        "role": "ROLE_USER",
        "parts": parts,
        "metadata": {"from": from_seat} if from_seat else {},
    },
}
print(json.dumps(body))
PY
)

TMP=$(mktemp)
HTTP=$(curl -sS --connect-timeout 2 --max-time 8 -o "$TMP" -w "%{http_code}" \
  -H 'Content-Type: application/json' \
  -X POST "$HUB/a2a/${SEAT}/message:send" \
  -d "$BODY")

if [[ "$HTTP" != "200" ]]; then
  echo "A2A_SEND_FAIL http=$HTTP seat=$SEAT" >&2
  cat "$TMP" >&2
  rm -f "$TMP"
  exit 1
fi

python3 - <<PY
import json
d=json.load(open("$TMP"))
task=d.get("task") or d
status=task.get("status") or {}
state=status.get("state") or ""
arts=task.get("artifacts") or []
has_receipt=any(isinstance(a, dict) and a.get("name")=="receipt" for a in arts)
kind="receipt" if has_receipt else str((task.get("metadata") or {}).get("kind") or "")
print(f"A2A_SEND_OK seat=$SEAT task={task.get('id','')} state={state} kind={kind}")
print(task.get("id",""))
PY
rm -f "$TMP"
