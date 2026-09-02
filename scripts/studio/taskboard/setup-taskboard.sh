#!/usr/bin/env bash
# Board-only Palemon wipe/setup path under scripts/studio/taskboard/.
# start: host ticket/tb PATH links + UI :3010 + MCP HTTP :3011
# stop:  UI + MCP HTTP
# wipe:  stop, then tcarac `taskboard --db $DB clear -f` and remove the sqlite file
#        (inboxes / mind pins / studio.env are cleanup.sh, not this script)
# Distinct from the operator health/docs kit and the PIN-upgrade kit.
# Never prints secrets. Never reconnects Agent Kanban. Does not vendor a blob.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"
gcs_source_studio_env

HOST="${GCS_TASKBOARD_UI_HOST:-127.0.0.1}"
PORT="${GCS_TASKBOARD_UI_PORT:-3010}"
MCP_HOST="${GCS_TASKBOARD_MCP_HOST:-127.0.0.1}"
MCP_PORT="${GCS_TASKBOARD_MCP_PORT:-3011}"

usage() {
  cat <<'EOF'
Usage: setup-taskboard.sh [start|stop|status|restart|wipe]

Board-only disaster-recovery path (tcarac/taskboard v0.6.0):
  start    install host ticket/tb PATH links; start UI :3010 + MCP HTTP :3011
  stop     stop MCP HTTP then UI (keeps studio.env and taskboard.db)
  status   UI + MCP HTTP + wrapper paths
  restart  stop then start
  wipe     requires GCS_TASKBOARD_WIPE=1 or CLEANUP_WIPE_STATE=1
           stop, taskboard --db $DB clear -f, rm sqlite file
           does not touch inboxes, mind pins, or studio.env

Leaf processes remain start-taskboard.sh and mcp-http.sh.
Does not pass --daemons (NO --daemons). Does not brew-upgrade. Does not compile.
See docs/studio/WIPE.md and scripts/studio/taskboard/README.md.
EOF
}

gcs_taskboard_ak_refuse() {
  local cand
  for cand in \
    "$GCS_KIT_ROOT/scripts/studio/agent-kanban" \
    "$SCRIPT_DIR/../agent-kanban"
  do
    if [[ -e "$cand" ]]; then
      echo "AK_REFUSE Agent Kanban tree at $cand — do not reconnect ak" >&2
      return 1
    fi
  done
  return 0
}

board_stop() {
  bash "$SCRIPT_DIR/mcp-http.sh" stop || true
  bash "$SCRIPT_DIR/start-taskboard.sh" stop || true
}

board_start() {
  local db bin
  gcs_taskboard_ak_refuse || return 1
  db="$(gcs_taskboard_db)"
  mkdir -p "$(dirname "$db")" "$(gcs_studio_state_dir)/taskboard"
  export GCS_A2A_STATE="$(gcs_studio_state_dir)"

  if [[ "${GCS_TASKBOARD_SKIP_SUBMODULE:-0}" != "1" ]]; then
    gcs_ensure_taskboard_submodule || true
  fi
  if [[ "${GCS_TASKBOARD_SKIP_INSTALL:-0}" != "1" ]]; then
    if ! gcs_taskboard_bin >/dev/null 2>&1; then
      bash "$SCRIPT_DIR/install-taskboard.sh"
    fi
  fi
  gcs_install_host_ticket_links || true

  bash "$SCRIPT_DIR/start-taskboard.sh" start
  bash "$SCRIPT_DIR/mcp-http.sh" start

  if [[ "${GCS_TASKBOARD_SKIP_READY:-0}" != "1" ]]; then
    if ! gcs_wait_listen "$HOST" "$PORT"; then
      echo "TASKBOARD_SETUP_FAIL reason=ui-not-ready url=http://${HOST}:${PORT}" >&2
      return 1
    fi
    if ! gcs_wait_listen "$MCP_HOST" "$MCP_PORT"; then
      echo "TASKBOARD_SETUP_FAIL reason=mcp-not-ready url=http://${MCP_HOST}:${MCP_PORT}/mcp" >&2
      return 1
    fi
  fi

  bin="$(gcs_taskboard_bin 2>/dev/null || true)"
  echo "TASKBOARD_SETUP_OK ui=http://${HOST}:${PORT} mcp=http://${MCP_HOST}:${MCP_PORT}/mcp db=$db ticket=$GCS_KIT_ROOT/bin/ticket tb=$GCS_KIT_ROOT/bin/tb bin=${bin:-none}"
}

board_status() {
  local db rc=0
  db="$(gcs_taskboard_db)"
  bash "$SCRIPT_DIR/start-taskboard.sh" status || rc=1
  bash "$SCRIPT_DIR/mcp-http.sh" status || rc=1
  echo "TASKBOARD_SETUP_STATUS db=$db ticket=$GCS_KIT_ROOT/bin/ticket tb=$GCS_KIT_ROOT/bin/tb"
  return "$rc"
}

board_wipe() {
  local db bin
  if [[ "${GCS_TASKBOARD_WIPE:-0}" != "1" && "${CLEANUP_WIPE_STATE:-0}" != "1" ]]; then
    echo "error: refuse wipe without GCS_TASKBOARD_WIPE=1 or CLEANUP_WIPE_STATE=1 (inboxes are not touched here)" >&2
    usage >&2
    return 2
  fi
  gcs_taskboard_ak_refuse || return 1
  db="$(gcs_taskboard_db)"
  board_stop
  if bin="$(gcs_taskboard_bin)"; then
    "$bin" --db "$db" clear -f || true
  fi
  rm -f "$db"
  echo "TASKBOARD_WIPE_OK db=$db"
}

cmd="${1:-start}"
case "$cmd" in
  -h|--help)
    usage
    exit 0
    ;;
  start|stop|status|restart|wipe) ;;
  *)
    echo "error: unknown command $cmd" >&2
    usage >&2
    exit 2
    ;;
esac

mkdir -p "$(gcs_studio_state_dir)"
export GCS_A2A_STATE="$(gcs_studio_state_dir)"

case "$cmd" in
  start)
    board_start
    ;;
  stop)
    board_stop
    echo "TASKBOARD_SETUP_STOP"
    ;;
  status)
    board_status
    ;;
  restart)
    board_stop
    board_start
    ;;
  wipe)
    board_wipe
    ;;
esac
