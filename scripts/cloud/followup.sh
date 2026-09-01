#!/usr/bin/env bash
# Send a follow-up prompt to an existing Cursor Cloud agent. SDK-first.
# REFUSE when the latest runStatus is RUNNING (do not stack a second live Extra High).
# Leftover ACTIVE+FINISHED may follow up. Never Bot CloudAgent.
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

# Refuse line must include runStatus= so Directors see why send was blocked.
refuse_live_followup() {
  local rs="${1:-unknown}"
  printf '%s\n' "CLOUD_FOLLOWUP_ERR runStatus=${rs}"
  printf '%s\n' "error: refuse live Extra High runStatus=${rs}; do not stack a second run" >&2
  exit 1
}

probe_latest_run_status() {
  local latest_run_id=""
  if ! cloud_http_request GET "/v1/agents/${agent_id}"; then
    fail_followup "error: curl failed probing agent http=${CLOUD_HTTP_CODE:-000}"
  fi
  if ! cloud_http_is_2xx; then
    echo "http=${CLOUD_HTTP_CODE}" >&2
    if [[ -n "${CLOUD_HTTP_BODY:-}" && -f "$CLOUD_HTTP_BODY" ]]; then
      cloud_redact_stream <"$CLOUD_HTTP_BODY" >&2 || true
    fi
    fail_followup "error: follow-up status probe failed http=${CLOUD_HTTP_CODE}"
  fi
  latest_run_id="$(cloud_json_get "$CLOUD_HTTP_BODY" latestRunId)"
  FOLLOWUP_RUN_STATUS=""
  if [[ -z "$latest_run_id" ]]; then
    return 0
  fi
  if ! cloud_http_request GET "/v1/agents/${agent_id}/runs/${latest_run_id}"; then
    fail_followup "error: curl failed probing run http=${CLOUD_HTTP_CODE:-000}"
  fi
  if ! cloud_http_is_2xx; then
    echo "http=${CLOUD_HTTP_CODE}" >&2
    if [[ -n "${CLOUD_HTTP_BODY:-}" && -f "$CLOUD_HTTP_BODY" ]]; then
      cloud_redact_stream <"$CLOUD_HTTP_BODY" >&2 || true
    fi
    fail_followup "error: follow-up run probe failed http=${CLOUD_HTTP_CODE}"
  fi
  FOLLOWUP_RUN_STATUS="$(cloud_json_get "$CLOUD_HTTP_BODY" status)"
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

# Never follow up on the Grok Bot orchestrator id. Extra High is the grunt.
if [[ -n "${GCS_BOT_AGENT_ID:-}" && "$agent_id" == "$GCS_BOT_AGENT_ID" ]]; then
  printf '%s\n' "CLOUD_FOLLOWUP_ERR"
  printf '%s\n' "error: never Bot CloudAgent (orchestrator/donald is send.sh)" >&2
  exit 1
fi

FOLLOWUP_RUN_STATUS=""
probe_latest_run_status
FOLLOWUP_RUN_STATUS_UC="$(printf '%s' "${FOLLOWUP_RUN_STATUS}" | tr '[:lower:]' '[:upper:]')"
if [[ "$FOLLOWUP_RUN_STATUS_UC" == "RUNNING" ]]; then
  refuse_live_followup "RUNNING"
fi

if cloud_sdk_exec followup "$agent_id" "$prompt"; then
  exit "$CLOUD_SDK_RC"
fi

payload="$(mktemp "${TMPDIR:-/tmp}/cloud-followup.XXXXXX")"
cleanup() { rm -f "$payload"; }
trap cleanup EXIT

CLOUD_PROMPT_TEXT="$prompt" python3 -c '
import json, os
print(json.dumps({"prompt": {"text": os.environ.get("CLOUD_PROMPT_TEXT") or ""}}))
' >"$payload"

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

printf '%s\n' "CLOUD_FOLLOWUP_OK"
run_id="$(cloud_json_get "$CLOUD_HTTP_BODY" run.id)"
[[ -n "$run_id" ]] && printf 'run_id=%s\n' "$run_id"
