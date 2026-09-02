#!/usr/bin/env bash
# Host clock: enqueue ACP_PING STATUS/CONTINUE onto a seat inbox.
# Inbox growth is woken by seat-wake-loop.sh → local ACP session/prompt.
# This script does not ACP-inject and does not emit a LAUNCH kind.
# Keep-alive is a work turn (not RESULT-only / PONG). Tools are allowed.
#
# Usage:
#   host-clock-ticker.sh enqueue_continue <seat>
#   host-clock-ticker.sh --once [seat,seat,...]
set -euo pipefail
# Never enable xtrace: callers may have secrets in the environment.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${GCS_ROOT:-$SCRIPT_DIR/../..}" && pwd)"
STATE_DIR="${GCS_A2A_STATE:-$ROOT/.a2a-state}"
LIB_PY="$ROOT/scripts/a2a/lib.py"
DEFAULT_SEATS="floor,ops"

enqueue_continue() {
  local seat="${1:-}"
  local now token inbox
  if [[ -z "$seat" ]]; then
    echo "usage: $0 enqueue_continue <seat>" >&2
    return 2
  fi
  if [[ -f "$LIB_PY" ]]; then
    mapped="$(python3 "$LIB_PY" known "$seat" 2>/dev/null || true)"
    if [[ -z "$mapped" ]]; then
      echo "HOST_CLOCK_SKIP seat=$seat reason=not-a-registry-seat"
      return 0
    fi
    seat="$mapped"
  fi
  now="$(date +%s)"
  token="tick-${seat}-${now}"
  inbox="$STATE_DIR/$seat/inbox.jsonl"
  mkdir -p "$STATE_DIR/$seat"
  python3 - "$inbox" "$seat" "$token" "$now" "$ROOT" <<'PY'
import sys
from pathlib import Path

inbox, seat, token, now, root = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
sys.path.insert(0, str(Path(root) / "scripts" / "a2a"))
from lib import append_inbox_record, host_tick_text

text = host_tick_text(seat, token)
rec = {
    "kind": "message",
    "role": "user",
    "taskId": token,
    "contextId": "host-clock",
    "parts": [{"kind": "text", "text": text}],
}
append_inbox_record(Path(inbox).parent, rec)
print(f"HOST_CLOCK_ENQUEUE seat={seat} token={token} ts={now}", flush=True)
PY
}

seats_from_arg() {
  local raw="${1:-}"
  local s
  if [[ -z "$raw" ]]; then
    raw="$DEFAULT_SEATS"
  fi
  IFS=',' read -r -a parts <<<"$raw"
  for s in "${parts[@]}"; do
    s="$(echo "$s" | tr -d '[:space:]')"
    [[ -n "$s" ]] && echo "$s"
  done
}

cmd="${1:-}"
case "$cmd" in
  enqueue_continue)
    enqueue_continue "${2:-}"
    ;;
  --once)
    while read -r seat; do
      [[ -z "$seat" ]] && continue
      enqueue_continue "$seat"
    done < <(seats_from_arg "${2:-}")
    ;;
  *)
    echo "usage: $0 enqueue_continue <seat> | --once [seats]" >&2
    exit 2
    ;;
esac
