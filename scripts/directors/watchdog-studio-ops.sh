#!/usr/bin/env bash
# Watchdog: keep A2A bus up, opted-in seat ACP daemons up, GROW wake loops up,
# and the host ticker alive. Loop every 10 minutes. Each beat MUST append one
# Manning apply-log line (docs/studio/HIVE.md, LIV-71). Logs under .a2a-state/<seat>/.
# Clock is host-ticker.py / host-clock-ticker.sh (inbox ACP_PING STATUS/CONTINUE).
# Not ACP inject. Tools allowed. Do not emit a LAUNCH kind.
# If serve dies: restart serve (start-seat-daemon.sh). Never grok --resume.
set -euo pipefail

export PATH="${HOME}/.grok/bin:${PATH:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${GCS_ROOT:-$SCRIPT_DIR/../..}" && pwd)"
STATE_DIR="${GCS_A2A_STATE:-$ROOT/.a2a-state}"
SEAT="${GCS_WATCHDOG_SEAT:-ops}"
LOG_DIR="$STATE_DIR/$SEAT"
LOG="$LOG_DIR/watchdog.log"
PIDFILE="$LOG_DIR/watchdog.pid"
BUS="$ROOT/scripts/a2a/start-studio-bus.sh"
WAKE_LOOP="$ROOT/scripts/directors/seat-wake-loop.sh"
START_DAEMON="$ROOT/scripts/directors/start-seat-daemon.sh"
TICKER_PY="$ROOT/scripts/a2a/host-ticker.py"
LIB_PY="$ROOT/scripts/a2a/lib.py"
APPLY_LOG_PY="$ROOT/scripts/studio/apply_log.py"

mkdir -p "$LOG_DIR" "$STATE_DIR/$SEAT"

if [[ -f "$STATE_DIR/studio.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$STATE_DIR/studio.env"
  set +a
fi

BEAT_SEC="${GCS_TICKER_SEC:-600}"

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

read_pid() {
  local f="$1"
  if [[ -f "$f" ]]; then
    tr -d '[:space:]' < "$f" || true
  fi
}

seat_alive() {
  local wp
  wp="$(read_pid "$STATE_DIR/$SEAT/wake.pid")"
  pid_alive "$wp"
}

serve_alive() {
  local dp
  dp="$(read_pid "$STATE_DIR/$SEAT/daemon.pid")"
  pid_alive "$dp"
}

ticker_alive() {
  local tp
  tp="$(read_pid "$STATE_DIR/host-ticker.pid")"
  pid_alive "$tp"
}

log "WATCHDOG_START pid=$$ root=$ROOT seat=$SEAT grow=serve+wake-loop+ticker beat=${BEAT_SEC}s"

while true; do
  bus_status=fail
  serve_status=down
  wake_status=down
  ticker_status=down

  if ! bash "$BUS" start >>"$LOG" 2>&1; then
    log "BUS_START_FAIL"
  else
    bus_status=ok
    log "BUS_OK"
  fi

  if [[ -f "$START_DAEMON" && -f "$STATE_DIR/daemons.enabled" ]]; then
    while IFS= read -r _seat; do
      [[ -z "$_seat" ]] && continue
      if ! bash "$ROOT/scripts/directors/status-seat-daemon.sh" "$_seat" >/dev/null 2>&1; then
        if bash "$START_DAEMON" "$_seat" >>"$LOG" 2>&1; then
          log "DAEMON_START seat=$_seat"
        else
          log "DAEMON_START_FAIL seat=$_seat"
        fi
      fi
    done < <(
      known="$(python3 "$LIB_PY" launch-seats 2>/dev/null || true)"
      IFS=','
      for s in ${GCS_ACP_SEATS:-floor,studio-ops}; do
        s="$(echo "$s" | tr -d '[:space:]')"
        [[ -n "$s" ]] || continue
        if printf '%s\n' "$known" | grep -qx "$s"; then
          echo "$s"
        elif [[ "$s" == "studio-ops" ]] && printf '%s\n' "$known" | grep -qx "ops"; then
          echo "ops"
        fi
      done
    )
  fi

  if serve_alive; then
    serve_status=ok
    log "SERVE_ALIVE $SEAT daemon.pid"
  else
    log "SERVE_DOWN ensuring $SEAT grok agent serve"
    if [[ -f "$START_DAEMON" ]]; then
      if bash "$START_DAEMON" "$SEAT" >>"$LOG" 2>&1; then
        serve_status=ok
        log "SERVE_START seat=$SEAT pid=$(read_pid "$STATE_DIR/$SEAT/daemon.pid")"
      else
        log "SERVE_START_FAIL seat=$SEAT"
      fi
    fi
  fi

  if seat_alive; then
    wake_status=ok
    log "SEAT_ALIVE $SEAT wake.pid"
  else
    log "SEAT_DOWN ensuring $SEAT seat-wake-loop"
    mkdir -p "$STATE_DIR/$SEAT"
    if [[ -f "$WAKE_LOOP" ]]; then
      nohup bash "$WAKE_LOOP" "$SEAT" >>"$STATE_DIR/$SEAT/wake.log" 2>&1 &
      echo $! >"$STATE_DIR/$SEAT/wake.pid"
      wake_status=ok
      log "WAKE_START seat=$SEAT pid=$(read_pid "$STATE_DIR/$SEAT/wake.pid")"
    fi
  fi

  if ticker_alive; then
    ticker_status=ok
    log "TICKER_ALIVE"
  else
    log "TICKER_DOWN restarting host-ticker"
    if [[ -f "$TICKER_PY" ]]; then
      nohup python3 "$TICKER_PY" >>"$STATE_DIR/host-ticker.log" 2>&1 &
      echo $! >"$STATE_DIR/host-ticker.pid"
      ticker_status=ok
      log "TICKER_START pid=$(read_pid "$STATE_DIR/host-ticker.pid")"
    fi
  fi

  change="IaC: health_check.sh apply_log.py bus=${bus_status} serve=${serve_status} wake=${wake_status} ticker=${ticker_status}; Palemon: no game code"
  if [[ -f "$APPLY_LOG_PY" ]] && python3 "$APPLY_LOG_PY" beat --change "$change" --seat "$SEAT" >>"$LOG" 2>&1; then
    log "APPLY_LOG_OK"
  else
    log "APPLY_LOG_FAIL"
  fi

  if [[ "${GCS_WATCHDOG_ONCE:-0}" == "1" ]]; then
    break
  fi
  sleep "$BEAT_SEC"
done
