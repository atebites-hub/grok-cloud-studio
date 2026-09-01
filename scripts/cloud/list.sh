#!/usr/bin/env bash
# List Cursor Cloud agents (newest first). SDK-first; REST fallback.
# Usage: list.sh [--limit N]   or   list.sh [N]
# Each row prints agentStatus (membership) and latest-run runStatus.
# Leftover ACTIVE+FINISHED is not a worker. Never prints API keys.
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
# Fetch each latest run so rows show runStatus (RUNNING vs FINISHED), not leftover ACTIVE.
python3 "${HERE}/capacity.py" format-list "$CLOUD_HTTP_BODY"
