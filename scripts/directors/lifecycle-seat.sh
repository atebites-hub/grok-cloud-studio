#!/usr/bin/env bash
# Alias → scripts/a2a/seat-lifecycle.sh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$SCRIPT_DIR/../a2a/seat-lifecycle.sh" "$@"
