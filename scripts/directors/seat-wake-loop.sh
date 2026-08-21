#!/usr/bin/env bash
# Block on .a2a-state/<seat>/inbox.jsonl growth, then ACP session/prompt
# into the live `grok agent serve` (same pid). GROW wake.
#
# Never grok --resume. If serve dies, restart serve (ensure_seat_serve).
# Dispatch does not own this inbox.
#
# Usage: seat-wake-loop.sh <seat>
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
if [[ -z "$SEAT_RAW" || "$SEAT_RAW" == "-h" || "$SEAT_RAW" == "--help" ]]; then
  echo "Usage: $(basename "$0") <seat>" >&2
  exit 2
fi

SEAT="$(normalize_seat "$SEAT_RAW")" || exit $?
SD="$(seat_state_dir "$SEAT")"
WAKE_PY="$ROOT/scripts/a2a/wake-daemon.py"
PID_FILE="$SD/wake.pid"

export_seat_serve_env "$SEAT"
: "${GCS_TASKBOARD_DB:?export_seat_serve_env must set GCS_TASKBOARD_DB}"

echo $$ >"$PID_FILE"
{
  echo "kind=grok-build-serve"
  echo "awake=inbox-acp-prompt"
  echo "mode=acp-serve"
} >"$SD/grow.mode"

if ! ensure_seat_serve "$SEAT"; then
  echo "WAKE_LOOP_FAIL seat=$SEAT serve down (never grok --resume)" >&2
  exit 1
fi

echo "WAKE_LOOP_START seat=$SEAT pid=$$ serve_pid=$(read_pid_file "$SD/daemon.pid") mode=acp-serve"

if [[ ! -f "$WAKE_PY" ]]; then
  echo "WAKE_LOOP_FAIL missing $WAKE_PY" >&2
  exit 1
fi

# Inbox consumer: ACP session/prompt into the live serve. Never grok --resume.
exec python3 "$WAKE_PY" --seat "$SEAT"
