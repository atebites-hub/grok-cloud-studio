#!/usr/bin/env bash
# Source this file to export LINEAR_API_KEY from env or a secret file.
# Snapshot install: source scripts/cloud/load-linear-env.sh
# Never prints the key. Safe under `set -x` (temporarily disables it).
#
# Secret file search order:
#   $LINEAR_API_KEY_FILE
#   $GCS_A2A_STATE/secrets/linear.api_key
#   ~/.config/linear/api_key
#   ~/.config/cursor/agent.env (LINEAR_API_KEY= line)
set +o posix 2>/dev/null || true

_gcs_linear_restore=0
case "$-" in *x*) _gcs_linear_restore=1; set +x ;; esac

_gcs_linear_root="${GCS_ROOT:-}"
if [[ -z "$_gcs_linear_root" ]]; then
  _gcs_linear_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
fi
_gcs_linear_py="${_gcs_linear_root}/scripts/directors/linear_env.py"

if [[ -z "${LINEAR_API_KEY:-}" && -f "$_gcs_linear_py" ]]; then
  _gcs_linear_val="$(python3 "$_gcs_linear_py" value 2>/dev/null || true)"
  if [[ -n "$_gcs_linear_val" ]]; then
    export LINEAR_API_KEY="$_gcs_linear_val"
  fi
  unset _gcs_linear_val
fi

unset _gcs_linear_root _gcs_linear_py
if [[ "${_gcs_linear_restore}" -eq 1 ]]; then set -x; fi
unset _gcs_linear_restore
