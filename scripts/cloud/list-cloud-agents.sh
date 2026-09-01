#!/usr/bin/env bash
# List Cursor Cloud agents. SDK-first; REST fallback.
# Usage: list-cloud-agents.sh [limit=20]
# Compact rows include runStatus= and prUrl= so capacity beats skip N status.sh.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$HERE/list.sh" "$@"
