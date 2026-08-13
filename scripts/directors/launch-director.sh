#!/usr/bin/env bash
# Launch a Grok Cloud Studio Director seat on Grok Build CLI with permission bypass.
# Usage: launch-director.sh <seat> [extra prompt...]
#        launch-director.sh --help
#        launch-director.sh --dry-run <seat> [extra prompt...]
# Env: BYPASS_PERMISSIONS=1 (synonym — always on for this launcher)
#      GCS_ROOT (default: repo root inferred from this script)
# Flags: grok --permission-mode bypassPermissions --always-approve
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${GCS_ROOT:-$SCRIPT_DIR/../..}" && pwd)"
PROMPTS_DIR="$ROOT/docs/studio/directors"
FOOTER="$SCRIPT_DIR/common_footer.txt"

usage() {
  cat <<USAGE
Usage: $(basename "$0") [--dry-run] <seat> [extra prompt...]

Seats:
  floor live-ops content narrative systems client art audio balance cloud-env qa-a qa-b studio-ops
  (aliases: live_ops, cloud_env, qa_a, qa_b, studio_ops, donald-double, donald_gb)
  (donald is NOT launchable here — Bot-only)

Runs:
  grok --permission-mode bypassPermissions --always-approve --cwd <repo> \\
       -p "\$(seat prompt + common footer + extras)" --output-format plain

BYPASS_PERMISSIONS=1 is accepted as a synonym (this launcher always bypasses).
--dry-run prints the composed prompt and exits without calling grok.

See: docs/studio/GROK_DIRECTORS.md
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

# Normalize seat → prompt file stem
normalize_seat() {
  local s
  s=$(echo "$1" | tr '[:upper:]' '[:lower:]' | tr '-' '_')
  case "$s" in
    floor|studio_floor|floor_manager) echo "floor" ;;
    live_ops|liveops) echo "live_ops" ;;
    content) echo "content" ;;
    narrative) echo "narrative" ;;
    systems) echo "systems" ;;
    client) echo "client" ;;
    art) echo "art" ;;
    audio) echo "audio" ;;
    balance) echo "balance" ;;
    cloud_env|cloudenv|cloud) echo "cloud_env" ;;
    qa_a|qaa|qa-a) echo "qa_a" ;;
    qa_b|qab|qa-b) echo "qa_b" ;;
    studio_ops|studio-ops|donald_double|donald-double|donald_gb) echo "studio_ops" ;;
    donald)
      echo "Donald stays on Grok Bot — do not launch via this script." >&2
      exit 2
      ;;
    *)
      echo "unknown seat: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
}

SEAT="$(normalize_seat "$SEAT_RAW")"
# Hyphen form for A2A / fleet ledger (qa_a → qa-a)
export GCS_DIRECTOR_SEAT="${SEAT//_/-}"
PROMPT_FILE="$PROMPTS_DIR/${SEAT}_director_prompt.txt"

if [[ ! -f "$PROMPT_FILE" ]]; then
  echo "missing prompt: $PROMPT_FILE" >&2
  exit 1
fi
if [[ ! -f "$FOOTER" ]]; then
  echo "missing footer: $FOOTER" >&2
  exit 1
fi

# BYPASS_PERMISSIONS synonym (always bypass for this launcher)
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

# User intent "bypassPermissions" → Grok Build: --permission-mode bypassPermissions AND --always-approve
# If launching via cursor-agent instead: --force / --yolo map to the same intent.
# exec so the launcher PID is grok itself (dispatch tracks this PID).
# Remove composed prompt first so EXIT/trap leftovers don't leak.
PROMPT_TEXT="$(cat "$COMPOSED")"
rm -f "$COMPOSED"
exec grok --permission-mode bypassPermissions --always-approve --trust \
  --cwd "$ROOT" \
  -p "$PROMPT_TEXT" \
  --output-format plain
