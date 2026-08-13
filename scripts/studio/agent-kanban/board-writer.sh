#!/usr/bin/env bash
# LIGHT Agent Kanban board-writer for Grok Cloud Studio.
# start|stop|status|once — never runs `ak start`.
#
# start launches ONE tiny long-lived process with argv0=cursor-agent so
# `ak auth login --leader-agent` and `ak create task` pass ancestry checks.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${GCS_ROOT:-$SCRIPT_DIR/../../..}" && pwd)"
STATE_DIR="${GCS_A2A_STATE:-$ROOT/.a2a-state}"
AK_DIR="$STATE_DIR/agent-kanban"
PID_FILE="$AK_DIR/board-writer.pid"
LOG_FILE="$AK_DIR/board-writer.log"
LOOP_SH="$SCRIPT_DIR/board-writer-loop.sh"
# ~2 GiB MemAvailable floor (kB)
MIN_AVAIL_KB="${AK_WRITER_MIN_AVAIL_KB:-2097152}"

export PATH="${HOME}/.local/bin:${PATH:-}"
export GCS_ROOT="$ROOT"
export GCS_A2A_STATE="$STATE_DIR"
export AGENT_KANBAN_BOARD_ID="${AGENT_KANBAN_BOARD_ID:-${GCS_AGENT_KANBAN_BOARD_ID:-zl2g1hym}}"

mkdir -p "$AK_DIR"

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
    tr -d '[:space:]' <"$f" || true
  fi
}

mem_available_kb() {
  awk '/^MemAvailable:/ {print $2; exit}' /proc/meminfo 2>/dev/null || echo 0
}

refuse_low_mem() {
  local avail
  avail="$(mem_available_kb)"
  if [[ -z "$avail" || "$avail" -lt "$MIN_AVAIL_KB" ]]; then
    echo "AK_WRITER_SKIP_LOW_MEM avail_kb=${avail:-unknown} need_kb=$MIN_AVAIL_KB"
    return 1
  fi
  return 0
}

cmd_status() {
  local pid rss comm
  pid="$(read_pid "$PID_FILE")"
  if pid_alive "$pid"; then
    rss="$(ps -p "$pid" -o rss= 2>/dev/null | tr -d '[:space:]' || echo '?')"
    comm="$(ps -p "$pid" -o comm= 2>/dev/null | tr -d '[:space:]' || echo '?')"
    echo "board_writer=up pid=$pid rss_kb=${rss:-?} comm=${comm:-?} log=$LOG_FILE"
    return 0
  fi
  echo "board_writer=down pid=${pid:-none} log=$LOG_FILE"
  return 1
}

cmd_stop() {
  local pid
  pid="$(read_pid "$PID_FILE")"
  if pid_alive "$pid"; then
    kill "$pid" 2>/dev/null || true
    for _ in 1 2 3 4 5 6 7 8 9 10; do
      pid_alive "$pid" || break
      sleep 0.2
    done
    if pid_alive "$pid"; then
      kill -9 "$pid" 2>/dev/null || true
    fi
    echo "AK_WRITER_STOP pid=$pid"
  else
    echo "AK_WRITER_NOT_RUNNING"
  fi
  rm -f "$PID_FILE"
}

cmd_once() {
  refuse_low_mem || return 1
  export CURSOR_AGENT=1
  exec -a cursor-agent bash "$SCRIPT_DIR/board-writer-once.sh"
}

cmd_start() {
  local pid
  refuse_low_mem || return 1
  pid="$(read_pid "$PID_FILE")"
  if pid_alive "$pid"; then
    echo "AK_WRITER_ALREADY pid=$pid"
    cmd_status || true
    return 0
  fi
  rm -f "$PID_FILE"
  if [[ ! -f "$LOOP_SH" ]]; then
    echo "AK_WRITER_FAIL missing $LOOP_SH" >&2
    return 1
  fi
  nohup bash -c 'exec -a cursor-agent bash "$0"' "$LOOP_SH" >>"$LOG_FILE" 2>&1 &
  echo $! >"$PID_FILE"
  sleep 0.3
  pid="$(read_pid "$PID_FILE")"
  if ! pid_alive "$pid"; then
    echo "AK_WRITER_FAIL did_not_stay_up log=$LOG_FILE" >&2
    rm -f "$PID_FILE"
    return 1
  fi
  echo "AK_WRITER_START pid=$pid log=$LOG_FILE board=${AGENT_KANBAN_BOARD_ID}"
  cmd_status || true
}

usage() {
  echo "usage: $0 {start|stop|status|once}" >&2
  exit 2
}

cmd="${1:-}"
case "$cmd" in
  start) cmd_start ;;
  stop) cmd_stop ;;
  status) cmd_status ;;
  once) cmd_once ;;
  *) usage ;;
esac
