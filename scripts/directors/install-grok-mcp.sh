#!/usr/bin/env bash
# Register tcarac/taskboard stdio MCP and Grok-catalog Linear HTTP MCP
# into each seat GROK_HOME/config.toml.
# PATH refresh only: does not start or remint a live serve.
#
# Usage: install-grok-mcp.sh [seat ...]
#   no args → every registry launch seat
#   one seat + GROK_HOME set → write that GROK_HOME (tests / explicit override)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=seat-daemon-common.sh
source "$SCRIPT_DIR/seat-daemon-common.sh"

if [[ -f "$STATE_DIR/studio.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$STATE_DIR/studio.env"
  set +a
fi

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  echo "Usage: $(basename "$0") [seat ...]" >&2
  echo "Register taskboard stdio MCP (absolute --db) and Linear HTTP MCP into seat GROK_HOME/config.toml." >&2
  echo "Does not remint a live serve." >&2
  exit 0
fi

seats=("$@")
if [[ ${#seats[@]} -eq 0 ]]; then
  seats=("${LAUNCH_SEATS[@]}")
fi

saved_gh="${GROK_HOME:-}"
for raw in "${seats[@]}"; do
  seat="$(normalize_seat "$raw")"
  sd="$(seat_state_dir "$seat")"
  if [[ ${#seats[@]} -eq 1 && -n "$saved_gh" ]]; then
    export GROK_HOME="$saved_gh"
  else
    export GROK_HOME="$sd/grok-home"
  fi
  install_seat_grok_mcp "$seat"
done
