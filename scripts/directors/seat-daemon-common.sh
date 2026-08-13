#!/usr/bin/env bash
# Shared helpers for per-seat ACP daemon scripts.
# Seats and ports come from docs/a2a/registry.json (see scripts/a2a/lib.py).
# shellcheck disable=SC2034

export PATH="${HOME}/.grok/bin:/home/box/.grok/bin:${PATH:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${GCS_ROOT:-$SCRIPT_DIR/../..}" && pwd)"
export GCS_ROOT="$ROOT"
STATE_DIR="${GCS_A2A_STATE:-$ROOT/.a2a-state}"
PROMPTS_DIR="${GCS_PROMPT_DIR:-$ROOT/prompts}"
FOOTER="$SCRIPT_DIR/common_footer.txt"
LIB_PY="$ROOT/scripts/a2a/lib.py"

mapfile -t LAUNCH_SEATS < <(python3 "$LIB_PY" launch-seats)

seat_port() {
  python3 "$LIB_PY" port "$1"
}

normalize_seat() {
  python3 "$LIB_PY" normalize "$1"
}

seat_prompt_stem() {
  echo "${1//-/_}"
}

seat_state_dir() {
  local seat="$1"
  mkdir -p "$STATE_DIR/$seat"
  echo "$STATE_DIR/$seat"
}

pid_alive() {
  local pid="${1:-}" state
  [[ -n "$pid" ]] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  state=$(ps -p "$pid" -o state= 2>/dev/null | tr -d '[:space:]')
  [[ "$state" == Z* ]] && return 1
  return 0
}

read_pid_file() {
  local f="$1"
  if [[ -f "$f" ]]; then
    tr -d '[:space:]' <"$f" || true
  fi
}

port_listening() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -ltn "sport = :$port" 2>/dev/null | grep -Eq ":${port}([[:space:]]|$)" && return 0
  fi
  (echo >/dev/tcp/127.0.0.1/"$port") >/dev/null 2>&1
}

daemon_healthy() {
  local seat="$1"
  local sd pid port
  sd="$(seat_state_dir "$seat")"
  pid="$(read_pid_file "$sd/daemon.pid")"
  port="$(seat_port "$seat")" || return 1
  pid_alive "$pid" || return 1
  port_listening "$port" || return 1
  [[ -f "$sd/acp.url" && -f "$sd/acp.secret" ]] || return 1
  return 0
}

write_agent_profile() {
  local seat="$1"
  local sd stem prompt_file profile
  sd="$(seat_state_dir "$seat")"
  stem="$(seat_prompt_stem "$seat")"
  prompt_file="$PROMPTS_DIR/${stem}_director_prompt.txt"
  profile="$sd/agent-profile.md"
  if [[ ! -f "$prompt_file" ]]; then
    echo "missing prompt: $prompt_file" >&2
    return 1
  fi
  if [[ ! -f "$FOOTER" ]]; then
    echo "missing footer: $FOOTER" >&2
    return 1
  fi
  {
    cat <<FRONT
---
name: gcs-${seat}-director
description: >
  Grok Cloud Studio ${seat} seat — persistent ACP daemon.
prompt_mode: full
model: inherit
permission_mode: bypassPermissions
agents_md: true
---

FRONT
    cat "$prompt_file"
    echo
    cat "$FOOTER"
    cat <<PERSIST

=== PERSISTENT ACP SEAT ===
You are a long-lived Grok agent serve process for seat "${seat}".
A2A wakeups arrive as session/prompt EXTRA TURN messages (not a fresh grok -p process).
After each wakeup: act on the MESSAGE, print exactly one RESULT (or PARK_ACK / QA_*_RESULT) line, then idle for the next inject.
Do not exit the daemon process. Do not wait for interactive chat.
Export awareness: GCS_DIRECTOR_SEAT=${seat}
PERSIST
  } >"$profile"
  echo "$profile"
}
