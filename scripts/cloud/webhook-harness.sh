#!/usr/bin/env bash
# Local webhook harness: serve the signed receiver, or POST a signed fixture.
# Never prints GCS_WEBHOOK_SECRET.
#
#   webhook-harness.sh serve
#   webhook-harness.sh simulate --id bc-test --status FINISHED [--pr URL]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
RECEIVER="$ROOT/scripts/cloud/webhook_receiver.py"
HOST="${GCS_WEBHOOK_HOST:-127.0.0.1}"
PORT="${GCS_WEBHOOK_PORT:-8788}"
URL_DEFAULT="http://${HOST}:${PORT}/webhooks/cursor-cloud"

usage() {
  cat <<'EOF'
Usage:
  webhook-harness.sh serve
  webhook-harness.sh simulate [--id ID] [--status STATUS] [--pr URL] [--url URL] [--body FILE]

serve      start scripts/cloud/webhook_receiver.py (requires GCS_WEBHOOK_SECRET)
simulate   HMAC-SHA256 sign a JSON body and POST it (local signed verify)

Env: GCS_WEBHOOK_SECRET (required), GCS_WEBHOOK_HOST, GCS_WEBHOOK_PORT
EOF
}

need_secret() {
  if [[ -z "${GCS_WEBHOOK_SECRET:-}" ]]; then
    echo "webhook-harness: GCS_WEBHOOK_SECRET is required" >&2
    exit 2
  fi
}

sign_body() {
  local body_file="$1"
  python3 - "$body_file" <<'PY'
import hashlib, hmac, os, sys
secret = (os.environ.get("GCS_WEBHOOK_SECRET") or "").encode("utf-8")
body = open(sys.argv[1], "rb").read()
print(hmac.new(secret, body, hashlib.sha256).hexdigest())
PY
}

cmd="${1:-}"
shift || true
case "$cmd" in
  -h|--help|help|"")
    usage
    exit 0
    ;;
  serve)
    need_secret
    exec python3 "$RECEIVER"
    ;;
  simulate)
    need_secret
    ID="bc-simulate"
    STATUS="FINISHED"
    PR=""
    URL="$URL_DEFAULT"
    BODY_FILE=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --id) ID="${2:-}"; shift 2 ;;
        --status) STATUS="${2:-}"; shift 2 ;;
        --pr) PR="${2:-}"; shift 2 ;;
        --url) URL="${2:-}"; shift 2 ;;
        --body) BODY_FILE="${2:-}"; shift 2 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
      esac
    done
    TMP="$(mktemp "${TMPDIR:-/tmp}/gcs-webhook.XXXXXX")"
    cleanup() { rm -f "$TMP"; }
    trap cleanup EXIT
    if [[ -n "$BODY_FILE" ]]; then
      cp "$BODY_FILE" "$TMP"
    else
      ID="$ID" STATUS="$STATUS" PR="$PR" python3 - <<'PY' >"$TMP"
import json, os
body = {
    "event": "statusChange",
    "id": os.environ["ID"],
    "status": os.environ["STATUS"],
    "name": "simulate",
    "target": {
        "url": f"https://cursor.com/agents?id={os.environ['ID']}",
    },
}
if os.environ.get("PR"):
    body["target"]["prUrl"] = os.environ["PR"]
print(json.dumps(body))
PY
    fi
    SIG="$(sign_body "$TMP")"
    HTTP="$(curl -sS -o /tmp/gcs-webhook-resp.json -w "%{http_code}" \
      -H "Content-Type: application/json" \
      -H "X-Webhook-Signature: sha256=${SIG}" \
      -X POST "$URL" \
      --data-binary @"$TMP")"
    echo "WEBHOOK_SIMULATE http=$HTTP url=$URL"
    cat /tmp/gcs-webhook-resp.json 2>/dev/null || true
    echo
    [[ "$HTTP" == "200" || "$HTTP" == "202" ]]
    ;;
  *)
    echo "unknown command: $cmd" >&2
    usage >&2
    exit 2
    ;;
esac
