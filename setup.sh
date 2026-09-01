#!/usr/bin/env bash
# One-command Palemon studio deploy. Idempotent disaster-recovery entrypoint.
# Never prints secrets. Never writes studio.env into git.
# Does not start grok agent serve (no --daemons). GCS_ACP_SEATS comes from env only.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
export GCS_ROOT="${GCS_ROOT:-$ROOT}"

# shellcheck source=scripts/studio/taskboard/common.sh
source "$ROOT/scripts/studio/taskboard/common.sh"

usage() {
  cat <<'EOF'
Usage: setup.sh [--help]

One-command deploy (idempotent). Disaster recovery entrypoint with cleanup.sh.

  1. Source $GCS_A2A_STATE/studio.env if present; else copy studio.env.example
     there (does not overwrite a live studio.env).
  2. Run ./install.sh (venv + chmod).
  3. Init vendor/taskboard submodule if missing (git submodule update --init).
  4. Board: scripts/studio/taskboard/setup-taskboard.sh start
     (host ticket/tb PATH links, start-taskboard.sh UI :3010, mcp-http.sh :3011).
  5. Start scripts/a2a/start-studio-bus.sh start   (NO --daemons)
  6. Optional Tailscale Serve (scripts/studio/taskboard/start-tailscale-serve.sh start).
     Skip if PALEMON_TAILSCALE_SERVE=0, tailscale missing, or not joined.
  7. Run ./doctor.sh (WARN if grok/agent/taskboard missing; FAIL if Agent Kanban returns)
  8. Print SETUP_OK with hub/board ports and mind seat list.
  9. Run ./health_check.sh (HEALTH_OK / HEALTH_DEGRADED / HEALTH_DOWN).

Never auto-spawn a 13-seat grok serve floor. Do not pass --daemons.
GCS_ACP_SEATS comes from env (studio.env) only; this script does not set it.
Never print secrets. Never git-add studio.env.
See docs/studio/WIPE.md.

Optional skips (already-bootstrapped box / tests):
  GCS_SETUP_SKIP_INSTALL=1    skip ./install.sh
  GCS_SETUP_SKIP_SUBMODULE=1  skip git submodule update --init
  GCS_SETUP_SKIP_START=1      skip taskboard install/start and bus start
  GCS_SETUP_SKIP_DOCTOR=1     skip ./doctor.sh
  GCS_SETUP_SKIP_HEALTH=1     skip ./health_check.sh (implied by SKIP_START)
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

gcs_source_studio_env
STATE="$(gcs_studio_state_dir)"
mkdir -p "$STATE"
export GCS_A2A_STATE="$STATE"

ENVF="$STATE/studio.env"
if [[ -f "$ENVF" ]]; then
  echo "SETUP_ENV_KEEP path=$ENVF"
else
  cp "$ROOT/studio.env.example" "$ENVF"
  echo "SETUP_ENV_COPIED path=$ENVF"
fi
gcs_source_studio_env
STATE="$(gcs_studio_state_dir)"
mkdir -p "$STATE"
export GCS_A2A_STATE="$STATE"

if [[ "${GCS_SETUP_SKIP_INSTALL:-0}" != "1" ]]; then
  bash "$ROOT/install.sh"
fi

if [[ "${GCS_SETUP_SKIP_SUBMODULE:-0}" != "1" ]]; then
  if [[ -e "$ROOT/vendor/taskboard/.git" ]]; then
    echo "SETUP_SUBMODULE_OK path=$ROOT/vendor/taskboard"
  elif [[ -f "$ROOT/.gitmodules" ]]; then
    echo "SETUP_SUBMODULE_INIT vendor/taskboard"
    git -C "$ROOT" submodule update --init --recursive -- vendor/taskboard
  else
    echo "SETUP_SUBMODULE_WARN missing .gitmodules; brew/tarball fallback" >&2
  fi
fi

if [[ "${GCS_SETUP_SKIP_SUBMODULE:-0}" == "1" ]]; then
  export GCS_TASKBOARD_SKIP_SUBMODULE=1
fi

if [[ "${GCS_SETUP_SKIP_START:-0}" != "1" ]]; then
  # Board-only path: host ticket/tb + start-taskboard.sh UI + mcp-http.sh MCP.
  bash "$ROOT/scripts/studio/taskboard/setup-taskboard.sh" start
  # Crash-safe: never pass --daemons. Do not start a 13-seat serve.
  bash "$ROOT/scripts/a2a/start-studio-bus.sh" start
  # Optional Tailscale Serve: already-joined only. Missing is WARN, not FAIL.
  bash "$ROOT/scripts/studio/taskboard/start-tailscale-serve.sh" start \
    || echo "SETUP_WARN tailscale serve failed (missing/not-joined is skip)" >&2
fi

if [[ "${GCS_SETUP_SKIP_DOCTOR:-0}" != "1" ]]; then
  bash "$ROOT/doctor.sh"
fi

HUB_PORT="${GCS_A2A_PORT:-8732}"
UI_HOST="${GCS_TASKBOARD_UI_HOST:-127.0.0.1}"
UI_PORT="${GCS_TASKBOARD_UI_PORT:-3010}"
MCP_HOST="${GCS_TASKBOARD_MCP_HOST:-127.0.0.1}"
MCP_PORT="${GCS_TASKBOARD_MCP_PORT:-3011}"
seats="$(python3 "$ROOT/scripts/a2a/lib.py" mind-seats 2>/dev/null | paste -sd, - || true)"
echo "SETUP_OK hub=http://127.0.0.1:${HUB_PORT} board_ui=http://${UI_HOST}:${UI_PORT} board_mcp=http://${MCP_HOST}:${MCP_PORT}/mcp mind_seats=${seats:-none}"

if [[ "${GCS_SETUP_SKIP_HEALTH:-0}" == "1" || "${GCS_SETUP_SKIP_START:-0}" == "1" ]]; then
  echo "SETUP_HEALTH_SKIP"
else
  bash "$ROOT/health_check.sh"
fi
