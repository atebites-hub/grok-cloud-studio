#!/usr/bin/env bash
# Count runStatus=RUNNING toward the per-repo Extra High floor (LIV-67).
# Leftover agent status=ACTIVE with latest-run FINISHED is not capacity.
# CREATING is not RUNNING. Capacity beats call this, not GCS #78 list running filters.
# Usage: capacity-count.sh [--limit N] [--repo org/name|https://github.com/org/name]
# Never Bot CloudAgent. Never prints API keys.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "${HERE}/_common.sh"

limit="${CLOUD_LIST_LIMIT:-50}"
repo=""
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
      echo "Usage: scripts/cloud/capacity-count.sh [--limit N] [--repo org/name|https://github.com/org/name]"
      echo "Prints CLOUD_CAPACITY repo=org/name running=N floor=8 leftover_active=N must_launch=0|1 deficit=N"
      echo "Count latest-run runStatus=RUNNING. Leftover agent status=ACTIVE with runStatus=FINISHED is not the floor."
      echo "CREATING is not RUNNING. Capacity beats call this helper (not GCS #78 list running filters)."
      echo "Never Bot CloudAgent. Model grok-4.6 xhigh fast=false."
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
# Always REST-annotate runStatus here. Do not remint GCS #78 list running filters.
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
  python3 "${HERE}/capacity_count.py" --repo "$repo" "$CLOUD_HTTP_BODY"
else
  python3 "${HERE}/capacity_count.py" "$CLOUD_HTTP_BODY"
fi
