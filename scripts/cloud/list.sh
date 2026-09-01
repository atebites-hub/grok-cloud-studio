#!/usr/bin/env bash
# List Cursor Cloud agents (newest first). SDK-first; REST fallback.
# Usage: list.sh [--running] [--limit N]   or   list.sh [--running] [N]
# Each row prints agent status and latest-run runStatus. Never prints API keys.
# Default lists ACTIVE membership. --running keeps latest-run runStatus=RUNNING only.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "${HERE}/_common.sh"

limit="${CLOUD_LIST_LIMIT:-20}"
running=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --running)
      running=1
      shift
      ;;
    --limit)
      limit="$2"
      shift 2
      ;;
    --limit=*)
      limit="${1#--limit=}"
      shift
      ;;
    -h|--help)
      echo "Usage: scripts/cloud/list.sh [--running] [--limit N]"
      echo "       scripts/cloud/list-cloud-agents.sh [--running] [limit=20]"
      echo "  --running  only rows whose latest run runStatus is RUNNING"
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

sdk_args=("$limit")
if [[ "$running" -eq 1 ]]; then
  sdk_args+=("--running")
fi
if cloud_sdk_exec list "${sdk_args[@]}"; then
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
# Fetch each latest run so rows show runStatus (RUNNING vs FINISHED), not only ACTIVE.
# --running filters after that parallel fetch so capacity beats skip leftover shells.
row_args=("$CLOUD_HTTP_BODY")
if [[ "$running" -eq 1 ]]; then
  row_args+=("--running")
fi
python3 "${HERE}/list_rows.py" "${row_args[@]}"
