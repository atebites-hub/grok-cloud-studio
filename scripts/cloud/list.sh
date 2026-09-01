#!/usr/bin/env bash
# List Cursor Cloud agents (newest first). SDK-first; REST fallback.
# Usage: list.sh [--limit N]   or   list.sh [N]
# Each row prints agent status and latest-run runStatus. Never prints API keys.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "${HERE}/_common.sh"

limit="${CLOUD_LIST_LIMIT:-20}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --limit)
      limit="$2"
      shift 2
      ;;
    --limit=*)
      limit="${1#--limit=}"
      shift
      ;;
    -h|--help)
      echo "Usage: scripts/cloud/list.sh [--limit N]"
      echo "       scripts/cloud/list-cloud-agents.sh [limit=20]"
      exit 0
      ;;
    *)
      if [[ "$1" =~ ^[0-9]+$ ]]; then
        limit="$1"
        shift
      else
        echo "error: unknown option $1" >&2
        exit 1
      fi
      ;;
  esac
done

if ! cloud_load_auth; then
  echo "error: CURSOR_API_KEY is not set (export it or add it to ~/.config/cursor/agent.env)" >&2
  exit 1
fi

if cloud_sdk_exec list "$limit"; then
  exit "$CLOUD_SDK_RC"
fi

if ! cloud_http_request GET "/v1/agents?limit=${limit}"; then
  echo "error: curl failed http=${CLOUD_HTTP_CODE:-000}" >&2
  exit 1
fi
if ! cloud_http_is_2xx; then
  echo "error: list failed http=${CLOUD_HTTP_CODE}" >&2
  cloud_redact_stream <"$CLOUD_HTTP_BODY" >&2 || true
  exit 1
fi

# Agent.status stays ACTIVE after the latest run is terminal (stale membership).
# Fetch each latest run so rows show runStatus (RUNNING/FINISHED/CANCELLED/…), not only ACTIVE.
python3 -c '
import base64
import json
import os
import sys
import urllib.error
import urllib.request

def unwrap(data, key):
    if isinstance(data, dict) and key in data and "id" not in data:
        inner = data[key]
        if isinstance(inner, dict):
            return inner
    return data

def fetch_run_status(base, key, agent_id, run_id, timeout):
    url = f"{base}/v1/agents/{agent_id}/runs/{run_id}"
    token = base64.b64encode(f"{key}:".encode("utf-8")).decode("ascii")
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "Authorization": f"Basic {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
        return "none"
    if not isinstance(payload, dict):
        return "none"
    run = unwrap(payload, "run")
    if not isinstance(run, dict):
        return "none"
    status = str(run.get("status") or "").strip()
    return status.upper() if status else "none"

base = (os.environ.get("CURSOR_API_BASE") or "https://api.cursor.com").rstrip("/")
key = os.environ.get("CURSOR_API_KEY") or ""
timeout = min(float(os.environ.get("CLOUD_CURL_MAX_TIME") or "120"), 15.0)
with open(sys.argv[1], encoding="utf-8") as fh:
    data = json.load(fh)
items = data.get("items") or []
for item in items:
    agent_id = str(item.get("id") or "")
    agent_status = str(item.get("status") or "")
    name = str(item.get("name") or "")
    url = str(item.get("url") or "")
    run_id = str(item.get("latestRunId") or "")
    run_status = "none"
    if agent_id and run_id:
        run_status = fetch_run_status(base, key, agent_id, run_id, timeout)
    print(
        f"id={agent_id} status={agent_status} runStatus={run_status} "
        f"name={name} url={url} latestRunId={run_id}"
    )
' "$CLOUD_HTTP_BODY"
