#!/usr/bin/env bash
# Start a per-seat persistent Grok ACP daemon (grok agent serve).
# Usage: start-seat-daemon.sh <seat>
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=seat-daemon-common.sh
source "$SCRIPT_DIR/seat-daemon-common.sh"

if [[ -f "$STATE_DIR/studio.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$STATE_DIR/studio.env"
  set +a
fi

SEAT_RAW="${1:-}"
if [[ -z "$SEAT_RAW" || "$SEAT_RAW" == "-h" || "$SEAT_RAW" == "--help" ]]; then
  echo "Usage: $(basename "$0") <seat>" >&2
  echo "Seats: ${LAUNCH_SEATS[*]}" >&2
  exit 2
fi

SEAT="$(normalize_seat "$SEAT_RAW")" || exit $?
PORT="$(seat_port "$SEAT")" || { echo "no port for seat=$SEAT" >&2; exit 1; }
SD="$(seat_state_dir "$SEAT")"
PID_FILE="$SD/daemon.pid"
LOG_FILE="$SD/daemon.log"
URL_FILE="$SD/acp.url"
SECRET_FILE="$SD/acp.secret"

# Wrappers go on GROK_HOME/bin and ~/.grok/bin even when serve is already
# healthy. Do not remint a live grok agent serve just to refresh PATH.
export_seat_serve_env "$SEAT"
: "${GCS_TASKBOARD_DB:?export_seat_serve_env must set GCS_TASKBOARD_DB}"
: "${GCS_A2A_STATE:?export_seat_serve_env must set GCS_A2A_STATE}"

if daemon_healthy "$SEAT"; then
  pid="$(read_pid_file "$PID_FILE")"
  echo "SEAT_DAEMON_ALREADY seat=$SEAT pid=$pid port=$PORT url=ws://127.0.0.1:${PORT}/ws"
  exit 0
fi

old_pid="$(read_pid_file "$PID_FILE")"
if pid_alive "$old_pid"; then
  echo "SEAT_DAEMON_STALE_KILL seat=$SEAT pid=$old_pid" >&2
  kill "$old_pid" 2>/dev/null || true
  for _ in 1 2 3 4 5; do
    pid_alive "$old_pid" || break
    sleep 0.2
  done
  pid_alive "$old_pid" && kill -9 "$old_pid" 2>/dev/null || true
fi
rm -f "$PID_FILE"

if port_listening "$PORT"; then
  echo "SEAT_DAEMON_FAIL seat=$SEAT port=$PORT already in use" >&2
  exit 1
fi

if ! command -v grok >/dev/null 2>&1; then
  echo "SEAT_DAEMON_FAIL grok not on PATH" >&2
  exit 1
fi

PROFILE="$(write_agent_profile "$SEAT")"

if [[ -f "$SECRET_FILE" ]]; then
  SECRET="$(tr -d '[:space:]' <"$SECRET_FILE")"
else
  SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
  printf '%s\n' "$SECRET" >"$SECRET_FILE"
  chmod 600 "$SECRET_FILE" || true
fi

URL="ws://127.0.0.1:${PORT}/ws?server-key=${SECRET}"
printf '%s\n' "$URL" >"$URL_FILE"

export_seat_serve_env "$SEAT"
export GCS_TASKBOARD_DB="${GCS_TASKBOARD_DB}"
export GCS_A2A_STATE="${GCS_A2A_STATE}"
export GROK_MEMORY="${GROK_MEMORY:-1}"
export GROK_HOME="${GROK_HOME}"
export PATH="${GROK_HOME}/bin:${HOME}/.grok/bin:${PATH:-}"

{
  echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) START seat=$SEAT port=$PORT ====="
} >>"$LOG_FILE"

# ACP serve cannot attach to grok agent leader (CLI exits on --leader serve).
# Always --no-leader for serve. GROK_USE_LEADER=1 only starts the shared leader
# so one-shot grok -p fallbacks can attach instead of forking more backends.
if [[ "${GROK_USE_LEADER:-0}" == "1" || "${GROK_USE_LEADER:-}" == "true" ]]; then
  bash "$SCRIPT_DIR/start-grok-leader.sh" || true
fi

nohup grok \
  --permission-mode bypassPermissions \
  --always-approve \
  --trust \
  --cwd "$ROOT" \
  agent \
  --always-approve \
  --no-leader \
  --agent-profile "$PROFILE" \
  serve \
  --bind "127.0.0.1:${PORT}" \
  --secret "$SECRET" \
  >>"$LOG_FILE" 2>&1 &
# grok agent serve currently requires --secret on argv (ps leak). Never print it.
echo $! >"$PID_FILE"
pid="$(read_pid_file "$PID_FILE")"

ok=0
for _ in $(seq 1 40); do
  if ! pid_alive "$pid"; then
    echo "SEAT_DAEMON_FAIL seat=$SEAT died during start; see $LOG_FILE" >&2
    exit 1
  fi
  if port_listening "$PORT"; then
    ok=1
    break
  fi
  sleep 0.25
done

if [[ "$ok" != "1" ]]; then
  echo "SEAT_DAEMON_FAIL seat=$SEAT port=$PORT not listening; see $LOG_FILE" >&2
  exit 1
fi

echo "SEAT_DAEMON_START seat=$SEAT pid=$pid port=$PORT url=ws://127.0.0.1:${PORT}/ws profile=$PROFILE log=$LOG_FILE"
{
  echo "kind=grok-build-serve"
  echo "awake=inbox-acp-prompt"
  echo "mode=acp-serve"
} >"$SD/grow.mode"
