#!/usr/bin/env bash
# Status for per-seat ACP daemons.
# Usage: status-seat-daemon.sh <seat|all>
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=seat-daemon-common.sh
source "$SCRIPT_DIR/seat-daemon-common.sh"

TARGET="${1:-all}"

status_one() {
  local seat="$1"
  local sd pid port url session state
  sd="$(seat_state_dir "$seat")"
  pid="$(read_pid_file "$sd/daemon.pid")"
  port="$(seat_port "$seat" || echo none)"
  url="none"
  [[ -f "$sd/acp.url" ]] && url="$(tr -d '\n' <"$sd/acp.url")"
  session="none"
  [[ -f "$sd/acp.session" ]] && session="$(tr -d '[:space:]' <"$sd/acp.session")"
  state="down"
  if daemon_healthy "$seat"; then
    state="up"
  elif pid_alive "$pid"; then
    state="starting-or-unhealthy"
  fi
  echo "SEAT_DAEMON_STATUS seat=$seat state=$state pid=${pid:-none} port=$port session=$session url=$url"
  [[ "$state" == "up" ]]
}

rc=0
if [[ "$TARGET" == "all" ]]; then
  for s in "${LAUNCH_SEATS[@]}"; do
    status_one "$s" || rc=1
  done
  exit "$rc"
fi

SEAT="$(normalize_seat "$TARGET")" || exit $?
status_one "$SEAT"
