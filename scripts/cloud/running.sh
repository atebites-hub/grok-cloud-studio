#!/usr/bin/env bash
# Print Cursor Cloud runStatus rows for GCS_CLOUD_REPO and CLOUD_MUST_LAUNCH.
# Count only runStatus=RUNNING. ACTIVE+FINISHED leftovers are not workers.
# Usage: running.sh [--work-kind playability|art] [--prompt TEXT]
# Never prints API keys.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "${HERE}/_common.sh"

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  echo "Usage: scripts/cloud/running.sh [--work-kind KIND] [--prompt TEXT] [--min N]"
  echo "Count RUNNING Cursor Cloud runs for GCS_CLOUD_REPO (default floor 8)."
  echo "Prints runStatus per agent. CLOUD_MUST_LAUNCH=1 for playability/art below floor."
  exit 0
fi

if ! cloud_load_auth; then
  echo "error: CURSOR_API_KEY is not set (export it or add it to ~/.config/cursor/agent.env)" >&2
  exit 1
fi

python3 "${HERE}/running_capacity.py" "$@"
