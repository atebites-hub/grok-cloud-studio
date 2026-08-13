#!/usr/bin/env bash
# Health check for a Grok Cloud Studio checkout. Never prints secrets.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
FAIL=0

ok() { printf 'OK  %s\n' "$*"; }
bad() { printf 'ERR %s\n' "$*"; FAIL=1; }

if command -v python3 >/dev/null 2>&1; then
  ok "python3 $(python3 -c 'import sys; print("%d.%d"%sys.version_info[:2])')"
else
  bad "python3 missing"
fi

for p in \
  scripts/a2a/hub.py \
  scripts/a2a/dispatch.py \
  scripts/a2a/duplex.py \
  scripts/a2a/send.sh \
  scripts/a2a/start-studio-bus.sh \
  scripts/directors/acp_inject.py \
  scripts/directors/start-seat-daemon.sh \
  scripts/directors/fleet-shepherd.py \
  scripts/studio/agent-kanban/fleet-bridge.py \
  docs/studio/AGENT_KANBAN.md \
  scripts/launch-cloud-extra-high.sh \
  scripts/cloud/spawn-waiter.sh \
  scripts/cloud/sdk/wait-notify.ts \
  scripts/cloud/webhook_receiver.py \
  scripts/mcp/gcs_mcp.py \
  plugins/a2a/.cursor-plugin/plugin.json \
  plugins/cursor-cloud/.cursor-plugin/plugin.json \
  docs/a2a/registry.json \
  docs/a2a/bot-agents.json \
  scripts/a2a/bind-bot-agent.sh \
  README.md LICENSE .gitignore .env.example
 do
  if [[ -e "$ROOT/$p" ]]; then
    ok "$p"
  else
    bad "missing $p"
  fi
done

if python3 "$ROOT/scripts/a2a/lib.py" launch-seats >/dev/null; then
  ok "registry seats: $(python3 "$ROOT/scripts/a2a/lib.py" launch-seats | tr '\n' ' ')"
else
  bad "lib.py launch-seats failed"
fi

# Bot bind: FAIL on empty/placeholder agentId unless GCS_BOT_BIND_OPTIONAL=1 (CI clones).
if [[ -x "$ROOT/scripts/a2a/bind-bot-agent.sh" || -f "$ROOT/scripts/a2a/bind-bot-agent.sh" ]]; then
  if bash "$ROOT/scripts/a2a/bind-bot-agent.sh" --check; then
    ok "bot-bind check"
  else
    bad "bot-bind unbound (set GCS_BOT_AGENT_ID and run scripts/a2a/bind-bot-agent.sh; CI clones may set GCS_BOT_BIND_OPTIONAL=1)"
  fi
else
  bad "missing scripts/a2a/bind-bot-agent.sh"
fi

if [[ -n "${GCS_CLOUD_REPO:-${CLOUD_REPO_URL:-}}" ]]; then
  ok "GCS_CLOUD_REPO/CLOUD_REPO_URL is set"
else
  printf 'WARN GCS_CLOUD_REPO unset (Extra High create will fail closed)\n'
fi

if [[ -n "${CURSOR_API_KEY:-}" ]]; then
  ok "CURSOR_API_KEY is set (value not printed)"
elif [[ -f "${CURSOR_AGENT_ENV:-$HOME/.config/cursor/agent.env}" ]]; then
  ok "CURSOR_API_KEY file present (value not printed)"
else
  printf 'WARN CURSOR_API_KEY unset (Extra High scripts need it)\n'
fi

if command -v grok >/dev/null 2>&1; then
  ok "grok CLI on PATH"
else
  printf 'WARN grok CLI not on PATH (ACP daemons / launch-director need it)\n'
fi

if command -v node >/dev/null 2>&1; then
  ok "node $(node -v 2>/dev/null || true)"
else
  printf 'WARN node missing (SDK will try ~/.cache/gcs-node or REST fallback)\n'
fi

if python3 "$ROOT/scripts/secret_scan.py" --root "$ROOT"; then
  ok "secret_scan=clean"
else
  bad "secret_scan failed"
fi

if [[ "$FAIL" -ne 0 ]]; then
  echo "doctor: FAIL"
  exit 1
fi
echo "doctor: OK"
exit 0
