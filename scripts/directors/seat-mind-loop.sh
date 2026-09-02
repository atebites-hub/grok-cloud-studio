#!/usr/bin/env bash
# Long-lived Grok Build mind for one seat. Mail is a turn.
# inbox.jsonl growth → scripts/directors/mind.py (mailbox + pin + stay-up;
# grok --resume pinned UUID --prompt-file mail; never bare -p).
# Installs grok-bot-like mind plugins (studio-mind, a2a, cursor-cloud)
# into seat GROK_HOME via grok plugin install --trust. Not Hermes plugin.yaml.
# No ACP WebSocket. No leftover inject. Does not start or kill grok agent serve.
#
# Usage: seat-mind-loop.sh <seat>
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
MIND_PY="$ROOT/scripts/directors/mind.py"
MIND_DIR="$SD/mind"
PID_FILE="$MIND_DIR/pid"

mkdir -p "$MIND_DIR"
export_seat_serve_env "$SEAT"
: "${GCS_TASKBOARD_DB:?export_seat_serve_env must set GCS_TASKBOARD_DB}"

echo $$ >"$PID_FILE"
{
  echo "kind=grok-build-mind"
  echo "awake=inbox-mind-turn"
  echo "mode=grok-build-mind"
} >"$MIND_DIR/mode"

install_studio_mind_plugin "$SEAT"
python3 "$ROOT/scripts/a2a/mind_bot_like.py" install-spawn --seat "$SEAT" \
  || echo "MIND_SPAWN_PATH_SKIP seat=$SEAT" >&2

echo "MIND_LOOP_START seat=$SEAT pid=$$ grok_home=${GROK_HOME} mode=grok-build-mind"

if [[ ! -f "$MIND_PY" ]]; then
  echo "MIND_LOOP_FAIL missing $MIND_PY" >&2
  exit 1
fi

exec python3 "$MIND_PY" --seat "$SEAT"
