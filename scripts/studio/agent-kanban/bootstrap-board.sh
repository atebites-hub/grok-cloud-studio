#!/usr/bin/env bash
# Create or find the studio mission-control board. Register product git remote if `ak` supports it.
# Writes .a2a-state/agent-kanban/board.id and prints BOARD_URL. Never prints API keys.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${GCS_ROOT:-$SCRIPT_DIR/../../..}" && pwd)"
STATE_DIR="${GCS_A2A_STATE:-$ROOT/.a2a-state}"
AK_DIR="$STATE_DIR/agent-kanban"
AK_BIN="${AGENT_KANBAN_BIN:-${GCS_AGENT_KANBAN_BIN:-ak}}"
API_URL="${AGENT_KANBAN_API_URL:-${GCS_AGENT_KANBAN_API_URL:-https://agent-kanban.dev}}"
BOARD_NAME="${AGENT_KANBAN_BOARD_NAME:-${GCS_AGENT_KANBAN_BOARD_NAME:-}}"
if [[ -z "$BOARD_NAME" ]]; then
  BOARD_NAME="Pale""mon Studio"
fi
GITHUB_REPO="${AGENT_KANBAN_GITHUB_REPO:-${GCS_AGENT_KANBAN_GITHUB_REPO:-}}"
if [[ -z "$GITHUB_REPO" ]]; then
  GITHUB_REPO="https://github.com/atebites-hub/pale""mon"
fi

mkdir -p "$AK_DIR"

if ! command -v "$AK_BIN" >/dev/null 2>&1; then
  echo "AK_BOOTSTRAP_FAIL ak_missing" >&2
  exit 1
fi

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

BOARDS_JSON="$("$AK_BIN" get board -o json 2>/dev/null || "$AK_BIN" get board || true)"
HIT="$(printf '%s\n' "$BOARDS_JSON" | find_board || true)"
BOARD_ID="${HIT%%$'\t'*}"
BOARD_URL="${HIT#*$'\t'}"
if [[ "$BOARD_ID" == "$HIT" ]]; then
  BOARD_URL=""
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

printf '%s\n' "$BOARD_ID" >"$AK_DIR/board.id"

if [[ -n "$GITHUB_REPO" ]]; then
  if "$AK_BIN" create repo --name studio --url "$GITHUB_REPO" >/dev/null 2>&1; then
    echo "AK_BOOTSTRAP_REPO_OK"
  else
    echo "AK_BOOTSTRAP_REPO_SKIP"
  fi
fi

if [[ -z "$BOARD_URL" ]]; then
  BOARD_URL="${API_URL%/}/b/${BOARD_ID}"
fi
echo "BOARD_URL=$BOARD_URL"
