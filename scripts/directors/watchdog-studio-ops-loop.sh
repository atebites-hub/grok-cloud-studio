#!/usr/bin/env bash
export PATH="$HOME/.grok/bin:$PATH"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
while true; do bash "$ROOT/scripts/directors/watchdog-studio-ops.sh"; sleep 600; done
