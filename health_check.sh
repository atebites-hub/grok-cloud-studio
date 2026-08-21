#!/usr/bin/env bash
# Probe LIVE Palemon studio services. Never prints secrets.
# Exit 0 HEALTH_OK, 1 HEALTH_DEGRADED, 2 HEALTH_DOWN.
# Tailscale missing is WARN, not FAIL. Do not remint, wipe, or launch Cursor Cloud.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
export GCS_ROOT="${GCS_ROOT:-$ROOT}"

# shellcheck source=scripts/studio/health-lib.sh
source "$ROOT/scripts/studio/health-lib.sh"
gcs_source_studio_env

usage() {
  cat <<'EOF'
Usage: health_check.sh [--help]

Probe live studio services (no secrets):
  hub GET /health
  taskboard UI :3010
  mcp-http :3011 GET /health
  each GCS_MIND_SEATS mind pid
  tailscale binary (WARN if missing, never FAIL)

Prints HEALTH_OK / HEALTH_DEGRADED / HEALTH_DOWN and exits 0 / 1 / 2.
Hub down => HEALTH_DOWN. Hub up but board/mcp/mind down => HEALTH_DEGRADED.
See docs/studio/WIPE.md (DR loop with recover.sh).
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

STATE="$(gcs_studio_state_dir)"
export GCS_A2A_STATE="$STATE"

hub_down=0
degraded=0

hub_url="$(gcs_health_hub_url)"
if gcs_health_hub_ok; then
  echo "HUB up url=$hub_url"
else
  echo "HUB down url=$hub_url"
  hub_down=1
fi

tb_url="$(gcs_health_taskboard_url)"
if gcs_health_taskboard_ok; then
  echo "TASKBOARD up url=$tb_url"
else
  echo "TASKBOARD down url=$tb_url"
  degraded=1
fi

mcp_url="$(gcs_health_mcp_http_url)"
if gcs_health_mcp_http_ok; then
  echo "MCP_HTTP up url=$mcp_url"
else
  echo "MCP_HTTP down url=$mcp_url"
  degraded=1
fi

mind_any=0
while read -r seat; do
  [[ -z "$seat" ]] && continue
  mind_any=1
  pidfile="$STATE/$seat/mind/pid"
  pid="$(gcs_read_pid "$pidfile")"
  if gcs_health_mind_ok "$seat"; then
    echo "MIND seat=$seat up pid=$pid"
  else
    echo "MIND seat=$seat down pid=${pid:-none}"
    degraded=1
  fi
done < <(gcs_health_mind_seats)
if [[ "$mind_any" -eq 0 ]]; then
  echo "MIND seats=none"
fi

if gcs_health_tailscale_ok; then
  echo "TAILSCALE ok"
else
  echo "WARN tailscale missing"
fi

if [[ "$hub_down" -eq 1 ]]; then
  echo "HEALTH_DOWN"
  exit 2
fi
if [[ "$degraded" -eq 1 ]]; then
  echo "HEALTH_DEGRADED"
  exit 1
fi
echo "HEALTH_OK"
exit 0
