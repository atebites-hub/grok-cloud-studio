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
