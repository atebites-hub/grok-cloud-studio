#!/usr/bin/env bash
# Launch a Grok Cloud Studio seat on Grok Build CLI with permission bypass.
# Usage: launch-director.sh <seat> [extra prompt...]
#        launch-director.sh --help
#        launch-director.sh --dry-run <seat> [extra prompt...]
# Env: BYPASS_PERMISSIONS=1 (synonym — always on for this launcher)
#      GCS_ROOT (default: repo root inferred from this script)
# Flags: grok --permission-mode bypassPermissions --always-approve
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${GCS_ROOT:-$SCRIPT_DIR/../..}" && pwd)"
export GCS_ROOT="$ROOT"
PROMPTS_DIR="${GCS_PROMPT_DIR:-$ROOT/prompts}"
FOOTER="$SCRIPT_DIR/common_footer.txt"
LIB_PY="$ROOT/scripts/a2a/lib.py"

usage() {
  local seats
  seats="$(python3 "$LIB_PY" launch-seats | tr '\n' ' ')"
  cat <<USAGE
Usage: $(basename "$0") [--dry-run] <seat> [extra prompt...]

Seats (from docs/a2a/registry.json):
  ${seats}

Runs:
  grok --permission-mode bypassPermissions --always-approve --cwd <repo> \
       -p "\$(seat prompt + common footer + extras)" --output-format plain

BYPASS_PERMISSIONS=1 is accepted as a synonym (this launcher always bypasses).
--dry-run prints the composed prompt and exits without calling grok.

See: docs/ARCHITECTURE.md
USAGE
}

DRY_RUN=0
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
  shift
fi

SEAT_RAW="${1:-}"
if [[ -z "$SEAT_RAW" ]]; then
  usage >&2
  exit 2
fi
shift || true
EXTRA="${*:-}"

SEAT="$(python3 "$LIB_PY" normalize "$SEAT_RAW")"
if ! python3 "$LIB_PY" launch-seats | grep -qx "$SEAT"; then
  if python3 "$LIB_PY" skip-seats | grep -qx "$SEAT"; then
    echo "seat $SEAT is in skipSeats — not launchable via this script." >&2
    exit 2
  fi
  echo "unknown seat: $SEAT_RAW" >&2
  usage >&2
  exit 2
fi

export GCS_DIRECTOR_SEAT="$SEAT"
STEM="${SEAT//-/_}"
PROMPT_FILE="$PROMPTS_DIR/${STEM}_director_prompt.txt"

if [[ ! -f "$PROMPT_FILE" ]]; then
  echo "missing prompt: $PROMPT_FILE" >&2
  exit 1
fi
if [[ ! -f "$FOOTER" ]]; then
  echo "missing footer: $FOOTER" >&2
  exit 1
fi

if [[ "${BYPASS_PERMISSIONS:-1}" != "1" && "${BYPASS_PERMISSIONS:-}" != "true" ]]; then
  echo "note: launch-director.sh always uses bypassPermissions + --always-approve" >&2
fi

COMPOSED=$(mktemp)
{
  cat "$PROMPT_FILE"
  echo
  cat "$FOOTER"
  if [[ -n "$EXTRA" ]]; then
    echo
    echo "=== EXTRA TURN INSTRUCTIONS ==="
    echo "$EXTRA"
  fi
} > "$COMPOSED"

if [[ "$DRY_RUN" == "1" ]]; then
  echo "=== DRY-RUN seat=$SEAT cwd=$ROOT ==="
  cat "$COMPOSED"
  rm -f "$COMPOSED"
  exit 0
fi

if ! command -v grok >/dev/null 2>&1; then
  echo "grok CLI not found on PATH" >&2
  rm -f "$COMPOSED"
  exit 1
fi

PROMPT_TEXT="$(cat "$COMPOSED")"
rm -f "$COMPOSED"
exec grok --permission-mode bypassPermissions --always-approve --trust \
  --cwd "$ROOT" \
  -p "$PROMPT_TEXT" \
  --output-format plain
