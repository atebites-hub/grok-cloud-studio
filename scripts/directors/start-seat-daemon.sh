#!/usr/bin/env bash
# Start a per-seat persistent Grok ACP daemon (grok agent serve).
# Usage: start-seat-daemon.sh <seat>
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=seat-daemon-common.sh
source "$SCRIPT_DIR/seat-daemon-common.sh"

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

if daemon_healthy "$SEAT"; then
  pid="$(read_pid_file "$PID_FILE")"
  echo "SEAT_DAEMON_ALREADY seat=$SEAT pid=$pid port=$PORT url=$(cat "$URL_FILE")"
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

export GCS_ROOT="$ROOT"
export GCS_A2A_STATE="$STATE_DIR"
export GCS_DIRECTOR_SEAT="$SEAT"
export PATH="${HOME}/.grok/bin:/home/box/.grok/bin:${PATH:-}"

{
  echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) START seat=$SEAT port=$PORT ====="
} >>"$LOG_FILE"

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

echo "SEAT_DAEMON_START seat=$SEAT pid=$pid port=$PORT url=$URL profile=$PROFILE log=$LOG_FILE"
