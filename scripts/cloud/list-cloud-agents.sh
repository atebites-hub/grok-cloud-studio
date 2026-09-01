#!/usr/bin/env bash
# List Cursor Cloud agents. SDK-first; REST fallback.
# Usage: list-cloud-agents.sh [--running] [limit=20]
# Each row prints agent status and latest-run runStatus.
# --running keeps latest-run runStatus=RUNNING only (existence is not liveness).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$HERE/list.sh" "$@"
