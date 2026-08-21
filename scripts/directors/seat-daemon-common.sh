#!/usr/bin/env bash
# Shared helpers for per-seat ACP daemon scripts.
# Seats and ports come from docs/a2a/registry.json (see scripts/a2a/lib.py).
# shellcheck disable=SC2034

export PATH="${HOME}/.grok/bin:${PATH:-}"

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
  python3 "$LIB_PY" canonical "$1"
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

install_seat_identity() {
  local seat="$1"
  local sd src alias
  sd="$(seat_state_dir "$seat")"
  src="$ROOT/docs/studio/directors/souls/$seat"
  alias="$ROOT/docs/studio/directors/souls/$(python3 "$LIB_PY" canonical "$seat" 2>/dev/null || echo "$seat")"
  mkdir -p "$sd/grok-home"
  install_seat_grok_auth "$seat"
  if [[ -f "$src/SOUL.md" ]]; then
    cp "$src/SOUL.md" "$sd/SOUL.md"
  elif [[ -f "$alias/SOUL.md" ]]; then
    cp "$alias/SOUL.md" "$sd/SOUL.md"
  elif [[ ! -f "$sd/SOUL.md" ]]; then
    printf '# %s\n\nNamed identity for Grok Cloud Studio seat `%s`.\n' "$seat" "$seat" >"$sd/SOUL.md"
  fi
  if [[ -f "$src/MEMORY.md" ]]; then
    cp "$src/MEMORY.md" "$sd/MEMORY.md"
    cp "$src/MEMORY.md" "$sd/grok-home/memory.md"
  elif [[ -f "$alias/MEMORY.md" ]]; then
    cp "$alias/MEMORY.md" "$sd/MEMORY.md"
    cp "$alias/MEMORY.md" "$sd/grok-home/memory.md"
  elif [[ ! -f "$sd/MEMORY.md" ]]; then
    printf '# Memory — %s\n' "$seat" >"$sd/MEMORY.md"
  fi
}

install_seat_grok_auth() {
  # Copy host ~/.grok/auth.json into seat GROK_HOME so grok agent serve can
  # authenticate cached_token. Never echo the file. Never fail the seat boot.
  local seat="$1"
  local sd gh src dst
  sd="$(seat_state_dir "$seat")"
  gh="${GROK_HOME:-$sd/grok-home}"
  mkdir -p "$gh"
  dst="$gh/auth.json"
  src="${GROK_AUTH_JSON:-}"
  if [[ -z "$src" && -n "${HOME:-}" && -f "$HOME/.grok/auth.json" ]]; then
    src="$HOME/.grok/auth.json"
  fi
  if [[ -z "$src" || ! -f "$src" ]]; then
    echo "SEAT_GROK_AUTH_SKIP seat=$seat missing host auth.json" >&2
    return 0
  fi
  cp -f "$src" "$dst"
  chmod 600 "$dst" 2>/dev/null || true
  echo "SEAT_GROK_AUTH_OK seat=$seat dest=GROK_HOME/auth.json method=cached_token" >&2
}

ensure_seat_serve() {
  local seat="$1"
  local sd
  sd="$(seat_state_dir "$seat")"
  if daemon_healthy "$seat"; then
    {
      echo "kind=grok-build-serve"
      echo "awake=inbox-acp-prompt"
      echo "mode=acp-serve"
    } >"$sd/grow.mode"
    return 0
  fi
  if [[ ! -f "$SCRIPT_DIR/start-seat-daemon.sh" ]]; then
    echo "ensure_seat_serve: missing $SCRIPT_DIR/start-seat-daemon.sh" >&2
    return 1
  fi
  bash "$SCRIPT_DIR/start-seat-daemon.sh" "$seat"
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
    if [[ -f "$sd/SOUL.md" ]]; then
      echo "=== NAMED IDENTITY (SOUL.md) ==="
      cat "$sd/SOUL.md"
      echo
    fi
    cat "$prompt_file"
    echo
    cat "$FOOTER"
    cat <<PERSIST

=== PERSISTENT ACP SEAT ===
You are a long-lived grok agent serve process for seat "${seat}" (kind=grok-build-serve, mode=acp-serve).
Peer mail: send.sh → inbox.jsonl → seat-wake-loop.sh → local ACP session/prompt
into THIS serve pid (scripts/directors/seat-prompt-acp.sh). Same ACP session forever
(.a2a-state/${seat}/acp.session). Never mint a new session per ping.
Named identity is SOUL.md + MEMORY.md + GROK_MEMORY=1 on this serve process
(--agent-profile alone is not enough).
Host clock is host-ticker.py / host-clock-ticker.sh ACP_PING STATUS/CONTINUE inbox lines (tools allowed), not /loop and not watchdog ACP-inject.
If this serve dies, start-seat-daemon.sh / ensure_seat_serve restarts it.
After each session/prompt: do work (taskboard ticket move, send.sh, your own
scripts/launch-cloud-extra-high.sh). Tools are allowed. Do not idle.
RESULT is optional duplex, not a hang-up; RESULT-only / PONG is a bug.
Stay in this serve for the next inbox ping. Do not exit the serve process.
Export awareness: GCS_DIRECTOR_SEAT=${seat}
PERSIST
  } >"$profile"
  echo "$profile"
}
