#!/usr/bin/env bash
# Watchdog: keep A2A bus up, opted-in seat ACP daemons up, and the ops seat alive.
# Loop every 10 minutes. Logs under .a2a-state/ops/.
set -euo pipefail

export PATH="${HOME}/.grok/bin:/home/box/.grok/bin:${PATH:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${GCS_ROOT:-$SCRIPT_DIR/../..}" && pwd)"
STATE_DIR="${GCS_A2A_STATE:-$ROOT/.a2a-state}"
SEAT="${GCS_WATCHDOG_SEAT:-ops}"
LOG_DIR="$STATE_DIR/$SEAT"
LOG="$LOG_DIR/watchdog.log"
LOCK="$STATE_DIR/$SEAT/dispatch.lock"
PIDFILE="$LOG_DIR/watchdog.pid"
LAUNCHER="$ROOT/scripts/directors/launch-director.sh"
BUS="$ROOT/scripts/a2a/start-studio-bus.sh"
LIB_PY="$ROOT/scripts/a2a/lib.py"

mkdir -p "$LOG_DIR" "$STATE_DIR/$SEAT"

echo $$ >"$PIDFILE"

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >>"$LOG"
}

pid_alive() {
  local pid="${1:-}" state
  [[ -n "$pid" ]] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  state=$(ps -p "$pid" -o state= 2>/dev/null | tr -d "[:space:]")
  [[ "$state" == Z* ]] && return 1
  return 0
}

seat_alive() {
  if bash "$ROOT/scripts/directors/status-seat-daemon.sh" "$SEAT" >/dev/null 2>&1; then
    return 0
  fi
  if [[ -f "$LOCK" ]]; then
    local lp
    lp="$(tr -d '[:space:]' <"$LOCK" || true)"
    if pid_alive "$lp"; then
      return 0
    fi
  fi
  if pgrep -f "launch-director\.sh[[:space:]]+${SEAT}" >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

WAKE_PROMPT='WATCHDOG_WAKE: ops seat is down. Restore bus health, wake idle Directors if assigned, continue Extra High waiters. RESULT line.'

log "WATCHDOG_START pid=$$ root=$ROOT seat=$SEAT"

reap_launches() {
  if [[ -f "$LOG_DIR/launch.pid" ]]; then
    local lp
    lp="$(tr -d '[:space:]' <"$LOG_DIR/launch.pid" || true)"
    if [[ -n "$lp" ]] && ! pid_alive "$lp"; then
      wait "$lp" 2>/dev/null || true
      rm -f "$LOG_DIR/launch.pid"
      log "REAPED launch_pid=$lp"
    fi
  fi
  while wait -n 2>/dev/null; do
    :
  done
}

while true; do
  reap_launches

  if ! bash "$BUS" start >>"$LOG" 2>&1; then
    log "BUS_START_FAIL"
  else
    log "BUS_OK"
  fi

  if [[ -f "$ROOT/scripts/directors/start-seat-daemon.sh" && -f "$STATE_DIR/daemons.enabled" ]]; then
    while IFS= read -r _seat; do
      [[ -z "$_seat" ]] && continue
      if ! bash "$ROOT/scripts/directors/status-seat-daemon.sh" "$_seat" >/dev/null 2>&1; then
        if bash "$ROOT/scripts/directors/start-seat-daemon.sh" "$_seat" >>"$LOG" 2>&1; then
          log "DAEMON_START seat=$_seat"
        else
          log "DAEMON_START_FAIL seat=$_seat"
        fi
      fi
    done < <(python3 "$LIB_PY" launch-seats)
  fi

  if seat_alive; then
    log "SEAT_ALIVE $SEAT"
  else
    log "SEAT_DOWN ensuring $SEAT ACP daemon + wake"
    bash "$ROOT/scripts/directors/start-seat-daemon.sh" "$SEAT" >>"$LOG" 2>&1 || true
    (
      export PATH="${HOME}/.grok/bin:/home/box/.grok/bin:${PATH:-}"
      export GCS_ROOT="$ROOT"
      cd "$ROOT"
      if bash "$ROOT/scripts/directors/status-seat-daemon.sh" "$SEAT" >/dev/null 2>&1; then
        python3 "$ROOT/scripts/directors/acp_inject.py" "$SEAT" "$WAKE_PROMPT" >>"$LOG_DIR/launch.log" 2>&1
      else
        bash "$LAUNCHER" "$SEAT" "$WAKE_PROMPT" >>"$LOG_DIR/launch.log" 2>&1
      fi
    ) &
    echo $! >"$LOG_DIR/launch.pid"
    log "SEAT_LAUNCHED launch_pid=$(cat "$LOG_DIR/launch.pid")"
  fi

  sleep 600
done
