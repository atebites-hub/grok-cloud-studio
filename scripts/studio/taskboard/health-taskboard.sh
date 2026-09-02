#!/usr/bin/env bash
# Host-side tcarac/taskboard maintainer health (board-only).
# Distinct from ./health_check.sh (studio DR: hub + ports + mind pids).
# Distinct from fleet-shepherd.py (GCS #112 orphan Extra High safety net).
# Distinct from seat stdio MCP (GCS #100). Never Bot CloudAgent.
# GET /health on :3011 is not a usable board. Never reconnect Agent Kanban.
# Never print secrets. Palemon Linear is Living Sky (LIV), never Black Swan.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../health-lib.sh
source "$SCRIPT_DIR/../health-lib.sh"
gcs_source_studio_env

usage() {
  cat <<'EOF'
Usage: health-taskboard.sh [--help]

Board-only maintainer probe (not ./health_check.sh, not fleet-shepherd).
Healthy means:
  1. scripts/studio/agent-kanban is absent (AK_REFUSE otherwise)
  2. SQLite DB exists ($GCS_TASKBOARD_DB or $GCS_A2A_STATE/taskboard/taskboard.db)
  3. UI is up on 127.0.0.1:3010
  4. taskboard --db $DB ticket list succeeds OR POST /mcp returns 2xx

GET /health on the MCP HTTP port is not enough.
Prints TASKBOARD_HEALTH_OK (exit 0) or TASKBOARD_HEALTH_FAIL (exit 1).
See scripts/studio/taskboard/README.md and maintainer.sh docs.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi
if [[ $# -gt 0 ]]; then
  echo "error: unknown argument $1" >&2
  usage >&2
  exit 2
fi

if [[ -e "$GCS_KIT_ROOT/scripts/studio/agent-kanban" ]]; then
  echo "AK_REFUSE scripts/studio/agent-kanban must stay gone"
  echo "TASKBOARD_HEALTH_FAIL reason=agent-kanban"
  exit 1
fi

DB="$(gcs_taskboard_db)"
if [[ ! -f "$DB" ]]; then
  echo "TASKBOARD_HEALTH db=$DB ui=down cli=skip mcp=fail"
  echo "TASKBOARD_HEALTH_FAIL reason=missing-db"
  exit 1
fi

ui="down"
if gcs_health_taskboard_ok; then
  ui="up"
fi

cli="skip"
if bin="$(gcs_taskboard_bin 2>/dev/null || true)"; then
  if [[ -n "$bin" && -x "$bin" ]]; then
    if "$bin" --db "$DB" ticket list >/dev/null 2>&1; then
      cli="ok"
    else
      cli="fail"
    fi
  fi
fi

gcs_taskboard_mcp_post_ok() {
  local host="${GCS_TASKBOARD_MCP_HOST:-127.0.0.1}"
  local port="${GCS_TASKBOARD_MCP_PORT:-3011}"
  local url="http://${host}:${port}/mcp"
  python3 - "$url" <<'PY'
import json
import sys
import urllib.error
import urllib.request

url = sys.argv[1]
body = json.dumps(
    {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
).encode("utf-8")
try:
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=2) as resp:
        status = int(getattr(resp, "status", 200) or 200)
    raise SystemExit(0 if 200 <= status < 300 else 1)
except Exception:
    raise SystemExit(1)
PY
}

mcp="fail"
if gcs_taskboard_mcp_post_ok; then
  mcp="ok"
fi

echo "TASKBOARD_HEALTH db=$DB ui=$ui cli=$cli mcp=$mcp"

if [[ "$ui" != "up" ]]; then
  echo "TASKBOARD_HEALTH_FAIL reason=ui-down"
  exit 1
fi
if [[ "$cli" != "ok" && "$mcp" != "ok" ]]; then
  echo "TASKBOARD_HEALTH_FAIL reason=not-usable"
  exit 1
fi
echo "TASKBOARD_HEALTH_OK"
exit 0
