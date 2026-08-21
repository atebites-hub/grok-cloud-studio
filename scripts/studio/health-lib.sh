#!/usr/bin/env bash
# Shared live-service probes for health_check.sh / recover.sh.
# Never print secrets. Agent Kanban stays gone.
# shellcheck disable=SC2034

HEALTH_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=taskboard/common.sh
source "$HEALTH_LIB_DIR/taskboard/common.sh"

gcs_http_ok() {
  local url="${1:-}"
  [[ -n "$url" ]] || return 1
  python3 - "$url" <<'PY'
import sys
import urllib.error
import urllib.request

url = sys.argv[1]
try:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=2) as resp:
        status = int(getattr(resp, "status", 200) or 200)
    raise SystemExit(0 if 200 <= status < 300 else 1)
except Exception:
    raise SystemExit(1)
PY
}

gcs_health_hub_url() {
  local host="${GCS_A2A_HOST:-127.0.0.1}"
  local port="${GCS_A2A_PORT:-8732}"
  printf 'http://%s:%s/health\n' "$host" "$port"
}

gcs_health_taskboard_url() {
  local host="${GCS_TASKBOARD_UI_HOST:-127.0.0.1}"
  local port="${GCS_TASKBOARD_UI_PORT:-3010}"
  printf 'http://%s:%s/\n' "$host" "$port"
}

gcs_health_mcp_http_url() {
  local host="${GCS_TASKBOARD_MCP_HOST:-127.0.0.1}"
  local port="${GCS_TASKBOARD_MCP_PORT:-3011}"
  printf 'http://%s:%s/health\n' "$host" "$port"
}

gcs_health_hub_ok() {
  gcs_http_ok "$(gcs_health_hub_url)"
}

gcs_health_taskboard_ok() {
  local host="${GCS_TASKBOARD_UI_HOST:-127.0.0.1}"
  local port="${GCS_TASKBOARD_UI_PORT:-3010}"
  if gcs_http_ok "$(gcs_health_taskboard_url)"; then
    return 0
  fi
  gcs_port_listening "$host" "$port"
}

gcs_health_mcp_http_ok() {
  local host="${GCS_TASKBOARD_MCP_HOST:-127.0.0.1}"
  local port="${GCS_TASKBOARD_MCP_PORT:-3011}"
  if gcs_http_ok "$(gcs_health_mcp_http_url)"; then
    return 0
  fi
  gcs_port_listening "$host" "$port"
}

gcs_health_mind_seats() {
  python3 "$GCS_KIT_ROOT/scripts/a2a/lib.py" mind-seats 2>/dev/null || true
}

gcs_health_mind_ok() {
  local seat="${1:-}" pid pidfile
  [[ -n "$seat" ]] || return 1
  pidfile="$(gcs_studio_state_dir)/$seat/mind/pid"
  pid="$(gcs_read_pid "$pidfile")"
  gcs_pid_alive "$pid"
}

gcs_health_tailscale_ok() {
  command -v tailscale >/dev/null 2>&1
}
