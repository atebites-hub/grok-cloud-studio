#!/usr/bin/env bash
# List Cursor Cloud agents. SDK-first; REST fallback.
# Usage: list-cloud-agents.sh [limit=20] [--occupancy]
# Each row prints agent status and latest-run runStatus.
# --occupancy lists hive occupancy (RUNNING/CREATING), not leftover ACTIVE.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$HERE/list.sh" "$@"
