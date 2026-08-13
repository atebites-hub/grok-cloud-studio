#!/usr/bin/env bash
# Poll a Cursor Cloud agent until latest run is terminal. SDK-first.
# Usage: watch-cloud-agent.sh <bc-id> [timeout_sec=1800] [poll_sec=30]
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ID="${1:-}"
if [[ -z "$ID" || "$ID" == "-h" || "$ID" == "--help" ]]; then
  echo "usage: $0 <bc-id> [timeout_sec=1800] [poll_sec=30]" >&2
  [[ "${ID:-}" == "-h" || "${ID:-}" == "--help" ]] && exit 0
  exit 2
fi
if [[ -n "${2:-}" ]]; then
  export CLOUD_WATCH_TIMEOUT_SEC="$2"
fi
if [[ -n "${3:-}" ]]; then
  export CLOUD_WATCH_INTERVAL="$3"
fi
export CLOUD_WATCH_TIMEOUT_SEC="${CLOUD_WATCH_TIMEOUT_SEC:-1800}"
export CLOUD_WATCH_INTERVAL="${CLOUD_WATCH_INTERVAL:-30}"
exec "$HERE/watch.sh" "$ID"
