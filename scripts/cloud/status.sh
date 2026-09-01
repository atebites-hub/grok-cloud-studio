#!/usr/bin/env bash
# Show one Cursor Cloud agent and its latest run. SDK-first; REST fallback.
# Usage: status.sh AGENT_ID [--json]
# Prints runStatus (latest run), not leftover agent ACTIVE. Never prints API keys.
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

name="$(cloud_json_get "$CLOUD_HTTP_BODY" name)"
agent_status="$(cloud_json_get "$CLOUD_HTTP_BODY" status)"
url="$(cloud_json_get "$CLOUD_HTTP_BODY" url)"
run_id="$(cloud_json_get "$CLOUD_HTTP_BODY" latestRunId)"
printf 'id=%s\n' "$agent_id"
printf 'name=%s\n' "$name"
printf 'agentStatus=%s\n' "$agent_status"
printf 'url=%s\n' "$url"
printf 'latestRunId=%s\n' "$run_id"

if [[ -n "$run_id" ]]; then
  if ! cloud_http_request GET "/v1/agents/${agent_id}/runs/${run_id}"; then
    echo "error: curl failed fetching run http=${CLOUD_HTTP_CODE:-000}" >&2
    exit 1
  fi
  if ! cloud_http_is_2xx; then
    echo "error: run status failed http=${CLOUD_HTTP_CODE}" >&2
    cloud_redact_stream <"$CLOUD_HTTP_BODY" >&2 || true
    exit 1
  fi
  run_status="$(cloud_json_get "$CLOUD_HTTP_BODY" status)"
  printf 'runStatus=%s\n' "$run_status"
else
  printf 'runStatus=%s\n' "none"
fi
