#!/usr/bin/env bash
# Optional cursor-agent shim for Agent Kanban leader ancestry.
# Prefer NOT installing over a real cursor-agent binary.
# Preferred runtime pattern (used by board-writer.sh):
#   exec -a cursor-agent bash scripts/studio/agent-kanban/board-writer-loop.sh
#
# Usage:
#   cursor-agent-shim.sh              # long-lived ancestry anchor (sleep loop)
#   cursor-agent-shim.sh --install    # install ~/.local/bin/cursor-agent ONLY if safe
#   cursor-agent-shim.sh --help
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

real_cursor_agent() {
  local cand
  shopt -s nullglob
  for cand in "${HOME}/.local/share/cursor-agent/versions/"*/cursor-agent; do
    [[ -x "$cand" ]] && { printf "%s" "$cand"; shopt -u nullglob; return 0; }
  done
  shopt -u nullglob
  if command -v cursor-agent >/dev/null 2>&1; then
    cand="$(command -v cursor-agent)"
    if [[ "$cand" != "${HOME}/.local/bin/cursor-agent" ]]; then
      printf "%s" "$cand"
      return 0
    fi
  fi
  return 1
}

cmd="${1:-}"
case "$cmd" in
  --help|-h)
    cat <<EOF
cursor-agent-shim.sh — optional AK ancestry helper

Prefer board-writer.sh, which starts with:
  exec -a cursor-agent bash board-writer-loop.sh

--install only links ~/.local/bin/cursor-agent when no real cursor-agent
exists under ~/.local/share/cursor-agent/versions/*/cursor-agent.
EOF
    exit 0
    ;;
  --install)
    if real="$(real_cursor_agent)"; then
      echo "AK_SHIM_SKIP real_cursor_agent=$real (prefer exec -a cursor-agent; do not clobber)"
      exit 0
    fi
    mkdir -p "${HOME}/.local/bin"
    ln -sfn "$SCRIPT_DIR/cursor-agent-shim.sh" "${HOME}/.local/bin/cursor-agent"
    echo "AK_SHIM_INSTALLED path=${HOME}/.local/bin/cursor-agent"
    exit 0
    ;;
esac

export CURSOR_AGENT="${CURSOR_AGENT:-1}"
exec -a cursor-agent bash -c "while true; do sleep 3600; done"
