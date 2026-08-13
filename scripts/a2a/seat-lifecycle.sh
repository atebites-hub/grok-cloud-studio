#!/usr/bin/env bash
# Control plane for Grok Build Director ACP seats (start|stop|restart|status).
# Reuses scripts/directors/{start,stop,status}-seat-daemon.sh + seat-daemon-common.sh.
#
# Usage:
#   seat-lifecycle.sh start|stop|restart|status <seat|--all>
#   seat-lifecycle.sh --help
#
# Optional A2A control (ops / lifecycle seat):
#   MESSAGE text "SEAT_UP seat=floor"  or  "SEAT_DOWN seat=floor"  or  "SEAT_STATUS seat=all"
#   seat-lifecycle.sh handle-message "<raw message text>"
#
# Crash hardening: clears stale pid files when process is dead/zombie; status is explicit.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${GCS_ROOT:-$SCRIPT_DIR/../..}" && pwd)"
export GCS_ROOT="$ROOT"
DIR_SCRIPTS="$ROOT/scripts/directors"
# shellcheck source=../directors/seat-daemon-common.sh
source "$DIR_SCRIPTS/seat-daemon-common.sh"

START_DAEMON="$DIR_SCRIPTS/start-seat-daemon.sh"
STOP_DAEMON="$DIR_SCRIPTS/stop-seat-daemon.sh"
STATUS_DAEMON="$DIR_SCRIPTS/status-seat-daemon.sh"

usage() {
  cat <<'USAGE'
Usage: seat-lifecycle.sh <start|stop|restart|status> <seat|--all>
       seat-lifecycle.sh handle-message "<SEAT_UP|SEAT_DOWN|SEAT_STATUS ...>"

Controls Grok Build Director ACP seats (grok agent serve).
REPORT_TO=ops for Director fleet orchestration (override via registry).

Examples:
  seat-lifecycle.sh start ops
  seat-lifecycle.sh stop --all
  seat-lifecycle.sh restart floor
  seat-lifecycle.sh status --all
  seat-lifecycle.sh handle-message "SEAT_UP seat=cloud"
USAGE
}

clear_stale_pid() {
  local seat="$1"
  local sd pid
  sd="$(seat_state_dir "$seat")"
  pid="$(read_pid_file "$sd/daemon.pid")"
  if [[ -n "$pid" ]] && ! pid_alive "$pid"; then
    rm -f "$sd/daemon.pid"
    echo "SEAT_LIFECYCLE_STALE_PID_CLEARED seat=$seat pid=$pid"
  fi
  # Stale inject lock left after crash
  if [[ -f "$sd/acp.inject.lock" ]]; then
    local lock_pid
    lock_pid="$(tr -d '[:space:]' <"$sd/acp.inject.lock" 2>/dev/null || true)"
    if [[ -n "$lock_pid" ]] && ! pid_alive "$lock_pid"; then
      rm -f "$sd/acp.inject.lock"
      echo "SEAT_LIFECYCLE_STALE_LOCK_CLEARED seat=$seat lock_pid=$lock_pid"
    fi
  fi
}

seats_for() {
  local target="$1"
  if [[ "$target" == "--all" || "$target" == "all" ]]; then
    printf '%s\n' "${LAUNCH_SEATS[@]}"
    return 0
  fi
  normalize_seat "$target"
}

cmd_start() {
  local seat
  while read -r seat; do
    [[ -z "$seat" ]] && continue
    clear_stale_pid "$seat"
    bash "$START_DAEMON" "$seat"
  done < <(seats_for "$1")
}

cmd_stop() {
  local seat
  while read -r seat; do
    [[ -z "$seat" ]] && continue
    bash "$STOP_DAEMON" "$seat" || true
    clear_stale_pid "$seat"
  done < <(seats_for "$1")
}

cmd_restart() {
  local seat
  while read -r seat; do
    [[ -z "$seat" ]] && continue
    bash "$STOP_DAEMON" "$seat" || true
    clear_stale_pid "$seat"
    sleep 0.2
    bash "$START_DAEMON" "$seat"
  done < <(seats_for "$1")
}

cmd_status() {
  local seat rc=0
  while read -r seat; do
    [[ -z "$seat" ]] && continue
    clear_stale_pid "$seat"
    bash "$STATUS_DAEMON" "$seat" || rc=1
  done < <(seats_for "$1")
  return "$rc"
}

handle_message() {
  local text="${1:-}"
  local action seat
  action="$(printf '%s' "$text" | tr '[:lower:]' '[:upper:]' | awk '{print $1}')"
  seat="$(printf '%s' "$text" | sed -n 's/.*seat=\([A-Za-z0-9_-]\+\).*/\1/p' | head -n1)"
  if [[ -z "$seat" ]]; then
    seat="$(printf '%s' "$text" | awk '{print $2}')"
  fi
  case "$action" in
    SEAT_UP)
      [[ -n "$seat" ]] || { echo "SEAT_LIFECYCLE_ERR missing seat" >&2; return 2; }
      cmd_start "$seat"
      ;;
    SEAT_DOWN)
      [[ -n "$seat" ]] || { echo "SEAT_LIFECYCLE_ERR missing seat" >&2; return 2; }
      cmd_stop "$seat"
      ;;
    SEAT_RESTART)
      [[ -n "$seat" ]] || { echo "SEAT_LIFECYCLE_ERR missing seat" >&2; return 2; }
      cmd_restart "$seat"
      ;;
    SEAT_STATUS)
      cmd_status "${seat:-all}"
      ;;
    *)
      echo "SEAT_LIFECYCLE_ERR unknown action (want SEAT_UP|SEAT_DOWN|SEAT_RESTART|SEAT_STATUS)" >&2
      return 2
      ;;
  esac
}

CMD="${1:-}"
TARGET="${2:-}"

case "$CMD" in
  -h|--help|help|"")
    usage
    exit 0
    ;;
  start|stop|restart|status)
    if [[ -z "$TARGET" ]]; then
      usage >&2
      exit 2
    fi
    "cmd_${CMD}" "$TARGET"
    ;;
  handle-message)
    handle_message "${2:-}"
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
