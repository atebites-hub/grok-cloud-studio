#!/usr/bin/env bash
# List Cursor Cloud agents (newest first). SDK-first; REST fallback.
# Usage: list.sh [--limit N]   or   list.sh [N]
# Each row prints agent status and latest-run runStatus. Never prints API keys.
# REST walks nextCursor when --limit exceeds the API page cap (100).
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

# REST: paginate GET /v1/agents via nextCursor (API max page 100). Fail-closed
# on a page error — never a partial list that looks like running=0.
python3 "${HERE}/list_rows.py" --limit "$limit"
