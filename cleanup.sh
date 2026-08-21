#!/usr/bin/env bash
# One-command Palemon studio teardown. Idempotent disaster-recovery entrypoint.
# Default is soft: processes only. Never reconnects Agent Kanban. Never prints keys.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
export GCS_ROOT="${GCS_ROOT:-$ROOT}"

# shellcheck source=scripts/studio/taskboard/common.sh
source "$ROOT/scripts/studio/taskboard/common.sh"

usage() {
  cat <<'EOF'
Usage: cleanup.sh [--help]

One-command teardown (idempotent). Disaster recovery entrypoint with setup.sh.

Default (soft): stop the bus WITHOUT --daemons, then stop taskboard UI + MCP HTTP.
Does not delete .env, studio.env, grok login, Cursor login, inboxes, or pins.

  start-studio-bus.sh stop              default (leave seat serve running)
  start-studio-bus.sh stop --daemons    CLEANUP_DAEMONS=1 or CLEANUP_WIPE_STATE=1

  CLEANUP_DAEMONS=1     pass stop --daemons (also stop seat grok agent serve)
  CLEANUP_WIPE_STATE=1  stop daemons too, then remove $GCS_A2A_STATE pid/lock files
                        and wipe inboxes, mind pins, and taskboard.db.
                        WARNING: inboxes and taskboard.db are wiped.
                        studio.env, repo .env, grok login, and Cursor login are kept.

Never print secrets. Never reconnect Agent Kanban.
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
export GCS_A2A_STATE="$STATE"
mkdir -p "$STATE"

WITH_DAEMONS=0
if [[ "${CLEANUP_DAEMONS:-0}" == "1" || "${CLEANUP_WIPE_STATE:-0}" == "1" ]]; then
  WITH_DAEMONS=1
fi

if [[ "$WITH_DAEMONS" == "1" ]]; then
  bash "$ROOT/scripts/a2a/start-studio-bus.sh" stop --daemons || true
else
  bash "$ROOT/scripts/a2a/start-studio-bus.sh" stop || true
fi

bash "$ROOT/scripts/studio/taskboard/mcp-http.sh" stop || true
bash "$ROOT/scripts/studio/taskboard/start-taskboard.sh" stop || true

wipe_runtime_state() {
  local state="$1"
  echo "CLEANUP_WIPE_STATE WARNING: wiping inboxes and taskboard.db under $state (studio.env kept; .env and grok/Cursor login not touched)"
  find "$state" -type f \( -name '*.pid' -o -name '*.lock' \) -delete 2>/dev/null || true
  rm -f "$state/daemons.enabled" "$state/dispatch.mind-seats"
  find "$state" -type f -name 'inbox.jsonl' -delete 2>/dev/null || true
  # Pins live under <seat>/mind/ (session, cursor-session, offset).
  shopt -s nullglob
  local d
  for d in "$state"/*/mind; do
    rm -rf "$d"
  done
  shopt -u nullglob
  rm -f "$state/taskboard/taskboard.db"
}

if [[ "${CLEANUP_WIPE_STATE:-0}" == "1" ]]; then
  wipe_runtime_state "$STATE"
fi

echo "CLEANUP_OK"
