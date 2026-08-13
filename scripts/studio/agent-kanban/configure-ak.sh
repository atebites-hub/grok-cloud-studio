#!/usr/bin/env bash
# Configure `ak` from AGENT_KANBAN_API_KEY, GCS_AGENT_KANBAN_API_KEY, or connector-secrets JSON api_key.
# Writes .a2a-state/agent-kanban/configured with timestamp + api-url only. Never prints secrets.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${GCS_ROOT:-$SCRIPT_DIR/../../..}" && pwd)"
STATE_DIR="${GCS_A2A_STATE:-$ROOT/.a2a-state}"
AK_DIR="$STATE_DIR/agent-kanban"
API_URL="${AGENT_KANBAN_API_URL:-${GCS_AGENT_KANBAN_API_URL:-https://agent-kanban.dev}}"
AK_BIN="${AGENT_KANBAN_BIN:-${GCS_AGENT_KANBAN_BIN:-ak}}"

mkdir -p "$AK_DIR"

json_api_key() {
  local src="$1"
  python3 - "$src" <<'PY'
import json
import sys
from pathlib import Path

raw = sys.argv[1]
try:
    if raw.lstrip().startswith("{") or raw.lstrip().startswith("["):
        data = json.loads(raw)
    else:
        path = Path(raw)
        if not path.is_file():
            raise SystemExit(0)
        data = json.loads(path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    raise SystemExit(0)

def walk(obj) -> bool:
    if isinstance(obj, dict):
        for key, val in obj.items():
            if key in {"api_key", "apiKey", "AGENT_KANBAN_API_KEY", "GCS_AGENT_KANBAN_API_KEY"}:
                if isinstance(val, str) and val.strip():
                    print(val.strip())
                    return True
        for nested in ("agent-kanban", "agent_kanban", "ak"):
            if nested in obj and walk(obj[nested]):
                return True
        for val in obj.values():
            if walk(val):
                return True
    elif isinstance(obj, list):
        for item in obj:
            if walk(item):
                return True
    return False

walk(data)
PY
}

KEY="${AGENT_KANBAN_API_KEY:-${GCS_AGENT_KANBAN_API_KEY:-}}"
if [[ -z "$KEY" ]]; then
  for cand in \
    "${AGENT_KANBAN_CONNECTOR_SECRETS:-}" \
    "${GCS_AGENT_KANBAN_CONNECTOR_SECRETS:-}" \
    "$AK_DIR/connector-secrets.json" \
    "$ROOT/connector-secrets.json" \
    "${HOME}/.config/cursor/connector-secrets.json"
  do
    [[ -n "$cand" ]] || continue
    KEY="$(json_api_key "$cand" || true)"
    [[ -n "$KEY" ]] && break
  done
fi

if [[ -z "$KEY" ]]; then
  echo "AK_CONFIG_FAIL no_key (set AGENT_KANBAN_API_KEY or GCS_AGENT_KANBAN_API_KEY)" >&2
  exit 2
fi

if ! command -v "$AK_BIN" >/dev/null 2>&1; then
  echo "AK_CONFIG_FAIL ak_missing" >&2
  exit 1
fi

if ! "$AK_BIN" config set --api-url "$API_URL" --api-key "$KEY" >/dev/null; then
  echo "AK_CONFIG_FAIL config_set" >&2
  exit 1
fi

{
  echo "ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  echo "api-url=$API_URL"
} >"$AK_DIR/configured"

if ! "$AK_BIN" get board >/dev/null; then
  echo "AK_CONFIG_FAIL smoke get_board" >&2
  exit 1
fi

echo "AK_CONFIG_OK api-url=$API_URL state=$AK_DIR/configured"
