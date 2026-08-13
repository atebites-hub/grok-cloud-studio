#!/usr/bin/env bash
# After CLOUD_LAUNCH_OK: register the run in the fleet ledger and spawn a
# detached waiter that blocks on SDK run.wait() (or REST poll) then A2A-pings
# the owning seat. Disable with GCS_SPAWN_WAITER=0 / CLOUD_SPAWN_WAITER=0.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

ID=""
RUN=""
NAME=""
SEAT="${GCS_DIRECTOR_SEAT:-${CLOUD_OWNER_SEAT:-floor}}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --id) ID="${2:-}"; shift 2 ;;
    --run) RUN="${2:-}"; shift 2 ;;
    --name) NAME="${2:-}"; shift 2 ;;
    --seat) SEAT="${2:-}"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ "${GCS_SPAWN_WAITER:-${CLOUD_SPAWN_WAITER:-1}}" == "0" ]]; then
  echo "CLOUD_WAITER_SKIPPED id=${ID:-unset} reason=GCS_SPAWN_WAITER=0"
  exit 0
fi
if [[ "${CLOUD_WAITER_DRY:-0}" == "1" ]]; then
  echo "CLOUD_WAITER_DRY id=${ID:-unset} run=${RUN:-unset}"
  exit 0
fi

if [[ -z "$ID" && -z "$RUN" ]]; then
  echo "spawn-waiter.sh: --id or --run required" >&2
  exit 2
fi

LEDGER="$ROOT/scripts/cloud/fleet_ledger.py"
LOOKUP_KEY="${ID:-$RUN}"
python3 "$LEDGER" register \
  --id "$LOOKUP_KEY" \
  ${RUN:+--run "$RUN"} \
  ${NAME:+--name "$NAME"} \
  --seat "$SEAT" >/dev/null

LOG_DIR="${GCS_CLOUD_LOG_DIR:-$ROOT/.gcs-state/cloud-logs}"
mkdir -p "$LOG_DIR"
SAFE_KEY="$(printf '%s' "$LOOKUP_KEY" | tr -c 'A-Za-z0-9._-' '_')"
LOG="$LOG_DIR/waiter-${SAFE_KEY}.log"

nohup "$ROOT/scripts/cloud/sdk/run.sh" wait-notify \
  --id "$LOOKUP_KEY" \
  ${RUN:+--run "$RUN"} \
  >>"$LOG" 2>&1 &
WAITER_PID=$!
disown "$WAITER_PID" 2>/dev/null || true

python3 "$LEDGER" set-waiter --id "$LOOKUP_KEY" --pid "$WAITER_PID" >/dev/null || true
echo "CLOUD_WAITER_SPAWNED id=${ID:-} run=${RUN:-} pid=$WAITER_PID log=$LOG"
