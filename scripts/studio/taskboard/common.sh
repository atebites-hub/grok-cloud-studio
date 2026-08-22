#!/usr/bin/env bash
# Shared helpers for host taskboard UI / MCP HTTP / Tailscale Serve.
# Never print credentials. Agent Kanban stays gone.
# shellcheck disable=SC2034

TASKBOARD_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GCS_KIT_ROOT="$(cd "${GCS_ROOT:-$TASKBOARD_SCRIPT_DIR/../../..}" && pwd)"
export GCS_ROOT="$GCS_KIT_ROOT"

gcs_studio_state_dir() {
  if [[ -n "${GCS_A2A_STATE:-}" ]]; then
    printf '%s\n' "$GCS_A2A_STATE"
    return 0
  fi
  if [[ -n "${PALEMON_A2A_STATE:-}" ]]; then
    printf '%s\n' "$PALEMON_A2A_STATE"
    return 0
  fi
  printf '%s\n' "$GCS_KIT_ROOT/.a2a-state"
}

gcs_source_studio_env() {
  local state envf
  state="$(gcs_studio_state_dir)"
  envf="$state/studio.env"
  if [[ -f "$envf" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$envf"
    set +a
  fi
}

gcs_taskboard_db() {
  if [[ -n "${GCS_TASKBOARD_DB:-}" ]]; then
    printf '%s\n' "$GCS_TASKBOARD_DB"
    return 0
  fi
  if [[ -n "${TASKBOARD_DB:-}" ]]; then
    printf '%s\n' "$TASKBOARD_DB"
    return 0
  fi
  printf '%s\n' "$(gcs_studio_state_dir)/taskboard/taskboard.db"
}

gcs_taskboard_vendor_dir() {
  printf '%s\n' "$GCS_KIT_ROOT/vendor/taskboard"
}

gcs_taskboard_submodule_prebuilt() {
  local cand
  for cand in \
    "$(gcs_taskboard_vendor_dir)/taskboard" \
    "$(gcs_taskboard_vendor_dir)/bin/taskboard"
  do
    if [[ -n "$cand" && -f "$cand" && -x "$cand" ]]; then
      printf '%s\n' "$cand"
      return 0
    fi
  done
  return 1
}

gcs_ensure_taskboard_submodule() {
  local dest
  dest="$(gcs_taskboard_vendor_dir)"
  if [[ -e "$dest/.git" ]]; then
    return 0
  fi
  if [[ ! -f "$GCS_KIT_ROOT/.gitmodules" ]]; then
    return 1
  fi
  git -C "$GCS_KIT_ROOT" submodule update --init --recursive -- vendor/taskboard
}

gcs_taskboard_bin() {
  local cand
  if [[ -n "${TASKBOARD_BIN:-}" && -x "${TASKBOARD_BIN}" ]]; then
    printf '%s\n' "$TASKBOARD_BIN"
    return 0
  fi
  if cand="$(gcs_taskboard_submodule_prebuilt)"; then
    printf '%s\n' "$cand"
    return 0
  fi
  for cand in \
    "$GCS_KIT_ROOT/bin/taskboard" \
    "${HOME:-}/.local/bin/taskboard" \
    /usr/local/bin/taskboard \
    /opt/homebrew/bin/taskboard \
    /usr/bin/taskboard
  do
    if [[ -n "$cand" && -x "$cand" ]]; then
      printf '%s\n' "$cand"
      return 0
    fi
  done
  cand="$(command -v taskboard 2>/dev/null || true)"
  if [[ -n "$cand" && -x "$cand" ]]; then
    printf '%s\n' "$cand"
    return 0
  fi
  return 1
}

gcs_pid_alive() {
  local pid="${1:-}" state
  [[ -n "$pid" ]] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  state=$(ps -p "$pid" -o state= 2>/dev/null | tr -d '[:space:]')
  [[ "$state" == Z* ]] && return 1
  return 0
}

gcs_read_pid() {
  local f="$1"
  if [[ -f "$f" ]]; then
    tr -d '[:space:]' <"$f" || true
  fi
}

gcs_stop_pid_file() {
  local pid_file="$1" label="${2:-PROC}"
  local pid
  pid="$(gcs_read_pid "$pid_file")"
  if gcs_pid_alive "$pid"; then
    kill "$pid" 2>/dev/null || true
    for _ in 1 2 3 4 5 6 7 8; do
      gcs_pid_alive "$pid" || break
      sleep 0.2
    done
    if gcs_pid_alive "$pid"; then
      kill -9 "$pid" 2>/dev/null || true
    fi
    echo "${label}_STOP pid=$pid"
  else
    echo "${label}_NOT_RUNNING"
  fi
  rm -f "$pid_file"
}

gcs_port_listening() {
  local host="$1" port="$2"
  if command -v ss >/dev/null 2>&1; then
    ss -ltn 2>/dev/null | grep -Eq ":${port}([[:space:]]|$)" && return 0
  fi
  (echo >/dev/tcp/"$host"/"$port") >/dev/null 2>&1
}
