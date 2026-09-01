#!/usr/bin/env bash
# Canonical ship gate: .venv/bin/pytest -q AND python3 scripts/secret_scan.py.
# Requires N passed (N>=1). Extra High / Bot seats are out of scope here.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${GCS_ROOT:-$SCRIPT_DIR/../..}" && pwd)"
cd "$ROOT"

if [[ ! -x .venv/bin/pytest ]]; then
  echo "ship-gate: missing .venv/bin/pytest (run ./install.sh)" >&2
  exit 1
fi
if [[ ! -f scripts/secret_scan.py ]]; then
  echo "ship-gate: missing scripts/secret_scan.py" >&2
  exit 1
fi

# Capture pytest so we can require N passed.
set +e
pytest_out="$(.venv/bin/pytest -q 2>&1)"
pytest_rc=$?
set -e
printf '%s\n' "$pytest_out"

if [[ "$pytest_rc" -ne 0 ]]; then
  echo "ship-gate: pytest failed rc=${pytest_rc}" >&2
  exit "${pytest_rc}"
fi

if ! printf '%s\n' "$pytest_out" | grep -Eq '[1-9][0-9]* passed'; then
  echo "ship-gate: pytest produced no passing tests (need N passed, N>=1)" >&2
  exit 1
fi

set +e
scan_out="$(python3 scripts/secret_scan.py 2>&1)"
scan_rc=$?
set -e
printf '%s\n' "$scan_out"

if [[ "$scan_rc" -ne 0 ]]; then
  echo "ship-gate: secret_scan failed rc=${scan_rc}" >&2
  exit "${scan_rc}"
fi
if ! printf '%s\n' "$scan_out" | grep -q 'secret_scan=clean'; then
  echo "ship-gate: secret_scan did not print secret_scan=clean" >&2
  exit 1
fi

echo "ship-gate: OK"
exit 0
