#!/usr/bin/env bash
# Idempotent bootstrap for Grok Cloud Studio (Python tests + executable scripts).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

export PIP_DISABLE_PIP_VERSION_CHECK=1
export PYTHONDONTWRITEBYTECODE=1

pick_python() {
  local cand
  for cand in python3.13 python3.12 python3.11 python3; do
    if command -v "$cand" >/dev/null 2>&1; then
      if "$cand" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
        printf '%s\n' "$cand"
        return 0
      fi
    fi
  done
  return 1
}

PYTHON="$(pick_python)" || {
  echo "error: Python 3.11+ is required" >&2
  exit 1
}

if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "creating .venv with ${PYTHON}"
  "$PYTHON" -m venv "$ROOT/.venv"
fi

"$ROOT/.venv/bin/python" -m pip install --upgrade pip
"$ROOT/.venv/bin/python" -m pip install -r "$ROOT/requirements.txt"

chmod +x \
  "$ROOT/install.sh" \
  "$ROOT/doctor.sh" \
  "$ROOT/setup.sh" \
  "$ROOT/cleanup.sh" \
  "$ROOT/health_check.sh" \
  "$ROOT/recover.sh" \
  "$ROOT"/scripts/*.sh \
  "$ROOT"/scripts/ci/*.sh \
  "$ROOT"/scripts/a2a/*.sh \
  "$ROOT"/scripts/cloud/*.sh \
  "$ROOT"/scripts/cloud/sdk/*.sh \
  "$ROOT"/scripts/directors/*.sh \
  "$ROOT"/scripts/webhook/*.sh \
  "$ROOT"/scripts/studio/taskboard/*.sh \
  "$ROOT"/scripts/host/cursor-grok \
  2>/dev/null || true

chmod +x "$ROOT/scripts/a2a/bot-bridge.py" "$ROOT/scripts/a2a/bind-bot-agent.sh" \
  "$ROOT/scripts/a2a/wake-daemon.py" "$ROOT/scripts/a2a/host-ticker.py" \
  "$ROOT/scripts/directors/mind.py" 2>/dev/null || true
mkdir -p "$ROOT/.a2a-state"
python3 "$ROOT/scripts/a2a/lib.py" ensure-prompts >/dev/null || true

if [[ -n "${GCS_BOT_AGENT_ID:-}" ]]; then
  bash "$ROOT/scripts/a2a/bind-bot-agent.sh"
else
  echo "WARN GCS_BOT_AGENT_ID unset — Bot orchestrator is not bound to A2A."
  echo "     Set GCS_BOT_AGENT_ID and re-run ./install.sh or scripts/a2a/bind-bot-agent.sh."
  echo "     doctor fails on placeholder agentId unless GCS_BOT_BIND_OPTIONAL=1 (CI clone checks)."
fi

echo "install ok — run ./doctor.sh then .venv/bin/pytest -q"
echo "DR: ./setup.sh (deploy) and ./cleanup.sh (teardown); ./health_check.sh / ./recover.sh; docs/studio/WIPE.md"
echo "A2A: scripts/a2a/start-studio-bus.sh (hub+dispatch+shepherd; bot-bridge if GCS_BOT_BRIDGE=1); GROW: start --daemons"
echo "Mind: GCS_MIND_SEATS from studio.env (docs/studio/MIND.md); Palemon wipe: docs/studio/WIPE.md"
echo "Board: scripts/studio/taskboard/ (install-taskboard.sh is documented, not run here)"
echo "ACP inject timeout overlay 600s via studio.env (code default remains 180s in acp_inject.py)"
