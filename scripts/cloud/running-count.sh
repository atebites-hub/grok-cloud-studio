#!/usr/bin/env bash
# Count live Cursor Cloud workers (latest-run runStatus=RUNNING).
# Agent status ACTIVE + latest run FINISHED is a leftover, not capacity.
# Prints list rows (runStatus + model) then CLOUD_RUNNING / CLOUD_MUST_LAUNCH.
#
# Usage: running-count.sh [--limit N]
# If RUNNING for GCS_CLOUD_REPO is below GCS_CLOUD_MIN_RUNNING (default 8),
# prints CLOUD_MUST_LAUNCH=1 — cloud mind / directors MUST cloud_launch.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "${HERE}/_common.sh"

limit="${CLOUD_LIST_LIMIT:-50}"
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
      echo "Usage: scripts/cloud/running-count.sh [--limit N]"
      exit 0
      ;;
    *)
      echo "error: unknown option $1" >&2
      exit 1
      ;;
  esac
done

if ! cloud_load_auth; then
  echo "error: CURSOR_API_KEY is not set (export it or add it to ~/.config/cursor/agent.env)" >&2
  exit 1
fi

list_out="$("${HERE}/list.sh" --limit "$limit")"
repo="${GCS_CLOUD_REPO:-${CLOUD_REPO_URL:-}}"
python3 "${HERE}/capacity.py" decide-from-list --repo "$repo" <<<"$list_out"
