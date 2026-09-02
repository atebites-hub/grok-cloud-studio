#!/usr/bin/env bash
# Occupancy catalog: paginate Agent.list / GET /v1/agents beyond limit=100.
# Fail-closed if a page errors — never fake running=0. Existence ACTIVE is
# not liveness. Never prints API keys.
# Usage: occupancy-count.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "${HERE}/_common.sh"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      echo "Usage: scripts/cloud/occupancy-count.sh"
      echo "Paginated occupancy catalog (nextCursor, page size 100). Fail-closed on page error."
      exit 0
      ;;
    *)
      echo "error: unknown option $1" >&2
      exit 1
      ;;
  esac
done

if ! cloud_load_auth; then
  echo "CLOUD_OCCUPANCY_ERR reason=err CURSOR_API_KEY missing" >&2
  exit 1
fi

if cloud_sdk_exec occupancy; then
  exit "$CLOUD_SDK_RC"
fi

python3 "${HERE}/occupancy_count.py"
