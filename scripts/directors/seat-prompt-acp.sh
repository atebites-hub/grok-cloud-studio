#!/usr/bin/env bash
# Local ACP client: session/load + session/prompt into this seat's grok agent serve.
#
# GROW wake: inbox.jsonl growth → this client → ACP session/prompt INSIDE the
# live `grok agent serve` pid. Never grok --resume. Never mint a new ACP
# session per ping (`acp_inject.py --pin-session` reuses
# .a2a-state/<seat>/acp.session).
#
# Usage:
#   seat-prompt-acp.sh <seat> [prompt text...]
#   seat-prompt-acp.sh <seat> --file PATH
#   seat-prompt-acp.sh <seat> --stdin
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

SEAT_RAW="${1:-}"
shift || true
if [[ -z "$SEAT_RAW" || "$SEAT_RAW" == "-h" || "$SEAT_RAW" == "--help" ]]; then
  echo "Usage: $(basename "$0") <seat> [--stdin|--file PATH|prompt...]" >&2
  exit 2
fi

SEAT="$(normalize_seat "$SEAT_RAW")" || exit $?
refuse_bot_acp_seat "$SEAT" "ACP_PROMPT_SKIP" || exit $?
SD="$(seat_state_dir "$SEAT")"
INJECT="$SCRIPT_DIR/acp_inject.py"

if [[ ! -f "$INJECT" ]]; then
  echo "ACP_PROMPT_FAIL seat=$SEAT missing $INJECT" >&2
  exit 1
fi

export_seat_serve_env "$SEAT"
: "${GCS_TASKBOARD_DB:?export_seat_serve_env must set GCS_TASKBOARD_DB}"

if ! ensure_seat_serve "$SEAT"; then
  echo "ACP_PROMPT_FAIL seat=$SEAT serve down (never grok --resume)" >&2
  exit 1
fi

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
