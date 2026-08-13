#!/usr/bin/env bash
# Start/stop/status for local Grok Cloud Studio A2A hub + inbox dispatch + bot-bridge + fleet shepherd.
# Seat ACP daemons are opt-in: GCS_START_SEAT_DAEMONS=1 or `start --daemons`.
# Usage:
#   start-studio-bus.sh          # start hub+dispatch+shepherd (idempotent)
#   start-studio-bus.sh start
#   start-studio-bus.sh start --daemons
#   start-studio-bus.sh stop
#   start-studio-bus.sh stop --daemons
#   start-studio-bus.sh status
# Local studio only. Pid/logs under .a2a-state/.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${GCS_ROOT:-$SCRIPT_DIR/../..}" && pwd)"
export GCS_ROOT="$ROOT"
STATE_DIR="${GCS_A2A_STATE:-$ROOT/.a2a-state}"
HUB_PY="$SCRIPT_DIR/hub.py"
DISPATCH_PY="$SCRIPT_DIR/dispatch.py"
BOT_BRIDGE_PY="$SCRIPT_DIR/bot-bridge.py"
HUB_PID_FILE="$STATE_DIR/hub.pid"
DISPATCH_PID_FILE="$STATE_DIR/dispatch.pid"
BOT_BRIDGE_PID_FILE="$STATE_DIR/bot-bridge.pid"
HUB_LOG="$STATE_DIR/hub.log"
DISPATCH_LOG="$STATE_DIR/dispatch.log"
BOT_BRIDGE_LOG="$STATE_DIR/bot-bridge.log"
SHEPHERD_PY="$ROOT/scripts/directors/fleet-shepherd.py"
SHEPHERD_PID_FILE="$STATE_DIR/fleet-shepherd.pid"
SHEPHERD_LOG="$STATE_DIR/fleet-shepherd.log"
START_DAEMON="$ROOT/scripts/directors/start-seat-daemon.sh"
STOP_DAEMON="$ROOT/scripts/directors/stop-seat-daemon.sh"
STATUS_DAEMON="$ROOT/scripts/directors/status-seat-daemon.sh"
DAEMONS_FLAG="$STATE_DIR/daemons.enabled"
LIB_PY="$SCRIPT_DIR/lib.py"

mkdir -p "$STATE_DIR"

usage() {
  cat <<'EOF'
Usage: start-studio-bus.sh [start|stop|status] [--daemons]

start            hub + dispatch + fleet-shepherd (idempotent)
start --daemons  also start per-seat ACP daemons (writes daemons.enabled)
stop             stop hub/dispatch/shepherd (leaves seat daemons)
stop --daemons   also stop seat ACP daemons and clear daemons.enabled
status           print bus + optional daemon flag

Opt-in without the flag: GCS_START_SEAT_DAEMONS=1
Do not spawn a grok agent process per seat by surprise; daemons are explicit.
See docs/ARCHITECTURE.md.
EOF
}

pid_alive() {
  local pid="${1:-}" state
  [[ -n "$pid" ]] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  state=$(ps -p "$pid" -o state= 2>/dev/null | tr -d '[:space:]')
  [[ "$state" == Z* ]] && return 1
  return 0
}

read_pid() {
  local f="$1"
  if [[ -f "$f" ]]; then
    tr -d '[:space:]' < "$f" || true
  fi
}

acp_seats() {
  python3 "$LIB_PY" launch-seats
}

want_daemons() {
  [[ "${WITH_DAEMONS:-0}" == "1" ]] && return 0
  [[ "${GCS_START_SEAT_DAEMONS:-0}" == "1" ]] && return 0
  [[ -f "$DAEMONS_FLAG" ]] && return 0
  return 1
}

start_seat_daemons() {
  local seat
  if [[ ! -f "$START_DAEMON" ]]; then
    echo "STUDIO_BUS_DAEMONS_SKIP missing $START_DAEMON"
    return 0
  fi
  touch "$DAEMONS_FLAG"
  while read -r seat; do
    [[ -z "$seat" ]] && continue
    if bash "$START_DAEMON" "$seat"; then
      :
    else
      echo "STUDIO_BUS_DAEMON_FAIL seat=$seat" >&2
    fi
  done < <(acp_seats)
}

stop_seat_daemons() {
  local seat
  if [[ ! -f "$STOP_DAEMON" ]]; then
    return 0
  fi
  while read -r seat; do
    [[ -z "$seat" ]] && continue
    bash "$STOP_DAEMON" "$seat" || true
  done < <(acp_seats)
  rm -f "$DAEMONS_FLAG"
}

status_seat_daemons() {
  local seat up=0 down=0
  if [[ ! -f "$STATUS_DAEMON" ]]; then
    echo "STUDIO_BUS_DAEMONS_STATUS unavailable"
    return 0
  fi
  while read -r seat; do
    [[ -z "$seat" ]] && continue
    if bash "$STATUS_DAEMON" "$seat"; then
      up=$((up + 1))
    else
      down=$((down + 1))
    fi
  done < <(acp_seats)
  echo "STUDIO_BUS_DAEMONS_SUMMARY up=$up down=$down"
}

WITH_DAEMONS=0
cmd="${1:-start}"
shift || true
case "$cmd" in
  -h|--help)
    usage
    exit 0
    ;;
  --daemons)
    WITH_DAEMONS=1
    cmd="start"
    ;;
  start|stop|status) ;;
  *)
    echo "error: unknown command $cmd" >&2
    usage >&2
    exit 2
    ;;
esac
for arg in "$@"; do
  case "$arg" in
    --daemons) WITH_DAEMONS=1 ;;
    *)
      echo "error: unknown option $arg" >&2
      usage >&2
      exit 2
      ;;
  esac
done

case "$cmd" in
  start)
    hub_pid="$(read_pid "$HUB_PID_FILE")"
    disp_pid="$(read_pid "$DISPATCH_PID_FILE")"
    hub_running=0
    disp_running=0
    if pid_alive "$hub_pid"; then hub_running=1; fi
    if pid_alive "$disp_pid"; then disp_running=1; fi

    export GCS_ROOT="$ROOT"
    export GCS_A2A_STATE="$STATE_DIR"

    if [[ "$hub_running" != "1" ]]; then
      rm -f "$HUB_PID_FILE"
      nohup python3 "$HUB_PY" >>"$HUB_LOG" 2>&1 &
      echo $! >"$HUB_PID_FILE"
      hub_pid="$(read_pid "$HUB_PID_FILE")"
      sleep 0.3
      if ! pid_alive "$hub_pid"; then
        echo "STUDIO_BUS_FAIL hub did not stay up; see $HUB_LOG" >&2
        exit 1
      fi
      echo "STUDIO_BUS_HUB_START pid=$hub_pid log=$HUB_LOG"
    else
      echo "STUDIO_BUS_HUB_ALREADY pid=$hub_pid"
    fi

    if [[ "$disp_running" != "1" ]]; then
      rm -f "$DISPATCH_PID_FILE"
      nohup python3 "$DISPATCH_PY" >>"$DISPATCH_LOG" 2>&1 &
      echo $! >"$DISPATCH_PID_FILE"
      disp_pid="$(read_pid "$DISPATCH_PID_FILE")"
      sleep 0.3
      if ! pid_alive "$disp_pid"; then
        echo "STUDIO_BUS_FAIL dispatch did not stay up; see $DISPATCH_LOG" >&2
        exit 1
      fi
      echo "STUDIO_BUS_DISPATCH_START pid=$disp_pid log=$DISPATCH_LOG"
    else
      echo "STUDIO_BUS_DISPATCH_ALREADY pid=$disp_pid"
    fi

    shep_pid="$(read_pid "$SHEPHERD_PID_FILE")"
    if pid_alive "$shep_pid"; then
      echo "STUDIO_BUS_SHEPHERD_ALREADY pid=$shep_pid"
    else
      rm -f "$SHEPHERD_PID_FILE"
      nohup python3 "$SHEPHERD_PY" >>"$SHEPHERD_LOG" 2>&1 &
      echo $! >"$SHEPHERD_PID_FILE"
      shep_pid="$(read_pid "$SHEPHERD_PID_FILE")"
      sleep 0.2
      if ! pid_alive "$shep_pid"; then
        echo "STUDIO_BUS_FAIL shepherd did not stay up; see $SHEPHERD_LOG" >&2
      else
        echo "STUDIO_BUS_SHEPHERD_START pid=$shep_pid log=$SHEPHERD_LOG"
      fi
    fi

    bridge_pid="$(read_pid "$BOT_BRIDGE_PID_FILE")"
    if pid_alive "$bridge_pid"; then
      echo "STUDIO_BUS_BOT_BRIDGE_ALREADY pid=$bridge_pid"
    else
      rm -f "$BOT_BRIDGE_PID_FILE"
      if [[ -f "$BOT_BRIDGE_PY" ]]; then
        nohup python3 "$BOT_BRIDGE_PY" >>"$BOT_BRIDGE_LOG" 2>&1 &
        echo $! >"$BOT_BRIDGE_PID_FILE"
        bridge_pid="$(read_pid "$BOT_BRIDGE_PID_FILE")"
        sleep 0.2
        if ! pid_alive "$bridge_pid"; then
          echo "STUDIO_BUS_FAIL bot-bridge did not stay up; see $BOT_BRIDGE_LOG" >&2
        else
          echo "STUDIO_BUS_BOT_BRIDGE_START pid=$bridge_pid log=$BOT_BRIDGE_LOG"
        fi
      else
        echo "STUDIO_BUS_BOT_BRIDGE_SKIP missing $BOT_BRIDGE_PY"
        bridge_pid=""
      fi
    fi

    if want_daemons; then
      start_seat_daemons
    else
      echo "STUDIO_BUS_DAEMONS_SKIP (pass --daemons or GCS_START_SEAT_DAEMONS=1)"
    fi

    echo "STUDIO_BUS_READY hub_pid=$hub_pid dispatch_pid=$disp_pid shepherd_pid=$shep_pid bot_bridge_pid=${bridge_pid:-none} state=$STATE_DIR"
    ;;

  stop)
    hub_pid="$(read_pid "$HUB_PID_FILE")"
    disp_pid="$(read_pid "$DISPATCH_PID_FILE")"
    shep_pid="$(read_pid "$SHEPHERD_PID_FILE")"
    bridge_pid="$(read_pid "$BOT_BRIDGE_PID_FILE")"
    if pid_alive "$bridge_pid"; then
      kill "$bridge_pid" 2>/dev/null || true
      for _ in 1 2 3 4 5; do
        pid_alive "$bridge_pid" || break
        sleep 0.2
      done
      if pid_alive "$bridge_pid"; then
        kill -9 "$bridge_pid" 2>/dev/null || true
      fi
      echo "STUDIO_BUS_BOT_BRIDGE_STOP pid=$bridge_pid"
    else
      echo "STUDIO_BUS_BOT_BRIDGE_NOT_RUNNING"
    fi
    rm -f "$BOT_BRIDGE_PID_FILE"
    if pid_alive "$shep_pid"; then
      kill "$shep_pid" 2>/dev/null || true
      for _ in 1 2 3 4 5; do
        pid_alive "$shep_pid" || break
        sleep 0.2
      done
      if pid_alive "$shep_pid"; then
        kill -9 "$shep_pid" 2>/dev/null || true
      fi
      echo "STUDIO_BUS_SHEPHERD_STOP pid=$shep_pid"
    else
      echo "STUDIO_BUS_SHEPHERD_NOT_RUNNING"
    fi
    rm -f "$SHEPHERD_PID_FILE"
    if pid_alive "$disp_pid"; then
      kill "$disp_pid" 2>/dev/null || true
      for _ in 1 2 3 4 5; do
        pid_alive "$disp_pid" || break
        sleep 0.2
      done
      if pid_alive "$disp_pid"; then
        kill -9 "$disp_pid" 2>/dev/null || true
      fi
      echo "STUDIO_BUS_DISPATCH_STOP pid=$disp_pid"
    else
      echo "STUDIO_BUS_DISPATCH_NOT_RUNNING"
    fi
    rm -f "$DISPATCH_PID_FILE"

    if pid_alive "$hub_pid"; then
      kill "$hub_pid" 2>/dev/null || true
      for _ in 1 2 3 4 5; do
        pid_alive "$hub_pid" || break
        sleep 0.2
      done
      if pid_alive "$hub_pid"; then
        kill -9 "$hub_pid" 2>/dev/null || true
      fi
      echo "STUDIO_BUS_HUB_STOP pid=$hub_pid"
    else
      echo "STUDIO_BUS_HUB_NOT_RUNNING"
    fi
    rm -f "$HUB_PID_FILE"
    if [[ "$WITH_DAEMONS" == "1" || "${GCS_ACP_STOP_WITH_BUS:-0}" == "1" ]]; then
      stop_seat_daemons
    else
      echo "STUDIO_BUS_DAEMONS_LEFT_RUNNING (pass stop --daemons to stop)"
    fi
    echo "STUDIO_BUS_STOPPED"
    ;;

  status)
    hub_pid="$(read_pid "$HUB_PID_FILE")"
    disp_pid="$(read_pid "$DISPATCH_PID_FILE")"
    hub_state="down"
    disp_state="down"
    if pid_alive "$hub_pid"; then hub_state="up"; fi
    if pid_alive "$disp_pid"; then disp_state="up"; fi
    shep_pid="$(read_pid "$SHEPHERD_PID_FILE")"
    shep_state="down"
    if pid_alive "$shep_pid"; then shep_state="up"; fi
    bridge_pid="$(read_pid "$BOT_BRIDGE_PID_FILE")"
    bridge_state="down"
    if pid_alive "$bridge_pid"; then bridge_state="up"; fi
    daemon_flag="off"
    [[ -f "$DAEMONS_FLAG" ]] && daemon_flag="on"
    echo "STUDIO_BUS_STATUS hub=$hub_state pid=${hub_pid:-none} dispatch=$disp_state pid=${disp_pid:-none} shepherd=$shep_state pid=${shep_pid:-none} bot_bridge=$bridge_state pid=${bridge_pid:-none} daemons=$daemon_flag state=$STATE_DIR"
    if [[ "$daemon_flag" == "on" ]] || want_daemons; then
      status_seat_daemons || true
    fi
    if [[ "$hub_state" == "up" && "$disp_state" == "up" && "$shep_state" == "up" ]]; then
      exit 0
    fi
    exit 1
    ;;
esac
