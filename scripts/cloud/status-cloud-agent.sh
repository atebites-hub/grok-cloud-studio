#!/usr/bin/env bash
# Status for one Cursor Cloud agent. SDK-first; REST fallback.
# Usage: status-cloud-agent.sh <bc-id> [--json]
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$HERE/status.sh" "$@"
