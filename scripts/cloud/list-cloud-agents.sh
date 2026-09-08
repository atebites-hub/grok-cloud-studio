#!/usr/bin/env bash
# List Cursor Cloud agents. SDK-first; REST fallback.
# Usage: list-cloud-agents.sh [--limit N] [--repo org/name|https://github.com/org/name]
# Each row prints agent status and latest-run runStatus.
# Count runStatus=RUNNING for --repo. Leftover ACTIVE is not capacity.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$HERE/list.sh" "$@"
