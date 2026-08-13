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
  "$ROOT"/scripts/*.sh \
  "$ROOT"/scripts/a2a/*.sh \
  "$ROOT"/scripts/cloud/*.sh \
  "$ROOT"/scripts/cloud/sdk/*.sh \
  "$ROOT"/scripts/directors/*.sh \
  "$ROOT"/scripts/webhook/*.sh \
  2>/dev/null || true

echo "install ok — run ./doctor.sh then .venv/bin/pytest -q"
