#!/usr/bin/env bash
# Occupancy counts for capacity beats. SDK Agent.list + listRuns; REST fallback.
# Bounded concurrency, per-call timeout, fail-closed on ERR (no hang, no fake running=0).
# Existence ACTIVE/IDLE is not liveness. Never prints API keys.
# Usage: occupancy-count.sh [--limit N]   or   occupancy-count.sh [N]
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "${HERE}/_common.sh"

limit="${CLOUD_OCCUPANCY_LIMIT:-${CLOUD_LIST_LIMIT:-100}}"
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
      echo "Usage: scripts/cloud/occupancy-count.sh [--limit N]"
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
  echo "CLOUD_OCCUPANCY_ERR reason=err CURSOR_API_KEY missing" >&2
  exit 1
fi

if cloud_sdk_exec occupancy "$limit"; then
  exit "$CLOUD_SDK_RC"
fi

python3 "${HERE}/occupancy_count.py" --limit "$limit"
