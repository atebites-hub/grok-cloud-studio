#!/usr/bin/env bash
# Poll a Cursor Cloud agent until its latest run is terminal. SDK-first.
# Directors: refused unless CLOUD_ALLOW_BLOCK_WAIT=1 (LIV-103).
# Terminal run statuses: FINISHED (exit 0), ERROR/CANCELLED/EXPIRED (exit 1).
# Usage: watch.sh AGENT_ID [timeout_sec] [poll_sec]
# Env: CLOUD_WATCH_INTERVAL (default 10), CLOUD_WATCH_TIMEOUT_SEC (0 = none)
# Never prints API keys. Never Bot CloudAgent.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "${HERE}/_common.sh"

if [[ $# -lt 1 || "$1" == "-h" || "$1" == "--help" ]]; then
  echo "Usage: scripts/cloud/watch.sh AGENT_ID [timeout_sec] [poll_sec]"
  echo "Env: CLOUD_WATCH_INTERVAL (seconds, default 10), CLOUD_WATCH_TIMEOUT_SEC (0 = none)"
  [[ $# -ge 1 && ( "$1" == "-h" || "$1" == "--help" ) ]] && exit 0
  exit 1
fi

agent_id="$1"
if cloud_refuse_director_block_wait "$agent_id"; then
  exit 2
fi
interval="${CLOUD_WATCH_INTERVAL:-10}"
timeout_sec="${CLOUD_WATCH_TIMEOUT_SEC:-0}"
if [[ $# -ge 2 && "$2" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  timeout_sec="$2"
fi
if [[ $# -ge 3 && "$3" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  interval="$3"
fi
start_ts="$(date +%s)"

if ! cloud_load_auth; then
  echo "error: CURSOR_API_KEY is not set (export it or add it to ~/.config/cursor/agent.env)" >&2
  exit 1
fi

if cloud_sdk_exec watch "$agent_id" "$timeout_sec" "$interval"; then
  exit "$CLOUD_SDK_RC"
fi

while true; do
  if ! cloud_http_request GET "/v1/agents/${agent_id}"; then
    echo "error: curl failed http=${CLOUD_HTTP_CODE:-000}" >&2
    exit 1
  fi
  if ! cloud_http_is_2xx; then
    echo "error: watch agent fetch failed http=${CLOUD_HTTP_CODE}" >&2
    cloud_redact_stream <"$CLOUD_HTTP_BODY" >&2 || true
    exit 1
  fi

  run_id="$(cloud_json_get "$CLOUD_HTTP_BODY" latestRunId)"
  agent_status="$(cloud_json_get "$CLOUD_HTTP_BODY" status)"
  run_status=""
  if [[ -n "$run_id" ]]; then
    if ! cloud_http_request GET "/v1/agents/${agent_id}/runs/${run_id}"; then
      echo "error: curl failed fetching run http=${CLOUD_HTTP_CODE:-000}" >&2
      exit 1
    fi
    if ! cloud_http_is_2xx; then
      echo "error: watch run fetch failed http=${CLOUD_HTTP_CODE}" >&2
      cloud_redact_stream <"$CLOUD_HTTP_BODY" >&2 || true
      exit 1
    fi
    run_status="$(cloud_json_get "$CLOUD_HTTP_BODY" status)"
  fi

  status="${run_status:-$agent_status}"
  printf 'agent=%s run=%s status=%s\n' "$agent_id" "$run_id" "$status"

  case "$status" in
    FINISHED)
      exit 0
      ;;
    ERROR|CANCELLED|EXPIRED)
      exit 1
      ;;
  esac

  if [[ "$timeout_sec" =~ ^[1-9][0-9]*([.][0-9]+)?$ ]]; then
    now_ts="$(date +%s)"
    if (( now_ts - start_ts >= ${timeout_sec%%.*} )); then
      echo "error: watch timed out after ${timeout_sec}s status=${status}" >&2
      exit 1
    fi
  fi
  sleep "$interval"
done
