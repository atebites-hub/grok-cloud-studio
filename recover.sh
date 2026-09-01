#!/usr/bin/env bash
# Restart ONLY down Palemon studio services via official scripts.
# Do not remint sessions. Do not wipe state. Do not launch Cursor Cloud.
# Do not pass --daemons. Prints RECOVER_OK then re-runs health_check.sh.
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
                         do not restart a live bot-bridge pid; Bot seats stay
                         standby unless studio.env already opted the bridge in)
  taskboard :3010 down -> scripts/studio/taskboard/start-taskboard.sh start
  mcp-http :3011 down  -> scripts/studio/taskboard/mcp-http.sh start

Does not remint sessions, wipe studio.env / inboxes / pins, reconnect
Agent Kanban, or launch Cursor Cloud.

Prints RECOVER_OK, then runs ./health_check.sh (same exit 0/1/2).

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

if [[ "$need_bus" -eq 1 ]]; then
  # Crash-safe: never pass --daemons. Do not remint. Do not wipe state.
  # Do not enable bot-bridge. Do not kill a live leftover bot-bridge pid.
  # Bot seats stay standby unless studio.env already opted the bridge in.
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
