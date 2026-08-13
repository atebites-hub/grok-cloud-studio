#!/usr/bin/env bash
# Create or find the studio mission-control board. Register product git remote if `ak` supports it.
# Writes .a2a-state/agent-kanban/board.id (+ kanban/ mirror) and prints BOARD_URL. Never prints API keys.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${GCS_ROOT:-$SCRIPT_DIR/../../..}" && pwd)"
STATE_DIR="${GCS_A2A_STATE:-$ROOT/.a2a-state}"
AK_DIR="$STATE_DIR/agent-kanban"
KANBAN_DIR="$STATE_DIR/kanban"
AK_BIN="${AGENT_KANBAN_BIN:-${GCS_AGENT_KANBAN_BIN:-ak}}"
API_URL="${AGENT_KANBAN_API_URL:-${GCS_AGENT_KANBAN_API_URL:-https://agent-kanban.dev}}"
BOARD_NAME="${AGENT_KANBAN_BOARD_NAME:-${GCS_AGENT_KANBAN_BOARD_NAME:-}}"
if [[ -z "$BOARD_NAME" ]]; then
  BOARD_NAME="Pale""mon Studio"
fi
GITHUB_REPO="${AGENT_KANBAN_GITHUB_REPO:-${GCS_AGENT_KANBAN_GITHUB_REPO:-${GCS_CLOUD_REPO:-${CLOUD_REPO_URL:-}}}}"
if [[ -z "$GITHUB_REPO" ]]; then
  GITHUB_REPO="https://github.com/atebites-hub/pale""mon"
fi

export PATH="${HOME}/.local/bin:${PATH:-}"
mkdir -p "$AK_DIR" "$KANBAN_DIR"

if ! command -v "$AK_BIN" >/dev/null 2>&1; then
  if [[ -e "${HOME}/.local/lib/node_modules/agent-kanban/dist/index.js" ]]; then
    mkdir -p "${HOME}/.local/bin"
    ln -sfn "${HOME}/.local/lib/node_modules/agent-kanban/dist/index.js" "${HOME}/.local/bin/ak"
    hash -r 2>/dev/null || true
    AK_BIN=ak
  fi
fi
if ! command -v "$AK_BIN" >/dev/null 2>&1; then
  echo "AK_BOOTSTRAP_FAIL ak_missing" >&2
  exit 1
fi

write_board_markers() {
  local bid="$1" burl="${2:-}"
  printf '%s\n' "$bid" >"$AK_DIR/board.id"
  printf '%s\n' "$bid" >"$KANBAN_DIR/board.id"
  python3 - "$AK_DIR/board.json" "$bid" "$BOARD_NAME" "$burl" "$API_URL" "$GITHUB_REPO" "$KANBAN_DIR/board.json" <<'PY'
import json, sys
from pathlib import Path
path, bid, name, url, api, repo, mirror = sys.argv[1:8]
if not url:
    url = f"{api.rstrip('/')}/b/{bid}"
payload = {
    "board_id": bid,
    "id": bid,
    "name": name,
    "url": url,
    "repo": repo,
    "api_url": api,
}
text = json.dumps(payload, indent=2) + "\n"
Path(path).write_text(text, encoding="utf-8")
Path(mirror).write_text(text, encoding="utf-8")
PY
}

find_board() {
  python3 -c '
import json
import sys

want = sys.argv[1]
raw = sys.stdin.read().strip()
if not raw:
    raise SystemExit(0)
try:
    data = json.loads(raw)
except json.JSONDecodeError:
    raise SystemExit(0)
if isinstance(data, dict):
    data = data.get("data") or data.get("boards") or data.get("items") or data.get("result") or [data]
if not isinstance(data, list):
    raise SystemExit(0)
for board in data:
    if not isinstance(board, dict):
        continue
    if str(board.get("name") or "") != want:
        continue
    bid = str(board.get("id") or "").strip()
    url = str(board.get("url") or board.get("html_url") or "").strip()
    if bid:
        print(f"{bid}\t{url}")
        break
' "$BOARD_NAME"
}

BOARD_ID="${AGENT_KANBAN_BOARD_ID:-${GCS_AGENT_KANBAN_BOARD_ID:-}}"
BOARD_URL=""

if [[ -z "$BOARD_ID" && -f "$AK_DIR/board.id" ]]; then
  BOARD_ID="$(tr -d '[:space:]' <"$AK_DIR/board.id" || true)"
fi

if [[ -z "$BOARD_ID" ]]; then
  BOARDS_JSON="$("$AK_BIN" get board -o json 2>/dev/null || "$AK_BIN" get board || true)"
  HIT="$(printf '%s\n' "$BOARDS_JSON" | find_board || true)"
  BOARD_ID="${HIT%%$'\t'*}"
  BOARD_URL="${HIT#*$'\t'}"
  if [[ "$BOARD_ID" == "$HIT" ]]; then
    BOARD_URL=""
  fi
fi

if [[ -z "$BOARD_ID" ]]; then
  CREATE_OUT="$("$AK_BIN" create board --name "$BOARD_NAME" --type ops --description "Studio mission control (sync-only fleet mirror)")"
  BOARD_ID="$(printf '%s\n' "$CREATE_OUT" | python3 -c 'import re,sys; m=re.search(r"Created board\s+(\S+):", sys.stdin.read()); print(m.group(1) if m else "")')"
  if [[ -z "$BOARD_ID" ]]; then
    echo "AK_BOOTSTRAP_FAIL create_board" >&2
    exit 1
  fi
  echo "AK_BOOTSTRAP_CREATE id=$BOARD_ID"
else
  echo "AK_BOOTSTRAP_FOUND id=$BOARD_ID"
fi

if [[ -z "$BOARD_URL" ]]; then
  BOARD_URL="${API_URL%/}/b/${BOARD_ID}"
fi
write_board_markers "$BOARD_ID" "$BOARD_URL"

if [[ -n "$GITHUB_REPO" ]]; then
  if "$AK_BIN" create repo --name studio --url "$GITHUB_REPO" >/dev/null 2>&1; then
    echo "AK_BOOTSTRAP_REPO_OK"
  else
    echo "AK_BOOTSTRAP_REPO_SKIP"
  fi
fi

echo "BOARD_ID=$BOARD_ID"
echo "BOARD_URL=$BOARD_URL"
