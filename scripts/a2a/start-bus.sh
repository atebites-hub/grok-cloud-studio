#!/usr/bin/env bash
# Compatibility entrypoint. Canonical bus is start-studio-bus.sh.
# Seat ACP daemons are opt-in: --daemons or GCS_START_SEAT_DAEMONS=1.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$SCRIPT_DIR/start-studio-bus.sh" "$@"
