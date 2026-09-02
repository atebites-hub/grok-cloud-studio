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
  scripts/a2a/wake-daemon.py \
  scripts/a2a/host-ticker.py \
  scripts/a2a/send.sh \
  scripts/a2a/start-studio-bus.sh \
  scripts/directors/acp_inject.py \
  scripts/directors/seat-prompt-acp.sh \
  scripts/directors/seat-wake-loop.sh \
  scripts/directors/mind.py \
  scripts/directors/seat-mind-loop.sh \
  scripts/directors/start-seat-daemon.sh \
  scripts/directors/prompt-dir.sh \
  scripts/directors/fleet-shepherd.py \
  docs/studio/TASKBOARD.md \
  docs/studio/MIND.md \
  docs/studio/WIPE.md \
  studio.env.example \
  setup.sh \
  cleanup.sh \
  health_check.sh \
  recover.sh \
  scripts/studio/higgsfield_sentry.py \
  .gitmodules \
  .cursor/mcp.json \
  scripts/studio/taskboard/run-mcp.sh \
  scripts/studio/taskboard/start-taskboard.sh \
  scripts/studio/taskboard/mcp-http.sh \
  scripts/studio/taskboard/mcp_http_gateway.py \
  scripts/studio/taskboard/install-taskboard.sh \
  scripts/studio/taskboard/start-tailscale-serve.sh \
  scripts/host/cursor-grok \
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

_prompt_floor="$(python3 "$ROOT/scripts/a2a/lib.py" prompt-file floor 2>/dev/null || true)"
if [[ -n "$_prompt_floor" && -f "$_prompt_floor" ]]; then
  ok "director prompt floor=$_prompt_floor"
else
  bad "missing director prompt for floor (prompts/ or docs/studio/directors)"
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
  printf 'WARN grok CLI not on PATH (ACP daemons / launch-director / mind need it)\n'
fi

if command -v cursor-grok >/dev/null 2>&1 || command -v agent >/dev/null 2>&1; then
  ok "Cursor Agent CLI (agent/cursor-grok) on PATH"
else
  printf 'WARN agent/cursor-grok not on PATH (mind runner switch + Extra High host CLI; see docs/studio/WIPE.md)\n'
fi

if command -v taskboard >/dev/null 2>&1 || [[ -x "$ROOT/bin/taskboard" ]]; then
  ok "taskboard on PATH"
else
  printf 'WARN taskboard not on PATH (board UI/MCP; run scripts/studio/taskboard/install-taskboard.sh)\n'
fi

if [[ -e "$ROOT/vendor/taskboard/.git" ]]; then
  ok "vendor/taskboard submodule"
else
  printf 'WARN vendor/taskboard submodule not initialized (git clone --recurse-submodules, or git submodule update --init --recursive)\n'
fi

if command -v node >/dev/null 2>&1; then
  ok "node $(node -v 2>/dev/null || true)"
else
  printf 'WARN node missing (SDK will try ~/.cache/gcs-node or REST fallback)\n'
fi

if [[ -e "$ROOT/scripts/studio/agent-kanban" ]]; then
  bad "Agent Kanban tree reappeared (scripts/studio/agent-kanban) — do not reconnect ak"
fi

if python3 "$ROOT/scripts/secret_scan.py" --root "$ROOT"; then
  ok "secret_scan=clean"
else
  bad "secret_scan failed"
fi

# Isolated GROK_HOME does not inherit ~/.grok/config.toml. Cursor
# ${workspaceFolder} never expands under grok serve — WARN, do not FAIL.
STATE="${GCS_A2A_STATE:-$ROOT/.a2a-state}"

# Art Higgsfield/Sentry: fail-closed if MCP would leak keys (argv / literals).
# Never print values. Distinct from WIPE leftover-green / empty GitHub CI.
_sentry_args=(--root "$ROOT")
if [[ -d "$STATE" ]]; then
  _sentry_args+=(--state "$STATE")
fi
if [[ -n "${GROK_HOME:-}" ]]; then
  _sentry_args+=(--grok-home "$GROK_HOME")
fi
if python3 "$ROOT/scripts/studio/higgsfield_sentry.py" "${_sentry_args[@]}"; then
  ok "higgsfield_sentry=clean"
else
  bad "higgsfield_sentry failed (art MCP would leak keys; values not printed)"
fi
_gcs_warn_workspace_folder_mcp() {
  local f="$1"
  [[ -f "$f" ]] || return 0
  if grep -F '${workspaceFolder}' "$f" >/dev/null 2>&1; then
    printf 'WARN seat MCP config contains ${workspaceFolder} (never expands; register stdio MCP in GROK_HOME/config.toml): %s\n' "$f"
  fi
}
mcp_configs=()
if [[ -d "$STATE" ]]; then
  mapfile -d '' mcp_configs < <(find "$STATE" -path '*/grok-home/config.toml' -print0 2>/dev/null || true)
fi
for f in "${mcp_configs[@]}"; do
  [[ -n "$f" ]] || continue
  _gcs_warn_workspace_folder_mcp "$f"
done
if [[ -n "${GROK_HOME:-}" ]]; then
  _gcs_warn_workspace_folder_mcp "${GROK_HOME}/config.toml"
fi

if [[ "$FAIL" -ne 0 ]]; then
  echo "doctor: FAIL"
  exit 1
fi
echo "doctor: OK"
exit 0
