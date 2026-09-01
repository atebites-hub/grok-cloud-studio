#!/usr/bin/env bash
# Send a follow-up prompt to an existing Cursor Cloud agent. SDK-first.
# Prints CLOUD_FOLLOWUP_OK only on success. Never prints API keys.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "${HERE}/_common.sh"

fail_followup() {
  printf '%s\n' "CLOUD_FOLLOWUP_ERR"
  if [[ $# -gt 0 ]]; then
    printf '%s\n' "$*" >&2
  fi
  exit 1
}

if [[ $# -lt 1 || "$1" == "-h" || "$1" == "--help" ]]; then
  echo "Usage: scripts/cloud/followup.sh AGENT_ID [PROMPT]"
  echo "PROMPT may also be read from stdin when omitted."
  [[ $# -ge 1 && ( "$1" == "-h" || "$1" == "--help" ) ]] && exit 0
  fail_followup "error: AGENT_ID is required"
fi

agent_id="$1"
shift
prompt=""
if [[ $# -gt 0 ]]; then
  prompt="$*"
elif [[ ! -t 0 ]]; then
  prompt="$(cat)"
fi
if [[ -z "${prompt//[$'\t\n\r ']/}" ]]; then
  fail_followup "error: prompt is required"
fi

if ! cloud_load_auth; then
  fail_followup "error: CURSOR_API_KEY is not set (export it or add it to ~/.config/cursor/agent.env)"
fi

if cloud_sdk_exec followup "$agent_id" "$prompt"; then
  exit "$CLOUD_SDK_RC"
fi

payload="$(mktemp "${TMPDIR:-/tmp}/cloud-followup.XXXXXX")"
cleanup() { rm -f "$payload"; }
trap cleanup EXIT

CLOUD_PROMPT_TEXT="$prompt" python3 "${HERE}/extra_high_model.py" followup-body >"$payload"

if ! cloud_http_request POST "/v1/agents/${agent_id}/runs" \
  -H "Content-Type: application/json" \
  --data-binary @"$payload"; then
  fail_followup "error: curl failed http=${CLOUD_HTTP_CODE:-000}"
fi

if ! cloud_http_is_create_ok; then
  echo "http=${CLOUD_HTTP_CODE}" >&2
  if [[ -n "${CLOUD_HTTP_BODY:-}" && -f "$CLOUD_HTTP_BODY" ]]; then
    cloud_redact_stream <"$CLOUD_HTTP_BODY" >&2 || true
  fi
  fail_followup "error: follow-up rejected http=${CLOUD_HTTP_CODE}"
fi

if ! python3 "${HERE}/extra_high_model.py" check "$CLOUD_HTTP_BODY"; then
  fail_followup "error: follow-up model is not grok-4.6"
fi

printf '%s\n' "CLOUD_FOLLOWUP_OK"
run_id="$(cloud_json_get "$CLOUD_HTTP_BODY" run.id)"
[[ -n "$run_id" ]] && printf 'run_id=%s\n' "$run_id"
