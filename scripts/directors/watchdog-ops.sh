#!/usr/bin/env bash
# Canonical watchdog name. Keeps the local bus and ops seat alive.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
exec bash "$ROOT/scripts/directors/watchdog-studio-ops.sh" "$@"
