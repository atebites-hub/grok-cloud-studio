#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
if [[ "${1:-}" == "--dry-run" ]]; then echo INSTALL_DRY_RUN_OK; exit 0; fi
mkdir -p .a2a-state
if [[ ! -f .env && -f .env.example ]]; then cp .env.example .env; fi
if [[ -f scripts/cloud/sdk/package.json ]] && command -v npm >/dev/null 2>&1; then (cd scripts/cloud/sdk && npm install --no-fund --no-audit) || true; fi
echo INSTALL_OK
