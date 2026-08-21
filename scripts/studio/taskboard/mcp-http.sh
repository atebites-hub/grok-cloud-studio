#!/usr/bin/env bash
# Start/stop/status the taskboard stdio MCP HTTP gateway on 127.0.0.1:3011.
# Child: taskboard --db $DB mcp. Never prints secrets. Agent Kanban stays gone.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"
gcs_source_studio_env

HOST="${GCS_TASKBOARD_MCP_HOST:-127.0.0.1}"
PORT="${GCS_TASKBOARD_MCP_PORT:-3011}"
STATE="$(gcs_studio_state_dir)"
DB="$(gcs_taskboard_db)"
RUN_DIR="$STATE/taskboard"
PID_FILE="$RUN_DIR/mcp-http.pid"
LOG_FILE="$RUN_DIR/mcp-http.log"
GW="$SCRIPT_DIR/mcp_http_gateway.py"

usage() {
  cat <<'EOF'
Usage: mcp-http.sh [start|stop|status]

HTTP MCP: http://127.0.0.1:3011/mcp
Child: taskboard --db $DB mcp
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
      echo "TASKBOARD_MCP_HTTP_ALREADY pid=$pid url=http://${HOST}:${PORT}/mcp db=$DB"
      exit 0
    fi
    rm -f "$PID_FILE"
    if ! bin="$(gcs_taskboard_bin)"; then
      echo "TASKBOARD_MCP_HTTP_FAIL missing taskboard binary (run install-taskboard.sh; set TASKBOARD_BIN)" >&2
      exit 1
    fi
    nohup python3 "$GW" --host "$HOST" --port "$PORT" --db "$DB" --bin "$bin" >>"$LOG_FILE" 2>&1 &
    echo $! >"$PID_FILE"
    pid="$(gcs_read_pid "$PID_FILE")"
    sleep 0.2
    if ! gcs_pid_alive "$pid"; then
      echo "TASKBOARD_MCP_HTTP_FAIL did not stay up; see $LOG_FILE" >&2
      exit 1
    fi
    echo "TASKBOARD_MCP_HTTP_START pid=$pid url=http://${HOST}:${PORT}/mcp db=$DB log=$LOG_FILE"
    ;;
  stop)
    gcs_stop_pid_file "$PID_FILE" "TASKBOARD_MCP_HTTP"
    ;;
  status)
    pid="$(gcs_read_pid "$PID_FILE")"
    if gcs_pid_alive "$pid"; then
      echo "TASKBOARD_MCP_HTTP_STATUS up pid=$pid url=http://${HOST}:${PORT}/mcp db=$DB"
      exit 0
    fi
    echo "TASKBOARD_MCP_HTTP_STATUS down pid=${pid:-none} db=$DB"
    exit 1
    ;;
esac
