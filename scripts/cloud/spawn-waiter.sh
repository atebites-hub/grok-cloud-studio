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

# Supervisor pid is what the ledger stores. wait-notify may still print
# CLOUD_WAITER_ERR and exit on a rate-limit; we restart it so fleet-shepherd
# never sees a dead waiter_pid (orphan) after 429. Invoke via bash because
# git ships these scripts as 100644.
export GCS_WAITER_ROOT="$ROOT"
export GCS_WAITER_ID="$LOOKUP_KEY"
export GCS_WAITER_RUN="${RUN:-}"
export GCS_WAITER_LOG="$LOG"

nohup bash -c '
set -uo pipefail
ROOT="${GCS_WAITER_ROOT:?}"
ID="${GCS_WAITER_ID:?}"
RUN="${GCS_WAITER_RUN:-}"
LOG="${GCS_WAITER_LOG:?}"
backoff_ms="${CLOUD_WAITER_RESTART_MS:-2000}"
cap_ms="${CLOUD_WAITER_RESTART_CAP_MS:-60000}"
if ! [[ "$backoff_ms" =~ ^[0-9]+$ ]] || [[ "$backoff_ms" -lt 1 ]]; then
  backoff_ms=2000
fi
if ! [[ "$cap_ms" =~ ^[0-9]+$ ]] || [[ "$cap_ms" -lt "$backoff_ms" ]]; then
  cap_ms=60000
fi

run_once() {
  if [[ -n "${CLOUD_WAITER_BIN:-}" ]]; then
    if [[ -x "${CLOUD_WAITER_BIN}" ]]; then
      "${CLOUD_WAITER_BIN}" --id "$ID" ${RUN:+--run "$RUN"}
    else
      bash "${CLOUD_WAITER_BIN}" --id "$ID" ${RUN:+--run "$RUN"}
    fi
  else
    bash "$ROOT/scripts/cloud/sdk/run.sh" wait-notify --id "$ID" ${RUN:+--run "$RUN"}
  fi
}

rate_limit_death() {
  [[ -f "$LOG" ]] || return 1
  tail -n 80 "$LOG" | grep -qiE "CLOUD_WAITER_ERR.*(429|rate[- ]?limit|ratelimit|too many requests)"
}

while true; do
  set +e
  run_once
  rc=$?
  set -e
  if [[ "$rc" -eq 0 ]]; then
    exit 0
  fi
  if rate_limit_death; then
    echo "CLOUD_WAITER_RESTART id=${ID} rc=${rc} backoff_ms=${backoff_ms}"
    sleep_s=$(awk -v ms="$backoff_ms" "BEGIN { printf \"%.3f\", ms/1000 }")
    sleep "$sleep_s"
    backoff_ms=$((backoff_ms * 2))
    if [[ "$backoff_ms" -gt "$cap_ms" ]]; then
      backoff_ms=$cap_ms
    fi
    continue
  fi
  exit "$rc"
done
' >>"$LOG" 2>&1 &
WAITER_PID=$!
disown "$WAITER_PID" 2>/dev/null || true

python3 "$LEDGER" set-waiter --id "$LOOKUP_KEY" --pid "$WAITER_PID" >/dev/null || true
echo "CLOUD_WAITER_SPAWNED id=${ID:-} run=${RUN:-} pid=$WAITER_PID log=$LOG"
