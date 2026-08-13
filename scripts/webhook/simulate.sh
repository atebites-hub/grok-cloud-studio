#!/usr/bin/env bash
set -euo pipefail
HOST="${GCS_WEBHOOK_HOST:-127.0.0.1}"
PORT="${GCS_WEBHOOK_PORT:-8788}"
SECRET="${GCS_WEBHOOK_SECRET:-dev-only-not-for-prod}"
SEAT="${1:-ops}"
BC_ID="${2:-bc-example000}"
STATUS="${3:-FINISHED}"
PR="${4:-https://github.com/example/repo/pull/1}"
BODY=$(BC_ID="$BC_ID" STATUS="$STATUS" SEAT="$SEAT" PR="$PR" python3 - <<'INNER'
import json, os
print(json.dumps({"id": os.environ["BC_ID"], "status": os.environ["STATUS"], "seat": os.environ["SEAT"], "prUrl": os.environ["PR"], "run": {"status": os.environ["STATUS"]}}))
INNER
)
SIG=$(printf '%s' "$BODY" | SECRET="$SECRET" python3 - <<'INNER'
import hmac, hashlib, os, sys
print("sha256=" + hmac.new(os.environ["SECRET"].encode(), sys.stdin.buffer.read(), hashlib.sha256).hexdigest())
INNER
)
curl -sS -X POST "http://${HOST}:${PORT}/hook" -H "Content-Type: application/json" -H "X-GCS-Signature: ${SIG}" -d "$BODY"
echo
