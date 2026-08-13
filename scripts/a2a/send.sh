#!/usr/bin/env bash
# Send an A2A text message to a Grok Cloud Studio seat via the local hub.
# Usage: send.sh <seat> "<text>" [optional-data-json]
# Env: GCS_A2A_HUB (default http://127.0.0.1:8732)
set -euo pipefail
SEAT="${1:-}"
TEXT="${2:-}"
DATA_JSON="${3:-}"
HUB="${GCS_A2A_HUB:-http://127.0.0.1:8732}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${GCS_ROOT:-$SCRIPT_DIR/../..}" && pwd)"

if [[ -z "$SEAT" || -z "$TEXT" ]]; then
  echo "usage: $0 <seat> \"<text>\" [optional-data-json]" >&2
  echo "seats:" >&2
  python3 "$ROOT/scripts/a2a/lib.py" launch-seats >&2 || true
  exit 2
fi

MSG_ID=$(python3 - <<'PY'
import uuid; print(uuid.uuid4())
PY
)

BODY=$(TEXT_VAL="$TEXT" MSG_ID="$MSG_ID" DATA_JSON="$DATA_JSON" python3 - <<'PY'
import json, os
parts = [{"kind": "text", "text": os.environ["TEXT_VAL"]}]
raw = os.environ.get("DATA_JSON") or ""
if raw.strip():
    parts.append({"kind": "data", "data": json.loads(raw)})
body = {
    "message": {
        "messageId": os.environ["MSG_ID"],
        "role": "ROLE_USER",
        "parts": parts,
    }
}
print(json.dumps(body))
PY
)

TMP=$(mktemp)
HTTP=$(curl -sS -o "$TMP" -w "%{http_code}" \
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
print(f"A2A_SEND_OK seat=$SEAT task={task.get('id','')} state={(task.get('status') or {}).get('state','')}")
print(task.get("id",""))
PY
rm -f "$TMP"
