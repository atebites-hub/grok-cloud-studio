#!/usr/bin/env bash
# Status for one or more Cursor Cloud agents. SDK-first; REST fallback.
# Usage: status-cloud-agent.sh <bc-id> [<bc-id>...] [--ids ID,ID] [--json]
# Prints runStatus per id. Parallel fetch — do not remint list.sh #29.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$HERE/status.sh" "$@"
