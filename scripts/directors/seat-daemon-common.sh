#!/usr/bin/env bash
# Shared helpers for per-seat ACP daemon scripts.
# shellcheck disable=SC2034

export PATH="/home/box/.grok/bin:${PATH:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${GCS_ROOT:-$SCRIPT_DIR/../..}" && pwd)"
STATE_DIR="${GCS_A2A_STATE:-$ROOT/.a2a-state}"
PROMPTS_DIR="$ROOT/docs/studio/directors"
FOOTER="$SCRIPT_DIR/common_footer.txt"

# Stable ports — avoid hub 8732 and default grok serve 2419.
# Map documented in docs/studio/GROK_DIRECTORS.md § Persistent ACP.
seat_port() {
  case "$1" in
    floor) echo 8740 ;;
    live-ops) echo 8741 ;;
    content) echo 8742 ;;
    narrative) echo 8743 ;;
    systems) echo 8744 ;;
    client) echo 8745 ;;
    art) echo 8746 ;;
    audio) echo 8747 ;;
    balance) echo 8748 ;;
    cloud-env) echo 8749 ;;
    qa-a) echo 8750 ;;
    qa-b) echo 8751 ;;
    studio-ops) echo 8752 ;;
    *) return 1 ;;
  esac
}

LAUNCH_SEATS=(
  floor live-ops content narrative systems client art audio balance cloud-env qa-a qa-b studio-ops
)

normalize_seat() {
  local s
  s=$(echo "$1" | tr '[:upper:]' '[:lower:]' | tr '_' '-')
  case "$s" in
    floor|studio-floor|floor-manager) echo "floor" ;;
    live-ops|liveops) echo "live-ops" ;;
    content) echo "content" ;;
    narrative) echo "narrative" ;;
    systems) echo "systems" ;;
    client) echo "client" ;;
    art) echo "art" ;;
    audio) echo "audio" ;;
    balance) echo "balance" ;;
    cloud-env|cloudenv|cloud) echo "cloud-env" ;;
    qa-a|qaa) echo "qa-a" ;;
    qa-b|qab) echo "qa-b" ;;
    studio-ops|donald-double|donald-gb) echo "studio-ops" ;;
    donald)
      echo "Donald stays on Grok Bot — no ACP daemon." >&2
      return 2
      ;;
    *)
      echo "unknown seat: $1" >&2
      return 2
      ;;
  esac
}

# Underscore stem for prompt filenames (art → art, live-ops → live_ops)
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
  # Prefer ss; fall back to bash /dev/tcp
  if command -v ss >/dev/null 2>&1; then
    ss -ltn "sport = :$port" 2>/dev/null | rg -q ":${port}\\b" && return 0
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
  Grok Cloud Studio ${seat} Director — persistent ACP seat daemon.
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
