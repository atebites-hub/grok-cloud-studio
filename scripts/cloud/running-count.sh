#!/usr/bin/env bash
# Count in-flight Cursor Cloud runs (runStatus RUNNING/CREATING).
# Agent status ACTIVE + latest run FINISHED is a leftover, not a worker.
# Prints list rows (with runStatus) then CLOUD_RUNNING / CLOUD_MUST_LAUNCH.
#
# Usage: running-count.sh [--work TEXT] [--limit N]
# If playability/art work is in progress and in-flight count for
# GCS_CLOUD_REPO is below GCS_CLOUD_RUNNING_CAP (default 8), prints
# CLOUD_MUST_LAUNCH=1 — the cloud mind MUST launch.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "${HERE}/_common.sh"

work=""
limit="${CLOUD_LIST_LIMIT:-50}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --work)
      work="$2"
      shift 2
      ;;
    --work=*)
      work="${1#--work=}"
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
      echo "Usage: scripts/cloud/running-count.sh [--work TEXT] [--limit N]"
      exit 0
      ;;
    *)
      work="${work:+$work }$1"
      shift
      ;;
  esac
done

if ! cloud_load_auth; then
  echo "error: CURSOR_API_KEY is not set (export it or add it to ~/.config/cursor/agent.env)" >&2
  exit 1
fi

list_out="$("${HERE}/list.sh" --limit "$limit")"
repo="${GCS_CLOUD_REPO:-${CLOUD_REPO_URL:-}}"
python3 "${HERE}/capacity.py" decide-from-list --work "$work" --repo "$repo" <<<"$list_out"
