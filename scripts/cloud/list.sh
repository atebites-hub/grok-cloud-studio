#!/usr/bin/env bash
# List Cursor Cloud agents (newest first). SDK-first; REST fallback.
# Usage: list.sh [--limit N] [--repo org/name|https://github.com/org/name]
#        list.sh [N]
# Each row prints status= (membership) and runStatus= (latest run).
# Count runStatus=RUNNING for --repo. Leftover ACTIVE is not capacity.
# Palemon Linear is Living Sky (LIV), not Black Swan. Never Bot CloudAgent.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "${HERE}/_common.sh"

limit="${CLOUD_LIST_LIMIT:-20}"
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
      echo "Usage: scripts/cloud/list.sh [--limit N] [--repo org/name|https://github.com/org/name]"
      echo "       scripts/cloud/list-cloud-agents.sh [--limit N] [--repo org/name]"
      echo "Each row prints status= (membership) and runStatus= (latest run)."
      echo "Count runStatus=RUNNING for the bound repo. Leftover ACTIVE is not capacity."
      echo "Palemon Linear is Living Sky (LIV), not Black Swan. Never Bot CloudAgent."
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

sdk_args=(list --limit "$limit")
if [[ -n "$repo" ]]; then
  sdk_args+=(--repo "$repo")
fi
if cloud_sdk_exec "${sdk_args[@]}"; then
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
# Fetch each latest run so rows show runStatus (RUNNING vs FINISHED).
# --repo loads GET /v1/agents/{id} for bound repos[0].url (list items omit repos).
if [[ -n "$repo" ]]; then
  python3 "${HERE}/list_format.py" --repo "$repo" "$CLOUD_HTTP_BODY"
else
  python3 "${HERE}/list_format.py" "$CLOUD_HTTP_BODY"
fi
