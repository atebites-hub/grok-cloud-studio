#!/usr/bin/env bash
# Show Cursor Cloud agent(s) and latest-run runStatus. SDK-first; REST fallback.
# Usage: status.sh AGENT_ID [AGENT_ID...] [--ids ID,ID] [--json]
# Multiple ids are fetched in parallel so capacity beats do not serial-timeout
# get_agent_run. Prints runStatus per id. Never prints API keys.
# Do not remint list.sh runStatus (GCS #29).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "${HERE}/_common.sh"

usage() {
  echo "Usage: scripts/cloud/status.sh AGENT_ID [AGENT_ID...] [--ids ID,ID] [--json]"
  echo "       scripts/cloud/status-cloud-agent.sh --ids bc-1,bc-2,bc-3"
  echo "Prints runStatus (latest run) on the same line as id=. Parallel REST/SDK."
}

append_ids() {
  local raw="$1"
  local part
  IFS=',' read -r -a _status_parts <<< "$raw"
  for part in "${_status_parts[@]}"; do
    part="${part//[[:space:]]/}"
    if [[ -n "$part" ]]; then
      STATUS_IDS+=("$part")
    fi
  done
}

if [[ $# -lt 1 ]]; then
  usage >&2
  exit 1
fi

json=0
STATUS_IDS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --json)
      json=1
      shift
      ;;
    --ids)
      if [[ $# -lt 2 ]]; then
        echo "error: --ids requires ID,ID" >&2
        exit 1
      fi
      append_ids "$2"
      shift 2
      ;;
    --ids=*)
      append_ids "${1#--ids=}"
      shift
      ;;
    --)
      shift
      while [[ $# -gt 0 ]]; do
        append_ids "$1"
        shift
      done
      break
      ;;
    -*)
      echo "error: unknown option $1" >&2
      exit 1
      ;;
    *)
      append_ids "$1"
      shift
      ;;
  esac
done

deduped=()
seen="|"
for id in "${STATUS_IDS[@]+"${STATUS_IDS[@]}"}"; do
  case "$seen" in
    *"|$id|"*) continue ;;
  esac
  deduped+=("$id")
  seen+="${id}|"
done
STATUS_IDS=("${deduped[@]+"${deduped[@]}"}")

if [[ ${#STATUS_IDS[@]} -lt 1 ]]; then
  usage >&2
  exit 1
fi

if ! cloud_load_auth; then
  echo "error: CURSOR_API_KEY is not set (export it or add it to ~/.config/cursor/agent.env)" >&2
  exit 1
fi

sdk_args=()
if [[ "$json" -eq 1 ]]; then
  sdk_args+=(--json)
fi
sdk_args+=("${STATUS_IDS[@]}")
if cloud_sdk_exec status "${sdk_args[@]}"; then
  exit "$CLOUD_SDK_RC"
fi

if [[ "$json" -eq 1 && ${#STATUS_IDS[@]} -eq 1 ]]; then
  exec "${HERE}/result-cloud-agent.sh" "${STATUS_IDS[0]}"
fi

fetch_args=()
if [[ "$json" -eq 1 ]]; then
  fetch_args+=(--json)
fi
python3 "${HERE}/status_fetch.py" "${fetch_args[@]+"${fetch_args[@]}"}" -- "${STATUS_IDS[@]}"
