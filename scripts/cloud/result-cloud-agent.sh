#!/usr/bin/env bash
# Print result/context JSON for a Cursor Cloud agent.
# Canonical: @cursor/sdk. REST curl = fallback (CURSOR_API_BASE / CLOUD_FORCE_REST).
# Usage: result-cloud-agent.sh <bc-id>
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "${HERE}/_common.sh"

ID="${1:-}"
if [[ -z "$ID" || "$ID" == "-h" || "$ID" == "--help" ]]; then
  echo "usage: $0 <bc-id>" >&2
  [[ "${ID:-}" == "-h" || "${ID:-}" == "--help" ]] && exit 0
  exit 2
fi

if ! cloud_load_auth; then
  echo "error: CURSOR_API_KEY is not set (export it or add it to ~/.config/cursor/agent.env)" >&2
  exit 1
fi

if cloud_sdk_exec result "$@"; then
  exit "$CLOUD_SDK_RC"
fi

if ! cloud_http_request GET "/v1/agents/${ID}"; then
  echo "error: curl failed http=${CLOUD_HTTP_CODE:-000}" >&2
  exit 1
fi
if ! cloud_http_is_2xx; then
  echo "CLOUD_RESULT_ERR http=${CLOUD_HTTP_CODE} id=${ID}" >&2
  cloud_redact_stream <"$CLOUD_HTTP_BODY" >&2 || true
  exit 1
fi

AGENT_FILE="$(mktemp "${TMPDIR:-/tmp}/cloud-result-agent.XXXXXX")"
RUN_FILE="$(mktemp "${TMPDIR:-/tmp}/cloud-result-run.XXXXXX")"
cleanup() { rm -f "$AGENT_FILE" "$RUN_FILE"; }
trap cleanup EXIT
cp "$CLOUD_HTTP_BODY" "$AGENT_FILE"
echo '{}' >"$RUN_FILE"

LATEST="$(cloud_json_get "$AGENT_FILE" latestRunId)"
if [[ -n "$LATEST" ]]; then
  if cloud_http_request GET "/v1/agents/${ID}/runs/${LATEST}" && cloud_http_is_2xx; then
    cp "$CLOUD_HTTP_BODY" "$RUN_FILE"
  fi
fi

python3 -c '
import json, sys

def unwrap(data, key):
    if isinstance(data, dict) and key in data and "id" not in data:
        inner = data[key]
        if isinstance(inner, dict):
            return inner
    return data

with open(sys.argv[1], encoding="utf-8") as fh:
    agent = unwrap(json.load(fh), "agent")
with open(sys.argv[2], encoding="utf-8") as fh:
    run = unwrap(json.load(fh), "run")

branches, pr = [], None
for b in (run.get("git") or {}).get("branches") or []:
    if b.get("branch"):
        branches.append(b["branch"])
    if b.get("prUrl") and not pr:
        pr = b["prUrl"]
err = run.get("error")
if isinstance(err, str):
    err = {"message": err}
elif not isinstance(err, dict):
    err = None
elif "message" not in err:
    err = {"message": json.dumps(err)}
status = run.get("status") or None
out = {
    "agentId": agent.get("id") or "",
    "name": agent.get("name") or "",
    "url": agent.get("url") or "",
    "runId": run.get("id") or agent.get("latestRunId") or None,
    "status": status,
    "agentStatus": agent.get("status") or None,
    "runStatus": status,
    "prUrl": pr,
    "branches": branches,
    "branch": branches[0] if branches else None,
    "summary": None,
    "result": (run.get("result") or "").strip() or None,
    "error": err,
}
print(json.dumps(out, indent=2))
' "$AGENT_FILE" "$RUN_FILE"
