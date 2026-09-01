#!/usr/bin/env bash
# Launch a Cursor Cloud Extra High grunt (grok-4.6, effort=xhigh, fast=false)
# against GCS_CLOUD_REPO / CLOUD_REPO_URL (required) from GCS_CLOUD_REF (default main)
# with autoCreatePR. Canonical: @cursor/sdk (scripts/cloud/sdk/launch.ts). REST curl is fallback.
# Prints CLOUD_LAUNCH_OK only on HTTP 200/201 (REST) or SDK create success.
# Otherwise CLOUD_LAUNCH_ERR. Never prints API keys.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=cloud/_common.sh
source "${SCRIPT_DIR}/cloud/_common.sh"

usage() {
  cat <<'EOF'
Usage: launch-cloud-extra-high.sh [--name NAME] [PROMPT]
       launch-cloud-extra-high.sh "prompt" [name]
       launch-cloud-extra-high.sh [--name NAME] -   # prompt on stdin

Creates a Cursor Cloud Extra High agent (SDK-first):
  model grok-4.6, params effort=xhigh and fast=false
  repo from GCS_CLOUD_REPO or CLOUD_REPO_URL (required)
  startingRef from GCS_CLOUD_REF (default main)
  autoCreatePR=true

REST fallback (CLOUD_FORCE_REST=1, GCS_CLOUD_BACKEND=rest,
SDK bootstrap fail, or CURSOR_API_BASE set): POST /v1/agents

Auth: CURSOR_API_KEY, or ~/.config/cursor/agent.env (never printed).
Prints CLOUD_LAUNCH_OK only on success; any other result is
CLOUD_LAUNCH_ERR and a non-zero exit.
EOF
}

fail_launch() {
  printf '%s\n' "CLOUD_LAUNCH_ERR"
  if [[ $# -gt 0 ]]; then
    printf '%s\n' "$*" >&2
  fi
  exit 1
}

name=""
prompt=""
name_from_flag=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --name)
      [[ $# -ge 2 ]] || fail_launch "error: --name requires a value"
      name="$2"
      name_from_flag=1
      shift 2
      ;;
    --name=*)
      name="${1#--name=}"
      name_from_flag=1
      shift
      ;;
    --)
      shift
      break
      ;;
    -)
      shift
      prompt="$(cat)"
      break
      ;;
    -*)
      fail_launch "error: unknown option $1"
      ;;
    *)
      break
      ;;
  esac
done

if [[ -z "$prompt" ]]; then
  if [[ "$name_from_flag" -eq 0 && $# -eq 2 ]]; then
    prompt="$1"
    name="$2"
  elif [[ $# -gt 0 ]]; then
    prompt="$*"
  elif [[ ! -t 0 ]]; then
    prompt="$(cat)"
  fi
fi

if [[ -z "${prompt//[$'\t\n\r ']/}" ]]; then
  fail_launch "error: prompt is required"
fi

if ! cloud_load_auth; then
  fail_launch "error: CURSOR_API_KEY is not set (export it or add it to ~/.config/cursor/agent.env)"
fi

CLOUD_REPO="$(python3 "${SCRIPT_DIR}/a2a/lib.py" cloud-repo)" || fail_launch "error: GCS_CLOUD_REPO or CLOUD_REPO_URL is required"
CLOUD_REF="$(python3 "${SCRIPT_DIR}/a2a/lib.py" cloud-ref)"
export GCS_CLOUD_REPO="$CLOUD_REPO"
export GCS_CLOUD_REF="$CLOUD_REF"
export CURSOR_CLOUD_REPO="${CURSOR_CLOUD_REPO:-$CLOUD_REPO}"
export CURSOR_CLOUD_REF="${CURSOR_CLOUD_REF:-$CLOUD_REF}"

if cloud_sdk_exec launch "$prompt" "$name"; then
  exit "$CLOUD_SDK_RC"
fi

payload="$(mktemp "${TMPDIR:-/tmp}/cloud-launch.XXXXXX")"
cleanup() { rm -f "$payload"; }
trap cleanup EXIT

CLOUD_PROMPT_TEXT="$prompt" CLOUD_AGENT_NAME="$name" GCS_CLOUD_REPO="$CLOUD_REPO" GCS_CLOUD_REF="$CLOUD_REF" python3 -c '
import json, os
prompt = os.environ.get("CLOUD_PROMPT_TEXT") or ""
name = os.environ.get("CLOUD_AGENT_NAME") or ""
repo = os.environ.get("GCS_CLOUD_REPO") or ""
ref = os.environ.get("GCS_CLOUD_REF") or "main"
if not repo:
    raise SystemExit("GCS_CLOUD_REPO missing")
body = {
    "prompt": {"text": prompt},
    "model": {
        "id": "grok-4.6",
        "params": [
            {"id": "effort", "value": "xhigh"},
            {"id": "fast", "value": "false"},
        ],
    },
    "repos": [
        {
            "url": repo,
            "startingRef": ref,
        }
    ],
    "autoCreatePR": True,
}
if name:
    body["name"] = name
print(json.dumps(body))
' >"$payload"

if ! cloud_http_request POST /v1/agents \
  -H "Content-Type: application/json" \
  --data-binary @"$payload"; then
  fail_launch "error: curl failed http=${CLOUD_HTTP_CODE:-000}"
fi

if ! cloud_http_is_create_ok; then
  echo "http=${CLOUD_HTTP_CODE}" >&2
  if [[ -n "${CLOUD_HTTP_BODY:-}" && -f "$CLOUD_HTTP_BODY" ]]; then
    cloud_redact_stream <"$CLOUD_HTTP_BODY" >&2 || true
  fi
  fail_launch "error: create rejected http=${CLOUD_HTTP_CODE}"
fi

printf '%s\n' "CLOUD_LAUNCH_OK"
id="$(cloud_json_get "$CLOUD_HTTP_BODY" agent.id)"
url="$(cloud_json_get "$CLOUD_HTTP_BODY" agent.url)"
run_id="$(cloud_json_get "$CLOUD_HTTP_BODY" run.id)"
[[ -n "$id" ]] && printf 'id=%s\n' "$id"
[[ -n "$url" ]] && printf 'url=%s\n' "$url"
[[ -n "$run_id" ]] && printf 'run_id=%s\n' "$run_id"
python3 "${SCRIPT_DIR}/directors/liv_evidence_stamp.py" \
  --kind cloud-launch \
  --seat "${GCS_DIRECTOR_SEAT:-${CLOUD_OWNER_SEAT:-floor}}" \
  --bc-id "${id}" \
  --name "${name}" \
  --text "${prompt}" || true
if [[ -n "$id" ]]; then
  bash "${SCRIPT_DIR}/cloud/spawn-waiter.sh" --id "$id" ${run_id:+--run "$run_id"} ${name:+--name "$name"} || true
fi
