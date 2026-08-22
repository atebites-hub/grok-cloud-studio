#!/usr/bin/env bash
# Start/stop/status the studio taskboard UI on 127.0.0.1:3010.
# DB: $GCS_TASKBOARD_DB or $GCS_A2A_STATE/taskboard/taskboard.db
# (PALEMON_A2A_STATE is accepted as an alias for GCS_A2A_STATE).
# Does not vendor the binary. Agent Kanban stays gone.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"
gcs_source_studio_env

HOST="${GCS_TASKBOARD_UI_HOST:-127.0.0.1}"
PORT="${GCS_TASKBOARD_UI_PORT:-3010}"
STATE="$(gcs_studio_state_dir)"
DB="$(gcs_taskboard_db)"
RUN_DIR="$STATE/taskboard"
PID_FILE="$RUN_DIR/ui.pid"
LOG_FILE="$RUN_DIR/ui.log"

usage() {
  cat <<'EOF'
Usage: start-taskboard.sh [start|stop|status]

UI: http://127.0.0.1:3010
DB: $GCS_A2A_STATE/taskboard/taskboard.db (or PALEMON_A2A_STATE)
See scripts/studio/taskboard/README.md and docs/studio/WIPE.md.
EOF
}

cmd="${1:-start}"
case "$cmd" in
  -h|--help)
    usage
    exit 0
    ;;
  start|stop|status) ;;
  *)
    echo "error: unknown command $cmd" >&2
    usage >&2
    exit 2
    ;;
esac

mkdir -p "$RUN_DIR" "$(dirname "$DB")"

case "$cmd" in
  start)
    pid="$(gcs_read_pid "$PID_FILE")"
    if gcs_pid_alive "$pid"; then
      echo "TASKBOARD_UI_ALREADY pid=$pid url=http://${HOST}:${PORT} db=$DB"
      exit 0
    fi
    rm -f "$PID_FILE"
    if ! bin="$(gcs_taskboard_bin)"; then
      echo "TASKBOARD_UI_FAIL missing taskboard binary (run install-taskboard.sh; set TASKBOARD_BIN)" >&2
      exit 1
    fi
    nohup "$bin" --db "$DB" start --port "$PORT" --foreground >>"$LOG_FILE" 2>&1 &
    echo $! >"$PID_FILE"
    pid="$(gcs_read_pid "$PID_FILE")"
    sleep 0.2
    if ! gcs_pid_alive "$pid"; then
      echo "TASKBOARD_UI_FAIL did not stay up; see $LOG_FILE" >&2
      exit 1
    fi
    echo "TASKBOARD_UI_START pid=$pid url=http://${HOST}:${PORT} db=$DB log=$LOG_FILE"
    ;;
  stop)
    gcs_stop_pid_file "$PID_FILE" "TASKBOARD_UI"
    ;;
  status)
    pid="$(gcs_read_pid "$PID_FILE")"
    if gcs_pid_alive "$pid"; then
      echo "TASKBOARD_UI_STATUS up pid=$pid url=http://${HOST}:${PORT} db=$DB"
      exit 0
    fi
    echo "TASKBOARD_UI_STATUS down pid=${pid:-none} db=$DB"
    exit 1
    ;;
esac
