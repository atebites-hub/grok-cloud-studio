#!/usr/bin/env bash
# Tailscale Serve: / → :3010 (UI) and /mcp → :3011 (MCP HTTP). Funnel off.
# Host default: palemon-studio.panther-arctic.ts.net (MagicDNS; already joined).
# Skip if PALEMON_TAILSCALE_SERVE=0 or tailscale is missing / not joined.
# Never write Tailscale auth key values. Never print secrets.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"
gcs_source_studio_env

HOST_DEFAULT="${GCS_TAILSCALE_HOST:-palemon-studio.panther-arctic.ts.net}"
UI_PORT="${GCS_TASKBOARD_UI_PORT:-3010}"
MCP_PORT="${GCS_TASKBOARD_MCP_PORT:-3011}"

usage() {
  cat <<EOF
Usage: start-tailscale-serve.sh [start|stop|status]

Serve (tailnet only, Funnel off):
  /    → http://127.0.0.1:${UI_PORT}
  /mcp → http://127.0.0.1:${MCP_PORT}

Expected MagicDNS host: ${HOST_DEFAULT}
Skip: PALEMON_TAILSCALE_SERVE=0, missing tailscale, or not joined.
Requires the node to already be on the tailnet. This script never writes
or prints Tailscale auth keys.
EOF
}

skip() {
  echo "TASKBOARD_TAILSCALE_SKIP $*"
  exit 0
}

want_serve() {
  case "${PALEMON_TAILSCALE_SERVE:-}" in
    0|false|off|no) return 1 ;;
  esac
  return 0
}

funnel_off() {
  # Funnel must stay off. Best-effort; ignore failures.
  if tailscale funnel status >/dev/null 2>&1; then
    tailscale funnel reset >/dev/null 2>&1 || true
  fi
  tailscale funnel --https=443 off >/dev/null 2>&1 || true
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

if ! want_serve; then
  skip "PALEMON_TAILSCALE_SERVE=0"
fi
if ! command -v tailscale >/dev/null 2>&1; then
  skip "tailscale missing"
fi

case "$cmd" in
  start)
    if ! tailscale status >/dev/null 2>&1; then
      skip "tailscale not joined (join the tailnet first; do not pass auth keys here)"
    fi
    funnel_off
    tailscale serve --bg --https=443 --set-path=/ "http://127.0.0.1:${UI_PORT}"
    tailscale serve --bg --https=443 --set-path=/mcp "http://127.0.0.1:${MCP_PORT}"
    echo "TASKBOARD_TAILSCALE_SERVE_OK host=${HOST_DEFAULT} ui=${UI_PORT} mcp=${MCP_PORT} funnel=off"
    ;;
  stop)
    tailscale serve --https=443 --set-path=/ off >/dev/null 2>&1 || true
    tailscale serve --https=443 --set-path=/mcp off >/dev/null 2>&1 || true
    funnel_off
    echo "TASKBOARD_TAILSCALE_SERVE_STOP"
    ;;
  status)
    echo "TASKBOARD_TAILSCALE_HOST ${HOST_DEFAULT}"
    tailscale serve status || true
    ;;
esac
