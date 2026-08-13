#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
fail=0
pass() { printf 'PASS %s\n' "$*"; }
warn() { printf 'WARN %s\n' "$*"; }
bad() { printf 'FAIL %s\n' "$*"; fail=1; }
[[ -f scripts/a2a/send.sh ]] && pass "a2a/send.sh present" || bad "a2a/send.sh missing"
[[ -f scripts/a2a/hub.py ]] && pass "a2a/hub.py present" || bad "a2a/hub.py missing"
[[ -f scripts/a2a/start-bus.sh ]] && pass "start-bus.sh present" || bad "start-bus.sh missing"
[[ -f scripts/launch-cloud-extra-high.sh ]] && pass "launcher present" || bad "launcher missing"
[[ -f scripts/cloud/sdk/package.json ]] && pass "cloud sdk present" || bad "cloud sdk missing"
[[ -f docs/a2a/registry.json ]] && pass "registry present" || bad "registry missing"
[[ -f .env.example ]] && pass ".env.example present" || bad ".env.example missing"
command -v python3 >/dev/null 2>&1 && pass "python3 ok" || bad "python3 missing"
command -v curl >/dev/null 2>&1 && pass "curl ok" || bad "curl missing"
if [[ -n "${CURSOR_API_KEY:-}" ]]; then pass "CURSOR_API_KEY set (hidden)"; elif [[ -f "$HOME/.config/cursor/agent.env" ]]; then pass "agent.env present (hidden)"; else warn "CURSOR_API_KEY unset"; fi
repo="${GCS_CLOUD_REPO:-${CLOUD_REPO_URL:-${CURSOR_CLOUD_REPO:-}}}"
if [[ -n "$repo" ]]; then pass "GCS_CLOUD_REPO configured"; else warn "GCS_CLOUD_REPO unset"; fi
if [[ "$fail" -ne 0 ]]; then printf 'DOCTOR_FAIL\n'; exit 1; fi
printf 'DOCTOR_PASS\n'
