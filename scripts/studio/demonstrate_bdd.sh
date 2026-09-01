#!/usr/bin/env bash
# LIV-67 / LIV-73 / LIV-74. Directors paste stdout as demonstrated N.
# Targeted evidence files only — not leftover-green suite, not --override-ini.
# Palemon Linear is Living Sky LIV. Never Bot CloudAgent.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if [[ -x "${ROOT}/.venv/bin/pytest" ]]; then
  PYTEST=("${ROOT}/.venv/bin/pytest")
else
  PYTEST=(python3 -m pytest)
fi

# Single -q (ship-gate). pytest.ini must not also add -q (LIV-74).
exec "${PYTEST[@]}" -q \
  tests/test_liv67_list_prints_runstatus.py \
  tests/test_liv73_failing_then_passing.py \
  tests/test_liv74_demonstrated_n.py \
  tests/test_list_rows.py \
  "$@"
