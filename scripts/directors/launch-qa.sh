#!/usr/bin/env bash
# Launch QA A and/or QA B on Grok Build CLI.
# Usage:
#   launch-qa.sh [a|b|both] [--dry-run] [extra...]
#   launch-qa.sh --dry-run [a|b|both] [extra...]
#   launch-qa.sh --help
# Wraps launch-director.sh → grok --permission-mode bypassPermissions --always-approve
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAUNCH="$SCRIPT_DIR/launch-director.sh"

usage() {
  cat <<USAGE
Usage: $(basename "$0") [a|b|both] [--dry-run] [extra...]
       $(basename "$0") --dry-run [a|b|both] [extra...]

  a | qa-a   QA Director A (odd PRs)
  b | qa-b   QA Director B (even PRs)
  both       Launch A then B (default; live runs in parallel)

Always uses: grok --permission-mode bypassPermissions --always-approve
See docs/ARCHITECTURE.md and docs/PLUGINS.md
USAGE
}

DRY=()
TARGET=""
EXTRA=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h) usage; exit 0 ;;
    --dry-run) DRY=(--dry-run); shift ;;
    a|A|qa-a|qa_a|odd) TARGET="a"; shift ;;
    b|B|qa-b|qa_b|even) TARGET="b"; shift ;;
    both|ab|qa|all) TARGET="both"; shift ;;
    *) EXTRA+=("$1"); shift ;;
  esac
done
TARGET="${TARGET:-both}"

run_one() {
  local seat="$1"
  echo "=== launch-qa: seat=$seat dry=${DRY[*]:-no} ==="
  "$LAUNCH" "${DRY[@]}" "$seat" "${EXTRA[@]+"${EXTRA[@]}"}"
}

case "$TARGET" in
  a) run_one qa-a ;;
  b) run_one qa-b ;;
  both)
    if [[ ${#DRY[@]} -gt 0 ]]; then
      run_one qa-a
      echo '-----'
      run_one qa-b
      exit 0
    fi
    "$LAUNCH" qa-a "${EXTRA[@]+"${EXTRA[@]}"}" > /tmp/qa_a_grok.log 2>&1 &
    PA=$!
    "$LAUNCH" qa-b "${EXTRA[@]+"${EXTRA[@]}"}" > /tmp/qa_b_grok.log 2>&1 &
    PB=$!
    echo "QA A pid=$PA log=/tmp/qa_a_grok.log"
    echo "QA B pid=$PB log=/tmp/qa_b_grok.log"
    wait "$PA"; EA=$?
    wait "$PB"; EB=$?
    echo "QA_A_EXIT=$EA"; tail -n 20 /tmp/qa_a_grok.log || true
    echo "QA_B_EXIT=$EB"; tail -n 20 /tmp/qa_b_grok.log || true
    if [[ "$EA" -ne 0 ]]; then exit "$EA"; fi
    exit "$EB"
    ;;
esac
