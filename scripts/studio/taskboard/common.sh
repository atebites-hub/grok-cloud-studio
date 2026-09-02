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

gcs_taskboard_pin_file() {
  printf '%s\n' "$GCS_KIT_ROOT/scripts/studio/taskboard/PIN"
}

gcs_taskboard_pin() {
  local pinf line
  pinf="$(gcs_taskboard_pin_file)"
  if [[ ! -f "$pinf" ]]; then
    echo "error: missing taskboard PIN file: $pinf" >&2
    return 1
  fi
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%#*}"
    line="$(printf '%s' "$line" | tr -d '[:space:]')"
    if [[ -n "$line" ]]; then
      printf '%s\n' "$line"
      return 0
    fi
  done < "$pinf"
  echo "error: empty taskboard PIN file: $pinf" >&2
  return 1
}

gcs_taskboard_id_is_ulid() {
  local id="${1:-}"
  id="$(printf '%s' "$id" | tr '[:lower:]' '[:upper:]')"
  [[ "$id" =~ ^[0123456789ABCDEFGHJKMNPQRSTVWXYZ]{26}$ ]]
}

gcs_taskboard_vendor_dir() {
  printf '%s\n' "$GCS_KIT_ROOT/vendor/taskboard"
}

_gcs_taskboard_is_wrapper() {
  local f="$1"
  [[ -n "$f" && -f "$f" ]] || return 1
  # Wrappers are tiny shell scripts; never scan a compiled blob.
  head -c 2048 "$f" 2>/dev/null | grep -q "gcs-.*-taskboard-wrapper"
}

gcs_taskboard_submodule_prebuilt() {
  local cand
  for cand in \
    "$(gcs_taskboard_vendor_dir)/taskboard" \
    "$(gcs_taskboard_vendor_dir)/bin/taskboard"
  do
    if [[ -n "$cand" && -f "$cand" && -x "$cand" ]] && ! _gcs_taskboard_is_wrapper "$cand"; then
      printf '%s\n' "$cand"
      return 0
    fi
  done
  return 1
}

gcs_host_ticket_script() {
  printf '%s\n' "$TASKBOARD_SCRIPT_DIR/ticket"
}

gcs_host_tb_script() {
  printf '%s\n' "$TASKBOARD_SCRIPT_DIR/tb"
}

gcs_install_host_ticket_links() {
  local src_ticket src_tb
  src_ticket="$(gcs_host_ticket_script)"
  src_tb="$(gcs_host_tb_script)"
  [[ -f "$src_ticket" && -f "$src_tb" ]] || return 1
  chmod +x "$src_ticket" "$src_tb" 2>/dev/null || true
  mkdir -p "$GCS_KIT_ROOT/bin"
  ln -sfn "$src_ticket" "$GCS_KIT_ROOT/bin/ticket"
  ln -sfn "$src_tb" "$GCS_KIT_ROOT/bin/tb"
  if [[ -n "${HOME:-}" ]]; then
    mkdir -p "$HOME/.local/bin"
    ln -sfn "$src_ticket" "$HOME/.local/bin/ticket"
    ln -sfn "$src_tb" "$HOME/.local/bin/tb"
  fi
}

gcs_wait_listen() {
  local host="$1" port="$2"
  local tries="${3:-${GCS_TASKBOARD_READY_TRIES:-25}}"
  local i
  for ((i = 0; i < tries; i++)); do
    gcs_port_listening "$host" "$port" && return 0
    sleep 0.2
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
  if [[ -n "${TASKBOARD_BIN:-}" && -x "${TASKBOARD_BIN}" ]] && ! _gcs_taskboard_is_wrapper "${TASKBOARD_BIN}"; then
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
    if [[ -n "$cand" && -x "$cand" ]] && ! _gcs_taskboard_is_wrapper "$cand"; then
      printf '%s\n' "$cand"
      return 0
    fi
  done
  cand="$(command -v taskboard 2>/dev/null || true)"
  if [[ -n "$cand" && -x "$cand" ]] && ! _gcs_taskboard_is_wrapper "$cand"; then
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
