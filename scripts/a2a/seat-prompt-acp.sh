#!/usr/bin/env bash
# Local ACP client: session/load + session/prompt into this seat's grok agent serve.
#
# Inbox.jsonl growth → this client → ACP session/prompt INSIDE the live
# `grok agent serve` pid.
# Never grok --resume. Never mint a new ACP session per ping
# (`acp_inject.py --pin-session` reuses .a2a-state/<seat>/acp.session).
# Never Agent Kanban.
#
# Usage:
#   seat-prompt-acp.sh <seat> [prompt text...]
#   seat-prompt-acp.sh <seat> --file PATH
#   seat-prompt-acp.sh <seat> --stdin
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${GCS_ROOT:-$SCRIPT_DIR/../..}" && pwd)"
# shellcheck source=../directors/seat-daemon-common.sh
source "$ROOT/scripts/directors/seat-daemon-common.sh"

if [[ -f "$STATE_DIR/studio.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$STATE_DIR/studio.env"
  set +a
fi

SEAT_RAW="${1:-}"
shift || true
if [[ -z "$SEAT_RAW" || "$SEAT_RAW" == "-h" || "$SEAT_RAW" == "--help" ]]; then
  echo "Usage: $(basename "$0") <seat> [--stdin|--file PATH|prompt...]" >&2
  exit 2
fi

SEAT="$(normalize_seat "$SEAT_RAW")" || exit $?
if [[ "$SEAT" == "studio-ops" ]]; then
  SEAT="ops"
fi
SD="$(seat_state_dir "$SEAT")"
INJECT="$ROOT/scripts/directors/acp_inject.py"

if [[ ! -f "$INJECT" ]]; then
  echo "ACP_PROMPT_FAIL seat=$SEAT missing $INJECT" >&2
  exit 1
fi

if ! ensure_seat_serve "$SEAT"; then
  echo "ACP_PROMPT_FAIL seat=$SEAT serve down (never grok resume)" >&2
  exit 1
fi

export GCS_ROOT="$ROOT"
export GCS_A2A_STATE="$STATE_DIR"
export GCS_DIRECTOR_SEAT="$SEAT"
export GROK_HOME="${GROK_HOME:-$SD/grok-home}"
mkdir -p "$GROK_HOME"

# Pin session: session/load existing acp.session; never --force-new-session.
# acp_inject.py --pin-session returns when session/prompt is accepted
# (serve owns the turn). Do not session/cancel a live pin-session.
if [[ "${1:-}" == "--stdin" ]]; then
  python3 "$INJECT" --seat "$SEAT" --pin-session --stdin
elif [[ "${1:-}" == "--file" ]]; then
  python3 "$INJECT" --seat "$SEAT" --pin-session --file "${2:-}"
else
  python3 "$INJECT" --seat "$SEAT" --pin-session -- "$@"
fi
