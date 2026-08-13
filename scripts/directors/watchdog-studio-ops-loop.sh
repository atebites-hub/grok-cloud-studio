#!/usr/bin/env bash
export PATH="${HOME}/.grok/bin:${PATH:-}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
exec bash "$ROOT/scripts/directors/watchdog-studio-ops.sh"
