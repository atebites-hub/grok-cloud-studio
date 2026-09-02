#!/usr/bin/env bash
# Show one Cursor Cloud agent and its latest run. SDK-first; REST fallback.
# Usage: status.sh AGENT_ID [--json]
# Compact REST prints agent status and latest-run runStatus (RUNNING vs FINISHED).
# Never prints API keys.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "${HERE}/_common.sh"

if [[ $# -lt 1 || "$1" == "-h" || "$1" == "--help" ]]; then
  echo "Usage: scripts/cloud/status.sh AGENT_ID [--json]"
  [[ $# -ge 1 && ( "$1" == "-h" || "$1" == "--help" ) ]] && exit 0
  exit 1
fi

json=0
agent_id=""
for arg in "$@"; do
  case "$arg" in
    --json) json=1 ;;
    -*)
      echo "error: unknown option $arg" >&2
      exit 1
      ;;
    *)
      if [[ -z "$agent_id" ]]; then
        agent_id="$arg"
      fi
      ;;
  esac
done

if [[ -z "$agent_id" ]]; then
  echo "Usage: scripts/cloud/status.sh AGENT_ID [--json]" >&2
  exit 1
fi

if ! cloud_load_auth; then
  echo "error: CURSOR_API_KEY is not set (export it or add it to ~/.config/cursor/agent.env)" >&2
  exit 1
fi

if cloud_sdk_exec status "$@"; then
  exit "$CLOUD_SDK_RC"
fi

if [[ "$json" -eq 1 ]]; then
  exec "${HERE}/result-cloud-agent.sh" "$agent_id"
fi

if ! cloud_http_request GET "/v1/agents/${agent_id}"; then
  echo "error: curl failed http=${CLOUD_HTTP_CODE:-000}" >&2
  exit 1
fi
if ! cloud_http_is_2xx; then
  echo "error: status failed http=${CLOUD_HTTP_CODE}" >&2
  cloud_redact_stream <"$CLOUD_HTTP_BODY" >&2 || true
  exit 1
fi

# Agent.status stays ACTIVE after the latest run is terminal (stale membership).
# Fetch the latest run so compact output shows runStatus (RUNNING vs FINISHED),
# not only ACTIVE. Missing / failed run GET (including HTTP 404) → runStatus=none.
AGENT_FILE="$(mktemp "${TMPDIR:-/tmp}/cloud-status-agent.XXXXXX")"
RUN_FILE="$(mktemp "${TMPDIR:-/tmp}/cloud-status-run.XXXXXX")"
cleanup_status_tmp() { rm -f "$AGENT_FILE" "$RUN_FILE"; }
trap cleanup_status_tmp EXIT
cp "$CLOUD_HTTP_BODY" "$AGENT_FILE"
echo '{}' >"$RUN_FILE"

run_id="$(
  python3 -c '
import json, sys
sys.path.insert(0, sys.argv[1])
from list_rows import unwrap_entity
with open(sys.argv[2], encoding="utf-8") as fh:
    agent = unwrap_entity(json.load(fh), "agent")
print(str(agent.get("latestRunId") or "") if isinstance(agent, dict) else "")
' "$HERE" "$AGENT_FILE"
)"

if [[ -n "$run_id" ]]; then
  set +e
  cloud_http_request GET "/v1/agents/${agent_id}/runs/${run_id}"
  run_fetch_rc=$?
  set -e
  if [[ "$run_fetch_rc" -eq 0 ]] && cloud_http_is_2xx; then
    cp "$CLOUD_HTTP_BODY" "$RUN_FILE"
  fi
fi

python3 -c '
import json, sys
sys.path.insert(0, sys.argv[1])
from list_rows import format_list_row, normalize_run_status, unwrap_entity

with open(sys.argv[2], encoding="utf-8") as fh:
    agent = unwrap_entity(json.load(fh), "agent")
if not isinstance(agent, dict):
    agent = {}
with open(sys.argv[3], encoding="utf-8") as fh:
    run = unwrap_entity(json.load(fh), "run")
if not isinstance(run, dict):
    run = {}
print(
    format_list_row(
        agent_id=str(agent.get("id") or sys.argv[4] or ""),
        agent_status=str(agent.get("status") or ""),
        run_status=normalize_run_status(run.get("status")),
        name=str(agent.get("name") or ""),
        url=str(agent.get("url") or ""),
        run_id=str(run.get("id") or agent.get("latestRunId") or ""),
    )
)
' "$HERE" "$AGENT_FILE" "$RUN_FILE" "$agent_id"
