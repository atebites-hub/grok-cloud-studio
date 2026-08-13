#!/usr/bin/env bash
# Stop a per-seat persistent Grok ACP daemon.
# Usage: stop-seat-daemon.sh <seat|all>
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=seat-daemon-common.sh
source "$SCRIPT_DIR/seat-daemon-common.sh"

TARGET="${1:-}"
if [[ -z "$TARGET" || "$TARGET" == "-h" || "$TARGET" == "--help" ]]; then
  echo "Usage: $(basename "$0") <seat|all>" >&2
  exit 2
fi

stop_one() {
  local seat="$1"
  local sd pid
  sd="$(seat_state_dir "$seat")"
  pid="$(read_pid_file "$sd/daemon.pid")"
  if pid_alive "$pid"; then
    kill "$pid" 2>/dev/null || true
    for _ in 1 2 3 4 5 6 7 8 9 10; do
      pid_alive "$pid" || break
      sleep 0.2
    done
    if pid_alive "$pid"; then
      kill -9 "$pid" 2>/dev/null || true
    fi
    echo "SEAT_DAEMON_STOP seat=$seat pid=$pid"
  else
    echo "SEAT_DAEMON_NOT_RUNNING seat=$seat"
  fi
  rm -f "$sd/daemon.pid"
  # Keep acp.secret / acp.session / agent-profile for resume across restarts.
}

if [[ "$TARGET" == "all" ]]; then
  for s in "${LAUNCH_SEATS[@]}"; do
    stop_one "$s"
  done
  exit 0
fi

SEAT="$(normalize_seat "$TARGET")" || exit $?
stop_one "$SEAT"
