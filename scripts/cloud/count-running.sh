#!/usr/bin/env bash
# Count runStatus=RUNNING per bound Cursor Cloud repo.
# Leftover agent ACTIVE is membership, not capacity. CREATING is not RUNNING.
# Usage: count-running.sh [--limit N] [--repo org/name|https://github.com/org/name]
# Palemon Linear is Living Sky (LIV), not Black Swan. Never Bot CloudAgent.
# Does not remint list --repo (GCS #50) or list runStatus rows (GCS #29).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "${HERE}/_common.sh"

limit="${CLOUD_LIST_LIMIT:-50}"
repo=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --limit)
      if [[ $# -lt 2 ]]; then
        echo "error: --limit requires a positive integer" >&2
        exit 1
      fi
      limit="$2"
      if [[ ! "$limit" =~ ^[0-9]+$ ]]; then
        echo "error: --limit requires a positive integer" >&2
        exit 1
      fi
      shift 2
      ;;
    --limit=*)
      limit="${1#--limit=}"
      if [[ ! "$limit" =~ ^[0-9]+$ ]]; then
        echo "error: --limit requires a positive integer" >&2
        exit 1
      fi
      shift
      ;;
    --repo)
      if [[ $# -lt 2 ]]; then
        echo "error: --repo requires org/name or https URL" >&2
        exit 1
      fi
      repo="$2"
      shift 2
      ;;
    --repo=*)
      repo="${1#--repo=}"
      shift
      ;;
    -h|--help)
      echo "Usage: scripts/cloud/count-running.sh [--limit N] [--repo org/name|https://github.com/org/name]"
      echo "Prints CLOUD_RUNNING repo=org/name running=N using latest-run runStatus=RUNNING."
      echo "Leftover agent status=ACTIVE is not capacity. CREATING is not RUNNING."
      echo "Palemon Linear is Living Sky (LIV), not Black Swan. Never Bot CloudAgent."
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

# Bound repos live on GET /v1/agents/{id}; list items omit them.
# Always REST-annotate runStatus here. Do not call list.sh --repo.
if ! cloud_http_request GET "/v1/agents?limit=${limit}"; then
  echo "error: curl failed http=${CLOUD_HTTP_CODE:-000}" >&2
  exit 1
fi
if ! cloud_http_is_2xx; then
  echo "error: list failed http=${CLOUD_HTTP_CODE}" >&2
  cloud_redact_stream <"$CLOUD_HTTP_BODY" >&2 || true
  exit 1
fi

if [[ -n "$repo" ]]; then
  python3 "${HERE}/count_running.py" --repo "$repo" "$CLOUD_HTTP_BODY"
else
  python3 "${HERE}/count_running.py" "$CLOUD_HTTP_BODY"
fi
