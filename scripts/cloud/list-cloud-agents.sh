#!/usr/bin/env bash
# List Cursor Cloud agents. SDK-first; REST fallback.
# Usage: list-cloud-agents.sh [--limit N] [--repo org/name|https://github.com/org/name]
# Each row prints status and latest-run runStatus. Leftover ACTIVE is not capacity.
# Palemon Linear is Living Sky (LIV), not Black Swan. Never Bot CloudAgent.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$HERE/list.sh" "$@"
