#!/usr/bin/env bash
# Count in-flight Cursor Cloud runs (runStatus RUNNING/CREATING) per repo.
# Agent status ACTIVE + latest run FINISHED is a leftover, not a worker.
# Prints list rows (with runStatus) then CLOUD_RUNNING / CLOUD_MUST_LAUNCH.
#
# Usage: running-count.sh [--limit N]
# Directors must cloud_launch until GCS_CLOUD_MIN_RUNNING (default 8)
# in-flight runs for GCS_CLOUD_REPO. Never Bot CloudAgent.
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
      echo "Prints runStatus rows then CLOUD_RUNNING / CLOUD_MUST_LAUNCH."
      echo "Count RUNNING/CREATING for GCS_CLOUD_REPO, not leftover ACTIVE."
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

repo="${GCS_CLOUD_REPO:-${CLOUD_REPO_URL:-}}"
list_out="$("${HERE}/list.sh" --limit "$limit")"
python3 "${HERE}/capacity.py" decide-from-list --repo "$repo" <<<"$list_out"
