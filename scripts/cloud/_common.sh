# SDK dispatch + REST fallback for Extra High control-plane scripts.
# Sources auth.sh. Never print API keys. Safe to source more than once.

CLOUD_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=auth.sh
source "${CLOUD_SCRIPT_DIR}/auth.sh"
CLOUD_SDK_RUN="${CLOUD_SCRIPT_DIR}/sdk/run.sh"

# REST when Directors force it, SDK cannot start, or tests set CURSOR_API_BASE.
cloud_prefer_rest() {
  if [[ "${CLOUD_FORCE_REST:-0}" == "1" ]]; then
    return 0
  fi
  if [[ "${GCS_CLOUD_BACKEND:-}" == "rest" ]]; then
    return 0
  fi
  if [[ -n "${CURSOR_API_BASE:-}" ]]; then
    return 0
  fi
  return 1
}

# Return 0 if the caller should exit with CLOUD_SDK_RC.
# Return 1 if the caller should use REST curl (CURSOR_API_BASE / force / bootstrap fail).
# Exit 75 from sdk/run.sh is the only SDK failure that falls back; other codes must not
# double-create an agent via REST.
_cloud_sdk_try() {
  if cloud_prefer_rest; then
    if [[ "${CLOUD_FORCE_REST:-0}" == "1" || "${GCS_CLOUD_BACKEND:-}" == "rest" ]]; then
      echo "CLOUD_SDK_FALLBACK: REST requested (CLOUD_FORCE_REST or GCS_CLOUD_BACKEND=rest)" >&2
    fi
    return 1
  fi
  if [[ ! -x "$CLOUD_SDK_RUN" ]]; then
    if [[ "${CLOUD_ALLOW_REST_FALLBACK:-1}" == "1" ]]; then
      echo "CLOUD_SDK_FALLBACK: sdk/run.sh missing; using REST curl" >&2
      return 1
    fi
    echo "CLOUD_SDK_ERR: sdk/run.sh missing and REST fallback disabled" >&2
    exit 1
  fi
  set +e
  "$CLOUD_SDK_RUN" "$@"
  CLOUD_SDK_RC=$?
  set -e
  if [[ "$CLOUD_SDK_RC" -eq 75 ]]; then
    if [[ "${CLOUD_ALLOW_REST_FALLBACK:-1}" == "1" ]]; then
      echo "CLOUD_SDK_FALLBACK: SDK unavailable (exit 75); using REST curl" >&2
      return 1
    fi
    echo "CLOUD_SDK_ERR: SDK unavailable and REST fallback disabled" >&2
    exit 1
  fi
  return 0
}

# For wrappers: `if cloud_sdk_exec …; then exit "$CLOUD_SDK_RC"; fi` then REST.
cloud_sdk_exec() {
  _cloud_sdk_try "$@"
}

# LIV-103: Directors never block-wait on Cloud. Return 0 when this process
# must refuse watch/poll. Operators may set CLOUD_ALLOW_BLOCK_WAIT=1.
cloud_director_must_not_block_wait() {
  if [[ "${CLOUD_ALLOW_BLOCK_WAIT:-0}" == "1" ]]; then
    return 1
  fi
  if [[ -n "${GCS_DIRECTOR_SEAT:-}" ]]; then
    return 0
  fi
  return 1
}

# Print CLOUD_WATCH_REFUSED and return 0 when a Director watch must stop.
# Return 1 when watch/poll is allowed.
cloud_refuse_director_block_wait() {
  local agent_id="${1:-}"
  if ! cloud_director_must_not_block_wait; then
    return 1
  fi
  printf '%s\n' "CLOUD_WATCH_REFUSED"
  if [[ -n "$agent_id" ]]; then
    printf 'id=%s\n' "$agent_id"
  fi
  printf '%s\n' "reason=director-no-block-wait"
  printf '%s\n' "Directors must not block-wait on Cloud. The SDK waiter (scripts/cloud/sdk/wait-notify.ts via run.wait) A2A-pings the owning seat. Collect context with scripts/cloud/result-cloud-agent.sh ${agent_id:-<bc-id>} or MCP cloud_result. Operator override=CLOUD_ALLOW_BLOCK_WAIT=1. Never Bot CloudAgent." >&2
  return 0
}
