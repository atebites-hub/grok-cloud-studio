#!/usr/bin/env bash
# Restart ONLY down Palemon studio services via official scripts.
# Do not remint sessions. Do not wipe state. Do not launch Cursor Cloud.
# Do not pass --daemons. On success prints recover-ok then re-runs health_check.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
export GCS_ROOT="${GCS_ROOT:-$ROOT}"

# shellcheck source=scripts/studio/health-lib.sh
source "$ROOT/scripts/studio/health-lib.sh"
gcs_source_studio_env

usage() {
  cat <<'EOF'
Usage: recover.sh [--help]

Restart only what health_check would mark down:
  hub or mind pid down -> scripts/a2a/start-studio-bus.sh start   (NO --daemons;
                         bot-bridge stays off unless GCS_BOT_BRIDGE=1.
                         leftover live bot-bridge.pid is evicted; ALREADY
                         is not a default start)
  taskboard :3010 down -> scripts/studio/taskboard/start-taskboard.sh start
  mcp-http :3011 down  -> scripts/studio/taskboard/mcp-http.sh start

Does not remint sessions, wipe studio.env / inboxes / pins, reconnect
Agent Kanban, or launch Cursor Cloud.

Fails closed (no restarts) if Higgsfield/Sentry art MCP would leak keys
(argv / literal env). Never prints secret values.

On success prints a recover-ok line, then runs ./health_check.sh (same exit 0/1/2).

GCS_RECOVER_DRY_RUN=1 prints the start commands without executing them.
See docs/studio/WIPE.md (DR loop with health_check.sh).
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
mkdir -p "$STATE"

# Fail-closed before any restart if art Higgsfield/Sentry MCP would leak keys
# (argv / literal env). Never print values. Distinct from leftover-green CI.
_sentry_args=(--root "$ROOT" --state "$STATE")
if [[ -n "${GROK_HOME:-}" ]]; then
  _sentry_args+=(--grok-home "$GROK_HOME")
fi
if ! python3 "$ROOT/scripts/studio/higgsfield_sentry.py" "${_sentry_args[@]}"; then
  echo "RECOVER_ERR higgsfield_sentry failed (art MCP would leak keys; values not printed)" >&2
  exit 1
fi

need_bus=0
need_tb=0
need_mcp=0

if ! gcs_health_hub_ok; then
  need_bus=1
fi
while read -r seat; do
  [[ -z "$seat" ]] && continue
  if ! gcs_health_mind_ok "$seat"; then
    need_bus=1
  fi
done < <(gcs_health_mind_seats)

if ! gcs_health_taskboard_ok; then
  need_tb=1
fi
if ! gcs_health_mcp_http_ok; then
  need_mcp=1
fi

recover_start() {
  local label="$1"
  shift
  if [[ "${GCS_RECOVER_DRY_RUN:-0}" == "1" ]]; then
    echo "RECOVER_DRY cmd=$*"
    return 0
  fi
  echo "RECOVER_START $label"
  bash "$@" || echo "RECOVER_WARN $label failed" >&2
}

# PAL-25 remaining: leftover live bot-bridge.pid is not a default start.
# STUDIO_BUS_BOT_BRIDGE_ALREADY still requires kill-after-RECOVER. Evict
# unless GCS_BOT_BRIDGE=1, even when the bus itself is already up.
if [[ "${GCS_BOT_BRIDGE:-0}" != "1" ]]; then
  leftover_bridge="$(gcs_read_pid "$STATE/bot-bridge.pid")"
  if gcs_pid_alive "$leftover_bridge"; then
    if [[ "${GCS_RECOVER_DRY_RUN:-0}" == "1" ]]; then
      echo "RECOVER_DRY cmd=evict leftover bot-bridge pid=$leftover_bridge"
    else
      echo "RECOVER_BOT_BRIDGE_EVICT reason=standby pid=$leftover_bridge"
      gcs_stop_pid_file "$STATE/bot-bridge.pid" "RECOVER_BOT_BRIDGE"
    fi
  fi
fi

if [[ "$need_bus" -eq 1 ]]; then
  # Crash-safe: never pass --daemons. Do not remint. Do not wipe state.
  # Do not enable bot-bridge (GCS_BOT_BRIDGE default off). Bot seats stay
  # standby unless studio.env already opted the bridge in.
  recover_start bus "$ROOT/scripts/a2a/start-studio-bus.sh" start
fi
if [[ "$need_tb" -eq 1 ]]; then
  recover_start taskboard "$ROOT/scripts/studio/taskboard/start-taskboard.sh" start
fi
if [[ "$need_mcp" -eq 1 ]]; then
  recover_start mcp-http "$ROOT/scripts/studio/taskboard/mcp-http.sh" start
fi

echo "RECOVER_OK"
bash "$ROOT/health_check.sh"
