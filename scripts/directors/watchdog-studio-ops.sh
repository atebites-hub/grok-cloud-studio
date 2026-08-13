#!/usr/bin/env bash
# Watchdog: keep A2A bus up, seat ACP daemons up, and studio-ops alive.
# Loop every 10 minutes. Logs to /workspace/cli-logs/org/studio-ops/watchdog.log
set -euo pipefail

export PATH="/home/box/.grok/bin:${PATH:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${GCS_ROOT:-$SCRIPT_DIR/../..}" && pwd)"
STATE_DIR="${GCS_A2A_STATE:-$ROOT/.a2a-state}"
LOG_DIR="/workspace/cli-logs/org/studio-ops"
LOG="$LOG_DIR/watchdog.log"
SEAT="studio-ops"
LOCK="$STATE_DIR/$SEAT/dispatch.lock"
PIDFILE="$LOG_DIR/watchdog.pid"
LAUNCHER="$ROOT/scripts/directors/launch-director.sh"
BUS="$ROOT/scripts/a2a/start-studio-bus.sh"

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
  # Persistent ACP daemon preferred
  if bash "$ROOT/scripts/directors/status-seat-daemon.sh" studio-ops >/dev/null 2>&1; then
    return 0
  fi
  if [[ -f "$LOCK" ]]; then
    local lp
    lp="$(tr -d '[:space:]' <"$LOCK" || true)"
    if pid_alive "$lp"; then
      return 0
    fi
  fi
  if pgrep -f "launch-director\.sh[[:space:]]+studio-ops" >/dev/null 2>&1; then
    return 0
  fi
  if pgrep -af "grok " 2>/dev/null | rg -q "Studio Ops|Donald-double|studio-ops orchestr|studio_ops_director"; then
    return 0
  fi
  return 1
}

WAKE_PROMPT='WATCHDOG_WAKE: Donald Bot may be usage-capped. You are live orchestrator. Run full studio pulse: bus health, open PRs, wake idle Directors, QA mergeables, Extra High rebases for conflicts, continue full studio pulse. RESULT line.'

log "WATCHDOG_START pid=$$ root=$ROOT"

reap_launches() {
  # Reap finished background studio-ops launches so they do not accumulate as zombies.
  if [[ -f "$LOG_DIR/launch.pid" ]]; then
    local lp
    lp="$(tr -d '[:space:]' <"$LOG_DIR/launch.pid" || true)"
    if [[ -n "$lp" ]] && ! pid_alive "$lp"; then
      wait "$lp" 2>/dev/null || true
      rm -f "$LOG_DIR/launch.pid"
      log "REAPED launch_pid=$lp"
    fi
  fi
  # Sweep any other finished children of this watchdog.
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

  # Ensure configured ACP seat daemons (bus start also does this; belt+suspenders)
  if [[ -f "$ROOT/scripts/directors/start-seat-daemon.sh" ]]; then
    while IFS= read -r _seat; do
      [[ -z "$_seat" ]] && continue
      if ! bash "$ROOT/scripts/directors/status-seat-daemon.sh" "$_seat" >/dev/null 2>&1; then
        if bash "$ROOT/scripts/directors/start-seat-daemon.sh" "$_seat" >>"$LOG" 2>&1; then
          log "DAEMON_START seat=$_seat"
        else
          log "DAEMON_START_FAIL seat=$_seat"
        fi
      fi
    done < <(IFS=','; for s in ${GCS_ACP_SEATS:-art,studio-ops}; do echo "$s"; done)
  fi

  if seat_alive; then
    log "SEAT_ALIVE studio-ops"
  else
    log "SEAT_DOWN ensuring studio-ops ACP daemon + wake"
    bash "$ROOT/scripts/directors/start-seat-daemon.sh" studio-ops >>"$LOG" 2>&1 || true
    (
      export PATH="/home/box/.grok/bin:${PATH:-}"
      export GCS_ROOT="$ROOT"
      cd "$ROOT"
      if bash "$ROOT/scripts/directors/status-seat-daemon.sh" studio-ops >/dev/null 2>&1; then
        python3 "$ROOT/scripts/directors/acp_inject.py" studio-ops "$WAKE_PROMPT" >>"$LOG_DIR/launch.log" 2>&1
      else
        bash "$LAUNCHER" studio-ops "$WAKE_PROMPT" >>"$LOG_DIR/launch.log" 2>&1
      fi
    ) &
    echo $! >"$LOG_DIR/launch.pid"
    log "SEAT_LAUNCHED launch_pid=$(cat "$LOG_DIR/launch.pid")"
  fi

  sleep 600
done
