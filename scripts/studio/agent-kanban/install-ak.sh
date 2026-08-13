#!/usr/bin/env bash
# Idempotent npm install -g agent-kanban (90s timeout). Exit 0 if `ak` is already on PATH.
set -euo pipefail

if command -v ak >/dev/null 2>&1; then
  echo "AK_INSTALL_OK already=$(command -v ak)"
  exit 0
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "AK_INSTALL_FAIL npm_missing" >&2
  exit 1
fi

set +e
if command -v timeout >/dev/null 2>&1; then
  timeout 90 npm install -g agent-kanban
  rc=$?
else
  npm install -g agent-kanban
  rc=$?
fi
set -e

if command -v ak >/dev/null 2>&1; then
  echo "AK_INSTALL_OK ak=$(command -v ak)"
  exit 0
fi

echo "AK_INSTALL_FAIL ak_missing rc=${rc:-1}" >&2
exit "${rc:-1}"
