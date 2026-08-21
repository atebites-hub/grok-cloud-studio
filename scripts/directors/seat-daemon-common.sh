#!/usr/bin/env bash
# Shared helpers for per-seat ACP daemon scripts.
# Seats and ports come from docs/a2a/registry.json (see scripts/a2a/lib.py).
# shellcheck disable=SC2034

export PATH="${HOME}/.grok/bin:${PATH:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${GCS_ROOT:-$SCRIPT_DIR/../..}" && pwd)"
export GCS_ROOT="$ROOT"
STATE_DIR="${GCS_A2A_STATE:-$ROOT/.a2a-state}"
export GCS_A2A_STATE="$STATE_DIR"
# Studio board SQLite. Wrappers always pass --db so grok serve does not
# fall back to ~/.config/taskboard/taskboard.db.
GCS_TASKBOARD_DB="${GCS_TASKBOARD_DB:-${TASKBOARD_DB:-$STATE_DIR/taskboard/taskboard.db}}"
export GCS_TASKBOARD_DB
export TASKBOARD_DB="$GCS_TASKBOARD_DB"
FOOTER="$SCRIPT_DIR/common_footer.txt"
LIB_PY="$ROOT/scripts/a2a/lib.py"
# shellcheck source=prompt-dir.sh
source "$SCRIPT_DIR/prompt-dir.sh"

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

_gcs_taskboard_is_wrapper() {
  local f="$1"
  [[ -f "$f" ]] || return 1
  grep -q "gcs-seat-taskboard-wrapper" "$f" 2>/dev/null
}

resolve_taskboard_bin() {
  local cand dir found oldifs
  if [[ -n "${TASKBOARD_BIN:-}" && -x "${TASKBOARD_BIN}" ]] && ! _gcs_taskboard_is_wrapper "$TASKBOARD_BIN"; then
    printf '%s\n' "$TASKBOARD_BIN"
    return 0
  fi
  for cand in \
    "$ROOT/bin/taskboard" \
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
  oldifs="$IFS"
  IFS=':'
  for dir in ${PATH:-}; do
    IFS="$oldifs"
    cand="${dir}/taskboard"
    if [[ -n "$dir" && -x "$cand" ]] && ! _gcs_taskboard_is_wrapper "$cand"; then
      printf '%s\n' "$cand"
      return 0
    fi
  done
  IFS="$oldifs"
  found="$(command -v taskboard 2>/dev/null || true)"
  if [[ -n "$found" && -x "$found" ]] && ! _gcs_taskboard_is_wrapper "$found"; then
    printf '%s\n' "$found"
    return 0
  fi
  return 1
}

_write_taskboard_wrapper() {
  local dest="$1" kind="$2" bin="$3" db="$4"
  local bin_q db_q
  mkdir -p "$(dirname "$dest")"
  bin_q="$(printf '%q' "$bin")"
  db_q="$(printf '%q' "$db")"
  case "$kind" in
    taskboard)
      cat >"$dest" <<EOF
#!/bin/bash
# gcs-seat-taskboard-wrapper
set -euo pipefail
BIN=\${TASKBOARD_BIN:-$bin_q}
DB=\${GCS_TASKBOARD_DB:-\${TASKBOARD_DB:-$db_q}}
if [[ ! -x "\$BIN" ]]; then
  echo "GCS_TASKBOARD_FAIL missing binary (set TASKBOARD_BIN)" >&2
  exit 127
fi
has_db=0
for arg in "\$@"; do
  if [[ "\$arg" == "--db" ]]; then
    has_db=1
    break
  fi
done
if [[ "\$has_db" == "1" ]]; then
  exec "\$BIN" "\$@"
fi
exec "\$BIN" --db "\$DB" "\$@"
EOF
      ;;
    ticket|tb)
      cat >"$dest" <<EOF
#!/bin/bash
# gcs-seat-taskboard-wrapper
set -euo pipefail
BIN=\${TASKBOARD_BIN:-$bin_q}
DB=\${GCS_TASKBOARD_DB:-\${TASKBOARD_DB:-$db_q}}
if [[ ! -x "\$BIN" ]]; then
  echo "GCS_TASKBOARD_FAIL missing binary (set TASKBOARD_BIN)" >&2
  exit 127
fi
exec "\$BIN" --db "\$DB" ticket "\$@"
EOF
      ;;
    *)
      echo "install_seat_taskboard_cli: unknown wrapper kind=$kind" >&2
      return 1
      ;;
  esac
  chmod +x "$dest"
}

_gcs_abs_path() {
  python3 -c 'import os, sys; print(os.path.abspath(sys.argv[1]))' "$1"
}

_write_seat_taskboard_mcp_config() {
  # Merge stdio MCP into GROK_HOME/config.toml. Equivalent to:
  #   GROK_HOME=$gh grok mcp add taskboard -- "$bin" --db "$db" mcp
  # Cursor workspace MCP JSON is not the serve config and is not inherited.
  local dest="$1" command="$2" db="$3"
  python3 - "$dest" "$command" "$db" <<'PY'
import json
import pathlib
import re
import sys

dest = pathlib.Path(sys.argv[1])
command, db = sys.argv[2], sys.argv[3]
start = "# gcs-seat-taskboard-mcp"
end = "# gcs-seat-taskboard-mcp-end"


def q(s: str) -> str:
    return json.dumps(s)


block = (
    f"{start}\n"
    "[compat.cursor]\n"
    "mcps = false\n"
    "\n"
    "[mcp_servers.taskboard]\n"
    f"command = {q(command)}\n"
    f"args = [{q('--db')}, {q(db)}, {q('mcp')}]\n"
    f"{end}\n"
)
text = dest.read_text(encoding="utf-8") if dest.is_file() else ""
text = re.sub(
    re.escape(start) + r"\n.*?" + re.escape(end) + r"\n?",
    "",
    text,
    flags=re.S,
)
text = text.rstrip()
if text:
    text += "\n\n"
text += block
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text(text, encoding="utf-8")
PY
}

install_seat_grok_mcp() {
  # Register stdio MCP in this seat's isolated GROK_HOME/config.toml:
  #   <absolute taskboard> --db $GCS_TASKBOARD_DB mcp
  # User-scope ~/.grok/config.toml is not inherited. Do not remint serve.
  local seat="${1:-}"
  local sd gh db bin cfg
  sd="$(seat_state_dir "${seat:-floor}")"
  gh="${GROK_HOME:-$sd/grok-home}"
  db="${GCS_TASKBOARD_DB:-${TASKBOARD_DB:-$STATE_DIR/taskboard/taskboard.db}}"
  mkdir -p "$gh"
  bin="$(resolve_taskboard_bin || true)"
  if [[ -z "$bin" ]]; then
    bin="${TASKBOARD_BIN:-$ROOT/bin/taskboard}"
    echo "SEAT_GROK_MCP_SKIP seat=${seat:-?} missing host binary; config still written bin=$bin db=$db" >&2
  fi
  bin="$(_gcs_abs_path "$bin")"
  db="$(_gcs_abs_path "$db")"
  case "$bin$db" in
    *'${'*)
      echo "SEAT_GROK_MCP_FAIL seat=${seat:-?} refusing unexpanded interpolation in MCP argv" >&2
      return 1
      ;;
  esac
  if [[ "$bin" != /* || "$db" != /* ]]; then
    echo "SEAT_GROK_MCP_FAIL seat=${seat:-?} MCP argv must be absolute" >&2
    return 1
  fi
  cfg="$gh/config.toml"
  _write_seat_taskboard_mcp_config "$cfg" "$bin" "$db"
  echo "SEAT_GROK_MCP_OK seat=${seat:-?} command=$bin db=$db dest=$cfg" >&2
}

install_seat_taskboard_cli() {
  # Put taskboard / ticket / tb on the grok serve PATH (~/.grok/bin and
  # GROK_HOME/bin). Wrappers bake --db to the state-dir board so a Director
  # can exec `ticket list` without a box-local symlink. Does not remint serve.
  local seat="${1:-}"
  local sd gh db bin wrap_dir
  sd="$(seat_state_dir "${seat:-floor}")"
  gh="${GROK_HOME:-$sd/grok-home}"
  db="${GCS_TASKBOARD_DB:-${TASKBOARD_DB:-$STATE_DIR/taskboard/taskboard.db}}"
  export GCS_A2A_STATE="${GCS_A2A_STATE:-$STATE_DIR}"
  export GCS_TASKBOARD_DB="$db"
  export TASKBOARD_DB="$db"
  mkdir -p "$gh/bin" "${HOME:-$gh}/.grok/bin" "$(dirname "$db")"
  bin="$(resolve_taskboard_bin || true)"
  if [[ -z "$bin" ]]; then
    bin="${TASKBOARD_BIN:-$ROOT/bin/taskboard}"
    echo "SEAT_TASKBOARD_SKIP seat=${seat:-?} missing host binary; wrappers still installed bin=$bin db=$db" >&2
  else
    echo "SEAT_TASKBOARD_OK seat=${seat:-?} bin=$bin db=$db wrap=$gh/bin" >&2
  fi
  for wrap_dir in "$gh/bin" "${HOME:-$gh}/.grok/bin"; do
    _write_taskboard_wrapper "$wrap_dir/taskboard" taskboard "$bin" "$db"
    _write_taskboard_wrapper "$wrap_dir/ticket" ticket "$bin" "$db"
    _write_taskboard_wrapper "$wrap_dir/tb" tb "$bin" "$db"
  done
}

export_seat_serve_env() {
  local seat="$1"
  local sd
  sd="$(seat_state_dir "$seat")"
  export GCS_ROOT="$ROOT"
  export GCS_A2A_STATE="$STATE_DIR"
  export GCS_DIRECTOR_SEAT="$seat"
  export GCS_TASKBOARD_DB="${GCS_TASKBOARD_DB:-${TASKBOARD_DB:-$STATE_DIR/taskboard/taskboard.db}}"
  export TASKBOARD_DB="$GCS_TASKBOARD_DB"
  export GROK_MEMORY="${GROK_MEMORY:-1}"
  export GROK_HOME="${GROK_HOME:-$sd/grok-home}"
  mkdir -p "$GROK_HOME"
  install_seat_identity "$seat"
  export PATH="${GROK_HOME}/bin:${HOME}/.grok/bin:${PATH:-}"
}

install_seat_identity() {
  local seat="$1"
  local sd src alias
  sd="$(seat_state_dir "$seat")"
  src="$ROOT/docs/studio/directors/souls/$seat"
  alias="$ROOT/docs/studio/directors/souls/$(python3 "$LIB_PY" canonical "$seat" 2>/dev/null || echo "$seat")"
  mkdir -p "$sd/grok-home"
  install_seat_grok_auth "$seat"
  install_seat_taskboard_cli "$seat"
  install_seat_grok_mcp "$seat"
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
  prompt_file="$(gcs_resolve_prompt_file "$seat" || true)"
  profile="$sd/agent-profile.md"
  if [[ -z "$prompt_file" || ! -f "$prompt_file" ]]; then
    echo "missing prompt: $PROMPTS_DIR/${stem}_director_prompt.txt" >&2
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
