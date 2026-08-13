#!/usr/bin/env bash
# Run Grok Cloud Studio @cursor/sdk CLIs: launch|list|status|watch|followup|result|wait-notify
# Exit 75 if Node >= 22.13 or npm deps cannot be prepared (bash wrappers may REST-fallback).
set -euo pipefail

SDK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENSURE="$SDK_DIR/ensure-node.sh"
CMD="${1:-}"
shift || true

case "$CMD" in
  launch|launch.ts) SCRIPT="launch.ts" ;;
  list|list.ts) SCRIPT="list.ts" ;;
  status|status.ts) SCRIPT="status.ts" ;;
  watch|watch.ts) SCRIPT="watch.ts" ;;
  followup|followup.ts) SCRIPT="followup.ts" ;;
  result|result.ts) SCRIPT="result.ts" ;;
  wait-notify|wait-notify.ts) SCRIPT="wait-notify.ts" ;;
  -h|--help|help|"")
    echo "usage: run.sh <launch|list|status|watch|followup|result|wait-notify> [args...]" >&2
    exit 2
    ;;
  *)
    echo "usage: run.sh <launch|list|status|watch|followup|result|wait-notify> [args...]" >&2
    exit 2
    ;;
esac

if [[ ! -x "$ENSURE" ]]; then
  echo "CLOUD_SDK_ERR: ensure-node.sh missing" >&2
  exit 75
fi

if ! NODE_BIN="$("$ENSURE")"; then
  echo "CLOUD_SDK_ERR: Node >= 22.13 required for @cursor/sdk (see scripts/cloud/README.md)" >&2
  exit 75
fi
NODE_HOME="$(cd "$(dirname "$NODE_BIN")/.." && pwd)"
export PATH="${NODE_HOME}/bin:${PATH}"
export NODE_NO_WARNINGS="${NODE_NO_WARNINGS:-1}"

if [[ ! -d "$SDK_DIR/node_modules/@cursor/sdk" ]]; then
  echo "CLOUD_SDK: installing @cursor/sdk (Node $($NODE_BIN -v))" >&2
  NPM_BIN="$(dirname "$NODE_BIN")/npm"
  if [[ ! -x "$NPM_BIN" ]]; then
    echo "CLOUD_SDK_ERR: npm missing next to Node" >&2
    exit 75
  fi
  if ! (
    cd "$SDK_DIR"
    if [[ -f package-lock.json ]]; then
      "$NPM_BIN" ci --no-fund --no-audit
    else
      "$NPM_BIN" install --no-fund --no-audit
    fi
  ); then
    echo "CLOUD_SDK_ERR: npm install failed in scripts/cloud/sdk" >&2
    exit 75
  fi
fi

TSX="$SDK_DIR/node_modules/tsx/dist/cli.mjs"
if [[ -f "$TSX" ]]; then
  exec "$NODE_BIN" "$TSX" "$SDK_DIR/$SCRIPT" "$@"
fi

exec "$NODE_BIN" --experimental-strip-types --no-warnings "$SDK_DIR/$SCRIPT" "$@"
