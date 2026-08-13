#!/usr/bin/env bash
# Configure `ak` from AGENT_KANBAN_API_KEY, GCS_AGENT_KANBAN_API_KEY, or connector-secrets JSON api_key.
# Writes .a2a-state/agent-kanban/configured with timestamp + api-url only. Never prints secrets.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${GCS_ROOT:-$SCRIPT_DIR/../../..}" && pwd)"
STATE_DIR="${GCS_A2A_STATE:-$ROOT/.a2a-state}"
AK_DIR="$STATE_DIR/agent-kanban"
KANBAN_DIR="$STATE_DIR/kanban"
API_URL="${AGENT_KANBAN_API_URL:-${GCS_AGENT_KANBAN_API_URL:-https://agent-kanban.dev}}"
AK_BIN="${AGENT_KANBAN_BIN:-${GCS_AGENT_KANBAN_BIN:-ak}}"

export PATH="${HOME}/.local/bin:${PATH:-}"
mkdir -p "$AK_DIR" "$KANBAN_DIR"

ensure_ak_on_path() {
  if command -v "$AK_BIN" >/dev/null 2>&1; then
    return 0
  fi
  local cand
  for cand in \
    "${HOME}/.local/bin/ak" \
    "${HOME}/.local/lib/node_modules/agent-kanban/dist/index.js"
  do
    [[ -n "$cand" && -e "$cand" ]] || continue
    mkdir -p "${HOME}/.local/bin"
    ln -sfn "$cand" "${HOME}/.local/bin/ak"
    hash -r 2>/dev/null || true
    command -v ak >/dev/null 2>&1 && { AK_BIN=ak; return 0; }
  done
  return 1
}

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

if ! ensure_ak_on_path; then
  echo "AK_CONFIG_FAIL ak_missing (run scripts/studio/agent-kanban/install-ak.sh)" >&2
  exit 1
fi

KEY="${AGENT_KANBAN_API_KEY:-${GCS_AGENT_KANBAN_API_KEY:-}}"
if [[ -z "$KEY" ]]; then
  for cand in \
    "${AGENT_KANBAN_CONNECTOR_SECRETS:-}" \
    "${GCS_AGENT_KANBAN_CONNECTOR_SECRETS:-}" \
    "${AGENT_KANBAN_SECRET_PATH:-}" \
    "${GCS_AGENT_KANBAN_SECRET_PATH:-}" \
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

{ set +x; } 2>/dev/null || true
if ! "$AK_BIN" config set --api-url "$API_URL" --api-key "$KEY" >/dev/null; then
  echo "AK_CONFIG_FAIL config_set" >&2
  unset KEY
  exit 1
fi

{
  echo "ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  echo "api-url=$API_URL"
} >"$AK_DIR/configured"
cp -f "$AK_DIR/configured" "$KANBAN_DIR/configured" 2>/dev/null || true

if ! "$AK_BIN" get board >/dev/null; then
  echo "AK_CONFIG_FAIL smoke get_board" >&2
  unset KEY
  exit 1
fi

unset KEY
echo "AK_CONFIG_OK api-url=$API_URL state=$AK_DIR/configured"
