#!/usr/bin/env bash
# Host maintainer kit for tcarac/taskboard: start / health / docs.
# Distinct from fleet-shepherd.py (GCS #112) and seat stdio MCP (GCS #100).
# Never Bot CloudAgent. Never reconnect Agent Kanban. Never print secrets.
# Palemon Linear is Living Sky (LIV), never Black Swan.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"
gcs_source_studio_env

usage() {
  cat <<'EOF'
Usage: maintainer.sh [start|stop|status|health|docs]

Host maintainer kit for the studio board (tcarac/taskboard v0.6.0):
  start   start UI (:3010) and MCP HTTP (:3011) via start-taskboard.sh + mcp-http.sh
  stop    stop MCP HTTP then UI
  status  UI + MCP HTTP pid status
  health  exec health-taskboard.sh (DB + UI + ticket list OR POST /mcp)
  docs    print operator pointers (no secrets)

GET /health is not a usable board. Agent Kanban stays gone.
See scripts/studio/taskboard/README.md, docs/studio/TASKBOARD.md, docs/studio/WIPE.md.
EOF
}

gcs_maintainer_refuse_ak() {
  if [[ -e "$GCS_KIT_ROOT/scripts/studio/agent-kanban" ]]; then
    echo "AK_REFUSE scripts/studio/agent-kanban must stay gone"
    return 1
  fi
  return 0
}

cmd="${1:-}"
case "$cmd" in
  -h|--help|"")
    usage
    if [[ "$cmd" == "-h" || "$cmd" == "--help" ]]; then
      exit 0
    fi
    exit 2
    ;;
  start|stop|status|health|docs) ;;
  *)
    echo "error: unknown command $cmd" >&2
    usage >&2
    exit 2
    ;;
esac

case "$cmd" in
  start)
    gcs_maintainer_refuse_ak
    bash "$SCRIPT_DIR/start-taskboard.sh" start
    bash "$SCRIPT_DIR/mcp-http.sh" start
    ;;
  stop)
    bash "$SCRIPT_DIR/mcp-http.sh" stop || true
    bash "$SCRIPT_DIR/start-taskboard.sh" stop || true
    ;;
  status)
    ui_rc=0
    mcp_rc=0
    bash "$SCRIPT_DIR/start-taskboard.sh" status || ui_rc=$?
    bash "$SCRIPT_DIR/mcp-http.sh" status || mcp_rc=$?
    if [[ "$ui_rc" -ne 0 || "$mcp_rc" -ne 0 ]]; then
      exit 1
    fi
    ;;
  health)
    gcs_maintainer_refuse_ak
    exec bash "$SCRIPT_DIR/health-taskboard.sh"
    ;;
  docs)
    cat <<'EOF'
TASKBOARD_MAINTAINER_DOCS
  start: scripts/studio/taskboard/start-taskboard.sh start
         scripts/studio/taskboard/mcp-http.sh start
         (or: scripts/studio/taskboard/maintainer.sh start)
  health: scripts/studio/taskboard/health-taskboard.sh
          DB exists + UI :3010 + (ticket list OR POST /mcp). GET /health is not enough.
  docs: docs/studio/TASKBOARD.md
        docs/studio/WIPE.md
        scripts/studio/taskboard/README.md
  pin: vendor/taskboard v0.6.0 (submodule; brew/tarball fallback; do not compile)
  linear: Living Sky (linear.app/livingsky, team Livingsky / LIV). NEVER Black Swan.
  not: fleet-shepherd.py (GCS #112 orphan Extra High probe)
       seat stdio MCP (GCS #100 GROK_HOME catalog)
       Agent Kanban / ak start / scripts/studio/agent-kanban
       Bot CloudAgent / do not vendor Hermes
  dashboard: scripts/studio/dashboard/ is LEGACY
EOF
    ;;
esac
