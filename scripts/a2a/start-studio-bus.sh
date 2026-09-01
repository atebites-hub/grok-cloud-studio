#!/usr/bin/env bash
# Start/stop/status for local Grok Cloud Studio A2A hub + leftover dispatch +
# fleet-shepherd. bot-bridge is opt-in: GCS_BOT_BRIDGE=1 (Bot seats stay
# standby otherwise). Seat ACP daemons are opt-in:
# GCS_START_SEAT_DAEMONS=1 or `start --daemons`.
#
# GROW: one `grok agent serve` per opted-in seat plus seat-wake-loop.sh →
# wake-daemon.py (inbox.jsonl → ACP session/prompt inside that serve pid).
# Opt-in Grok Build mind (GCS_MIND_SEATS, default empty, example floor,ops):
# seat-mind-loop.sh → mind.py (inbox → grok --resume pinned session --prompt-file;
# never bare -p). Mind is
# the GROW path when opted in; ACP wake is skipped for those seats unless
# GCS_MIND_PLUS_ACP_WAKE=1 (in addition). Do not kill existing serve.
# Leftover ACP GROW is session/prompt inside serve, not this grok --resume path.
# start recycles leftover dispatch only when .a2a-state/dispatch.mind-seats
# differs from current GCS_MIND_SEATS (env / studio.env). Matching keeps
# STUDIO_BUS_DISPATCH_ALREADY. Recycle does not kill hub, leftover
# bot-bridge, fleet-shepherd, seat minds, host ticker, or grok agent serve.
# start / recover.sh do not spawn bot-bridge unless GCS_BOT_BRIDGE=1.
# Host ticker enqueues ACP_PING STATUS/CONTINUE keep-alives (work turns).
# Ticker also starts when GCS_MIND_SEATS is set (mind stay-up, no --daemons).
# Agent Kanban / `ak` was removed. Board is tcarac/taskboard (ticket CLI + HTTP /mcp).
# Host board after a wipe: scripts/studio/taskboard/start-taskboard.sh start
# and mcp-http.sh start. Full Palemon floor recreate: docs/studio/WIPE.md.
# start (no --daemons) never auto-spawns a 13-seat grok serve floor on a ~15GB box.
#
# Usage:
#   start-studio-bus.sh          # start hub+dispatch+shepherd (idempotent)
#                                # bot-bridge only if GCS_BOT_BRIDGE=1
#   start-studio-bus.sh start
#   start-studio-bus.sh start --daemons
#   start-studio-bus.sh stop
#   start-studio-bus.sh stop --daemons
#   start-studio-bus.sh status
# Local studio only. Pid/logs under .a2a-state/.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${GCS_ROOT:-$SCRIPT_DIR/../..}" && pwd)"
export GCS_ROOT="$ROOT"
STATE_DIR="${GCS_A2A_STATE:-$ROOT/.a2a-state}"
HUB_PY="$SCRIPT_DIR/hub.py"
DISPATCH_PY="$SCRIPT_DIR/dispatch.py"
BOT_BRIDGE_PY="$SCRIPT_DIR/bot-bridge.py"
HUB_PID_FILE="$STATE_DIR/hub.pid"
DISPATCH_PID_FILE="$STATE_DIR/dispatch.pid"
DISPATCH_MIND_SEATS_FILE="$STATE_DIR/dispatch.mind-seats"
BOT_BRIDGE_PID_FILE="$STATE_DIR/bot-bridge.pid"
HUB_LOG="$STATE_DIR/hub.log"
DISPATCH_LOG="$STATE_DIR/dispatch.log"
BOT_BRIDGE_LOG="$STATE_DIR/bot-bridge.log"
SHEPHERD_PY="$ROOT/scripts/directors/fleet-shepherd.py"
SHEPHERD_PID_FILE="$STATE_DIR/fleet-shepherd.pid"
SHEPHERD_LOG="$STATE_DIR/fleet-shepherd.log"
START_DAEMON="$ROOT/scripts/directors/start-seat-daemon.sh"
STOP_DAEMON="$ROOT/scripts/directors/stop-seat-daemon.sh"
STATUS_DAEMON="$ROOT/scripts/directors/status-seat-daemon.sh"
WAKE_LOOP="$ROOT/scripts/directors/seat-wake-loop.sh"
MIND_LOOP="$ROOT/scripts/directors/seat-mind-loop.sh"
TICKER_PY="$SCRIPT_DIR/host-ticker.py"
TICKER_PID_FILE="$STATE_DIR/host-ticker.pid"
TICKER_LOG="$STATE_DIR/host-ticker.log"
DAEMONS_FLAG="$STATE_DIR/daemons.enabled"
LIB_PY="$SCRIPT_DIR/lib.py"
# Comma-separated seats to keep as ACP daemons + GROW wake.
# Default floor+ops (studio-ops on product floors) — full registry OOMs ~15GB VMs.
DEFAULT_ACP_SEATS="floor,studio-ops"

mkdir -p "$STATE_DIR"

# Crash-safe overrides (seat cap, GROK_USE_LEADER). Not committed.
if [[ -f "$STATE_DIR/studio.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$STATE_DIR/studio.env"
  set +a
fi

usage() {
  cat <<'EOF'
Usage: start-studio-bus.sh [start|stop|status] [--daemons]

start            hub + dispatch + fleet-shepherd (idempotent; recycle leftover
                 dispatch only when dispatch.mind-seats != current GCS_MIND_SEATS).
                 bot-bridge stays off unless GCS_BOT_BRIDGE=1 (Bot seats standby).
start --daemons  also start per-seat ACP daemons + GROW wake loops + host ticker
                 (ticker also starts when GCS_MIND_SEATS is set, no --daemons)
stop             stop hub/dispatch/shepherd/wake/mind/ticker (leaves seat serve)
stop --daemons   also stop seat ACP daemons and clear daemons.enabled
status           print bus + optional daemon / wake / mind / ticker flag

GROW mail path: seat-wake-loop.sh → wake-daemon.py → seat-prompt-acp.sh
(session/prompt inside grok agent serve). Dispatch does not own GROW inboxes.
Opt-in mind (GCS_MIND_SEATS, example floor,ops): seat-mind-loop.sh → mind.py.
Mind replaces ACP wake for those seats (set GCS_MIND_PLUS_ACP_WAKE=1 to run
ACP wake in addition). Do not kill existing grok agent serve.
Host ticker enqueues ACP_PING STATUS/CONTINUE work turns (not PONG, not LAUNCH).
Mind seats get that mailbox keep-alive even when --daemons is off.
Board is tcarac/taskboard. Agent Kanban was removed; do not reconnect `ak`.

Opt-in without the flag: GCS_START_SEAT_DAEMONS=1
Do not spawn a grok agent process per seat by surprise; daemons are explicit.
See docs/ARCHITECTURE.md, docs/A2A.md, docs/studio/MIND.md, and docs/studio/WIPE.md.
Host board: scripts/studio/taskboard/start-taskboard.sh (UI :3010) + mcp-http.sh (:3011).
EOF
}

pid_alive() {
  local pid="${1:-}" state
  [[ -n "$pid" ]] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  state=$(ps -p "$pid" -o state= 2>/dev/null | tr -d '[:space:]')
  [[ "$state" == Z* ]] && return 1
  return 0
}

read_pid() {
  local f="$1"
  if [[ -f "$f" ]]; then
    tr -d '[:space:]' < "$f" || true
  fi
}

acp_seats() {
  local raw="${GCS_ACP_SEATS:-$DEFAULT_ACP_SEATS}"
  local s known
  known="$(python3 "$LIB_PY" launch-seats 2>/dev/null || true)"
  IFS=',' read -r -a parts <<<"$raw"
  for s in "${parts[@]}"; do
    s="$(echo "$s" | tr -d '[:space:]')"
    [[ -n "$s" ]] || continue
    if printf '%s\n' "$known" | grep -qx "$s"; then
      echo "$s"
    elif [[ "$s" == "studio-ops" ]] && printf '%s\n' "$known" | grep -qx "ops"; then
      echo "ops"
    fi
  done
}

wake_seats() {
  local raw="${GCS_WAKE_SEATS:-${GCS_GROW_SEATS:-}}"
  if [[ -n "$raw" ]]; then
    local s known
    known="$(python3 "$LIB_PY" launch-seats 2>/dev/null || true)"
    IFS=',' read -r -a parts <<<"$raw"
    for s in "${parts[@]}"; do
      s="$(echo "$s" | tr -d '[:space:]')"
      [[ -n "$s" ]] || continue
      if printf '%s\n' "$known" | grep -qx "$s"; then
        echo "$s"
      elif [[ "$s" == "studio-ops" ]] && printf '%s\n' "$known" | grep -qx "ops"; then
        echo "ops"
      fi
    done
    return 0
  fi
  acp_seats
}

mind_seats() {
  python3 "$LIB_PY" mind-seats 2>/dev/null || true
}

# Sorted comma set so floor,qa-a and qa-a,floor compare equal. Empty → "".
comma_join_sorted_seats() {
  awk 'NF { gsub(/^[ \t]+|[ \t]+$/, ""); if ($0 != "") print }' | sort -u | awk 'BEGIN { ORS="" } { if (n++) printf ","; printf "%s", $0 }'
}

canonical_mind_seats() {
  mind_seats | comma_join_sorted_seats
}

persisted_mind_seats() {
  local f="$DISPATCH_MIND_SEATS_FILE"
  [[ -f "$f" ]] || { printf '%s' ""; return 0; }
  tr ',' '\n' < "$f" | comma_join_sorted_seats
}

write_dispatch_mind_seats() {
  canonical_mind_seats > "$DISPATCH_MIND_SEATS_FILE"
}

# Recycle leftover dispatch only when its persisted GCS_MIND_SEATS set differs
# from current env / studio.env. Missing persist file is the empty set (pre-feature
# leftovers). Do not touch hub, leftover bot-bridge, shepherd, minds, ticker,
# or serve. Do not start bot-bridge unless GCS_BOT_BRIDGE=1.
recycle_dispatch_for_mind_seats() {
  local disp_pid="$1"
  local want have
  want="$(canonical_mind_seats)"
  have="$(persisted_mind_seats)"
  if [[ "$want" == "$have" ]]; then
    return 1
  fi
  echo "STUDIO_BUS_DISPATCH_RECYCLE reason=mind-seats-changed pid=$disp_pid was=${have:-none} now=${want:-none}"
  stop_pid_file "$DISPATCH_PID_FILE" "DISPATCH"
  rm -f "$DISPATCH_MIND_SEATS_FILE"
  return 0
}

is_mind_seat() {
  local seat="$1" s
  while read -r s; do
    [[ -z "$s" ]] && continue
    [[ "$s" == "$seat" ]] && return 0
  done < <(mind_seats)
  return 1
}

want_daemons() {
  [[ "${WITH_DAEMONS:-0}" == "1" ]] && return 0
  [[ "${GCS_START_SEAT_DAEMONS:-0}" == "1" ]] && return 0
  [[ -f "$DAEMONS_FLAG" ]] && return 0
  return 1
}

want_bot_bridge() {
  [[ "${GCS_BOT_BRIDGE:-0}" == "1" ]] && return 0
  return 1
}

stop_pid_file() {
  local pid_file="$1" label="$2"
  local pid
  pid="$(read_pid "$pid_file")"
  if pid_alive "$pid"; then
    kill "$pid" 2>/dev/null || true
    for _ in 1 2 3 4 5; do
      pid_alive "$pid" || break
      sleep 0.2
    done
    if pid_alive "$pid"; then
      kill -9 "$pid" 2>/dev/null || true
    fi
    echo "STUDIO_BUS_${label}_STOP pid=$pid"
  else
    echo "STUDIO_BUS_${label}_NOT_RUNNING"
  fi
  rm -f "$pid_file"
}

start_wake_daemons() {
  local seat pid pidfile
  if [[ ! -f "$WAKE_LOOP" ]]; then
    echo "STUDIO_BUS_WAKE_SKIP missing $WAKE_LOOP" >&2
    return 0
  fi
  while read -r seat; do
    [[ -z "$seat" ]] && continue
    if is_mind_seat "$seat" && [[ "${GCS_MIND_PLUS_ACP_WAKE:-0}" != "1" ]]; then
      echo "STUDIO_BUS_WAKE_SKIP seat=$seat reason=mind-owns-inbox (GCS_MIND_PLUS_ACP_WAKE=1 to also start ACP wake)"
      continue
    fi
    mkdir -p "$STATE_DIR/$seat"
    pidfile="$STATE_DIR/$seat/wake.pid"
    pid="$(read_pid "$pidfile")"
    if pid_alive "$pid"; then
      echo "STUDIO_BUS_WAKE_ALREADY seat=$seat pid=$pid"
      continue
    fi
    rm -f "$pidfile"
    nohup bash "$WAKE_LOOP" "$seat" >>"$STATE_DIR/$seat/wake.log" 2>&1 &
    echo $! >"$pidfile"
    echo "STUDIO_BUS_WAKE_START seat=$seat pid=$(read_pid "$pidfile") log=$STATE_DIR/$seat/wake.log mode=acp-serve"
  done < <(wake_seats)
}

start_mind_daemons() {
  local seat pid pidfile
  if [[ ! -f "$MIND_LOOP" ]]; then
    echo "STUDIO_BUS_MIND_SKIP missing $MIND_LOOP" >&2
    return 0
  fi
  while read -r seat; do
    [[ -z "$seat" ]] && continue
    mkdir -p "$STATE_DIR/$seat/mind"
    pidfile="$STATE_DIR/$seat/mind/pid"
    pid="$(read_pid "$pidfile")"
    if pid_alive "$pid"; then
      echo "STUDIO_BUS_MIND_ALREADY seat=$seat pid=$pid"
      continue
    fi
    rm -f "$pidfile"
    nohup bash "$MIND_LOOP" "$seat" >>"$STATE_DIR/$seat/mind/mind.log" 2>&1 &
    echo $! >"$pidfile"
    echo "STUDIO_BUS_MIND_START seat=$seat pid=$(read_pid "$pidfile") log=$STATE_DIR/$seat/mind/mind.log mode=grok-build-mind"
  done < <(mind_seats)
}

stop_mind_daemons() {
  local seat pid pidfile
  while read -r seat; do
    [[ -z "$seat" ]] && continue
    pidfile="$STATE_DIR/$seat/mind/pid"
    pid="$(read_pid "$pidfile")"
    if pid_alive "$pid"; then
      kill "$pid" 2>/dev/null || true
      for _ in 1 2 3 4 5; do
        pid_alive "$pid" || break
        sleep 0.2
      done
      if pid_alive "$pid"; then
        kill -9 "$pid" 2>/dev/null || true
      fi
      echo "STUDIO_BUS_MIND_STOP seat=$seat pid=$pid"
    fi
    rm -f "$pidfile"
  done < <(mind_seats)
}

status_mind_daemons() {
  local seat up=0 down=0 pid
  while read -r seat; do
    [[ -z "$seat" ]] && continue
    pid="$(read_pid "$STATE_DIR/$seat/mind/pid")"
    if pid_alive "$pid"; then
      echo "STUDIO_BUS_MIND_STATUS seat=$seat up pid=$pid"
      up=$((up + 1))
    else
      echo "STUDIO_BUS_MIND_STATUS seat=$seat down pid=${pid:-none}"
      down=$((down + 1))
    fi
  done < <(mind_seats)
  echo "STUDIO_BUS_MIND_SUMMARY up=$up down=$down"
}

stop_wake_daemons() {
  local seat pid pidfile
  while read -r seat; do
    [[ -z "$seat" ]] && continue
    pidfile="$STATE_DIR/$seat/wake.pid"
    pid="$(read_pid "$pidfile")"
    if pid_alive "$pid"; then
      kill "$pid" 2>/dev/null || true
      for _ in 1 2 3 4 5; do
        pid_alive "$pid" || break
        sleep 0.2
      done
      if pid_alive "$pid"; then
        kill -9 "$pid" 2>/dev/null || true
      fi
      echo "STUDIO_BUS_WAKE_STOP seat=$seat pid=$pid"
    fi
    rm -f "$pidfile"
  done < <(wake_seats)
}

status_wake_daemons() {
  local seat up=0 down=0 pid
  while read -r seat; do
    [[ -z "$seat" ]] && continue
    pid="$(read_pid "$STATE_DIR/$seat/wake.pid")"
    if pid_alive "$pid"; then
      echo "STUDIO_BUS_WAKE_STATUS seat=$seat up pid=$pid"
      up=$((up + 1))
    else
      echo "STUDIO_BUS_WAKE_STATUS seat=$seat down pid=${pid:-none}"
      down=$((down + 1))
    fi
  done < <(wake_seats)
  echo "STUDIO_BUS_WAKE_SUMMARY up=$up down=$down"
}

start_host_ticker() {
  local pid
  if [[ ! -f "$TICKER_PY" ]]; then
    echo "STUDIO_BUS_TICKER_SKIP missing $TICKER_PY"
    return 0
  fi
  pid="$(read_pid "$TICKER_PID_FILE")"
  if pid_alive "$pid"; then
    echo "STUDIO_BUS_TICKER_ALREADY pid=$pid"
    return 0
  fi
  rm -f "$TICKER_PID_FILE"
  nohup python3 "$TICKER_PY" "$@" >>"$TICKER_LOG" 2>&1 &
  echo $! >"$TICKER_PID_FILE"
  echo "STUDIO_BUS_TICKER_START pid=$(read_pid "$TICKER_PID_FILE") log=$TICKER_LOG"
}

stop_host_ticker() {
  local pid
  pid="$(read_pid "$TICKER_PID_FILE")"
  if pid_alive "$pid"; then
    kill "$pid" 2>/dev/null || true
    for _ in 1 2 3 4 5; do
      pid_alive "$pid" || break
      sleep 0.2
    done
    if pid_alive "$pid"; then
      kill -9 "$pid" 2>/dev/null || true
    fi
    echo "STUDIO_BUS_TICKER_STOP pid=$pid"
  fi
  rm -f "$TICKER_PID_FILE"
}

start_seat_daemons() {
  local seat
  if [[ "${GROK_USE_LEADER:-0}" == "1" || "${GROK_USE_LEADER:-}" == "true" ]]; then
    if [[ -f "$ROOT/scripts/directors/start-grok-leader.sh" ]]; then
      bash "$ROOT/scripts/directors/start-grok-leader.sh" || echo "STUDIO_BUS_LEADER_FAIL" >&2
    fi
  fi
  if [[ ! -f "$START_DAEMON" ]]; then
    echo "STUDIO_BUS_DAEMONS_SKIP missing $START_DAEMON"
  else
    touch "$DAEMONS_FLAG"
    while read -r seat; do
      [[ -z "$seat" ]] && continue
      if bash "$START_DAEMON" "$seat"; then
        echo "STUDIO_BUS_DAEMON_OK seat=$seat mode=acp-serve"
      else
        echo "STUDIO_BUS_DAEMON_FAIL seat=$seat" >&2
      fi
    done < <(acp_seats)
  fi
  start_wake_daemons
  start_host_ticker
}

stop_seat_daemons() {
  local seat
  stop_wake_daemons
  stop_host_ticker
  if [[ ! -f "$STOP_DAEMON" ]]; then
    rm -f "$DAEMONS_FLAG"
    return 0
  fi
  while read -r seat; do
    [[ -z "$seat" ]] && continue
    bash "$STOP_DAEMON" "$seat" || true
  done < <(acp_seats)
  rm -f "$DAEMONS_FLAG"
}

status_seat_daemons() {
  status_wake_daemons || true
  local tpid tstate="down"
  tpid="$(read_pid "$TICKER_PID_FILE")"
  if pid_alive "$tpid"; then tstate="up"; fi
  echo "STUDIO_BUS_TICKER_STATUS $tstate pid=${tpid:-none}"
  local seat up=0 down=0
  if [[ ! -f "$STATUS_DAEMON" ]]; then
    echo "STUDIO_BUS_DAEMONS_STATUS unavailable"
    return 0
  fi
  while read -r seat; do
    [[ -z "$seat" ]] && continue
    if bash "$STATUS_DAEMON" "$seat"; then
      up=$((up + 1))
    else
      down=$((down + 1))
    fi
  done < <(acp_seats)
  echo "STUDIO_BUS_DAEMONS_SUMMARY up=$up down=$down"
}

WITH_DAEMONS=0
cmd="${1:-start}"
shift || true
case "$cmd" in
  -h|--help)
    usage
    exit 0
    ;;
  --daemons)
    WITH_DAEMONS=1
    cmd="start"
    ;;
  start|stop|status) ;;
  *)
    echo "error: unknown command $cmd" >&2
    usage >&2
    exit 2
    ;;
esac
for arg in "$@"; do
  case "$arg" in
    --daemons) WITH_DAEMONS=1 ;;
    *)
      echo "error: unknown option $arg" >&2
      usage >&2
      exit 2
      ;;
  esac
done

case "$cmd" in
  start)
    hub_pid="$(read_pid "$HUB_PID_FILE")"
    disp_pid="$(read_pid "$DISPATCH_PID_FILE")"
    hub_running=0
    disp_running=0
    if pid_alive "$hub_pid"; then hub_running=1; fi
    if pid_alive "$disp_pid"; then disp_running=1; fi

    export GCS_ROOT="$ROOT"
    export GCS_A2A_STATE="$STATE_DIR"

    if [[ "$hub_running" != "1" ]]; then
      rm -f "$HUB_PID_FILE"
      nohup python3 "$HUB_PY" >>"$HUB_LOG" 2>&1 &
      echo $! >"$HUB_PID_FILE"
      hub_pid="$(read_pid "$HUB_PID_FILE")"
      sleep 0.3
      if ! pid_alive "$hub_pid"; then
        echo "STUDIO_BUS_FAIL hub did not stay up; see $HUB_LOG" >&2
        exit 1
      fi
      echo "STUDIO_BUS_HUB_START pid=$hub_pid log=$HUB_LOG"
    else
      echo "STUDIO_BUS_HUB_ALREADY pid=$hub_pid"
    fi

    if [[ "$disp_running" == "1" ]]; then
      if recycle_dispatch_for_mind_seats "$disp_pid"; then
        disp_running=0
        disp_pid=""
      fi
    fi

    if [[ "$disp_running" != "1" ]]; then
      rm -f "$DISPATCH_PID_FILE"
      nohup python3 "$DISPATCH_PY" >>"$DISPATCH_LOG" 2>&1 &
      echo $! >"$DISPATCH_PID_FILE"
      disp_pid="$(read_pid "$DISPATCH_PID_FILE")"
      sleep 0.3
      if ! pid_alive "$disp_pid"; then
        echo "STUDIO_BUS_FAIL dispatch did not stay up; see $DISPATCH_LOG" >&2
        exit 1
      fi
      write_dispatch_mind_seats
      echo "STUDIO_BUS_DISPATCH_START pid=$disp_pid log=$DISPATCH_LOG"
    else
      echo "STUDIO_BUS_DISPATCH_ALREADY pid=$disp_pid"
    fi

    shep_pid="$(read_pid "$SHEPHERD_PID_FILE")"
    if pid_alive "$shep_pid"; then
      echo "STUDIO_BUS_SHEPHERD_ALREADY pid=$shep_pid"
    else
      rm -f "$SHEPHERD_PID_FILE"
      nohup python3 "$SHEPHERD_PY" >>"$SHEPHERD_LOG" 2>&1 &
      echo $! >"$SHEPHERD_PID_FILE"
      shep_pid="$(read_pid "$SHEPHERD_PID_FILE")"
      sleep 0.2
      if ! pid_alive "$shep_pid"; then
        echo "STUDIO_BUS_FAIL shepherd did not stay up; see $SHEPHERD_LOG" >&2
      else
        echo "STUDIO_BUS_SHEPHERD_START pid=$shep_pid log=$SHEPHERD_LOG"
      fi
    fi

    bridge_pid="$(read_pid "$BOT_BRIDGE_PID_FILE")"
    if pid_alive "$bridge_pid"; then
      echo "STUDIO_BUS_BOT_BRIDGE_ALREADY pid=$bridge_pid"
    elif want_bot_bridge; then
      rm -f "$BOT_BRIDGE_PID_FILE"
      if [[ -f "$BOT_BRIDGE_PY" ]]; then
        nohup python3 "$BOT_BRIDGE_PY" >>"$BOT_BRIDGE_LOG" 2>&1 &
        echo $! >"$BOT_BRIDGE_PID_FILE"
        bridge_pid="$(read_pid "$BOT_BRIDGE_PID_FILE")"
        sleep 0.2
        if ! pid_alive "$bridge_pid"; then
          echo "STUDIO_BUS_FAIL bot-bridge did not stay up; see $BOT_BRIDGE_LOG" >&2
        else
          echo "STUDIO_BUS_BOT_BRIDGE_START pid=$bridge_pid log=$BOT_BRIDGE_LOG"
        fi
      else
        echo "STUDIO_BUS_BOT_BRIDGE_SKIP missing $BOT_BRIDGE_PY"
        bridge_pid=""
      fi
    else
      rm -f "$BOT_BRIDGE_PID_FILE"
      bridge_pid=""
      echo "STUDIO_BUS_BOT_BRIDGE_SKIP reason=standby (set GCS_BOT_BRIDGE=1 to start)"
    fi

    start_mind_daemons
    if want_daemons; then
      start_seat_daemons
    else
      echo "STUDIO_BUS_DAEMONS_SKIP (pass --daemons or GCS_START_SEAT_DAEMONS=1)"
      if [[ -n "$(canonical_mind_seats)" ]]; then
        start_host_ticker --seats "$(canonical_mind_seats)"
      fi
    fi

    echo "STUDIO_BUS_READY hub_pid=$hub_pid dispatch_pid=$disp_pid shepherd_pid=$shep_pid bot_bridge_pid=${bridge_pid:-none} state=$STATE_DIR"
    ;;

  stop)
    stop_wake_daemons
    stop_mind_daemons
    stop_host_ticker
    hub_pid="$(read_pid "$HUB_PID_FILE")"
    disp_pid="$(read_pid "$DISPATCH_PID_FILE")"
    shep_pid="$(read_pid "$SHEPHERD_PID_FILE")"
    bridge_pid="$(read_pid "$BOT_BRIDGE_PID_FILE")"
    if pid_alive "$bridge_pid"; then
      kill "$bridge_pid" 2>/dev/null || true
      for _ in 1 2 3 4 5; do
        pid_alive "$bridge_pid" || break
        sleep 0.2
      done
      if pid_alive "$bridge_pid"; then
        kill -9 "$bridge_pid" 2>/dev/null || true
      fi
      echo "STUDIO_BUS_BOT_BRIDGE_STOP pid=$bridge_pid"
    else
      echo "STUDIO_BUS_BOT_BRIDGE_NOT_RUNNING"
    fi
    rm -f "$BOT_BRIDGE_PID_FILE"
    if pid_alive "$shep_pid"; then
      kill "$shep_pid" 2>/dev/null || true
      for _ in 1 2 3 4 5; do
        pid_alive "$shep_pid" || break
        sleep 0.2
      done
      if pid_alive "$shep_pid"; then
        kill -9 "$shep_pid" 2>/dev/null || true
      fi
      echo "STUDIO_BUS_SHEPHERD_STOP pid=$shep_pid"
    else
      echo "STUDIO_BUS_SHEPHERD_NOT_RUNNING"
    fi
    rm -f "$SHEPHERD_PID_FILE"
    if pid_alive "$disp_pid"; then
      kill "$disp_pid" 2>/dev/null || true
      for _ in 1 2 3 4 5; do
        pid_alive "$disp_pid" || break
        sleep 0.2
      done
      if pid_alive "$disp_pid"; then
        kill -9 "$disp_pid" 2>/dev/null || true
      fi
      echo "STUDIO_BUS_DISPATCH_STOP pid=$disp_pid"
    else
      echo "STUDIO_BUS_DISPATCH_NOT_RUNNING"
    fi
    rm -f "$DISPATCH_PID_FILE" "$DISPATCH_MIND_SEATS_FILE"

    if pid_alive "$hub_pid"; then
      kill "$hub_pid" 2>/dev/null || true
      for _ in 1 2 3 4 5; do
        pid_alive "$hub_pid" || break
        sleep 0.2
      done
      if pid_alive "$hub_pid"; then
        kill -9 "$hub_pid" 2>/dev/null || true
      fi
      echo "STUDIO_BUS_HUB_STOP pid=$hub_pid"
    else
      echo "STUDIO_BUS_HUB_NOT_RUNNING"
    fi
    rm -f "$HUB_PID_FILE"
    # GROW wake loops + ticker stop with the bus. Leave grok agent serve running
    # unless stop --daemons or GCS_ACP_STOP_WITH_BUS=1 (serve is the long-lived seat).
    if [[ "$WITH_DAEMONS" == "1" || "${GCS_ACP_STOP_WITH_BUS:-0}" == "1" ]]; then
      if [[ -f "$STOP_DAEMON" ]]; then
        while read -r seat; do
          [[ -z "$seat" ]] && continue
          bash "$STOP_DAEMON" "$seat" || true
        done < <(acp_seats)
      fi
      rm -f "$DAEMONS_FLAG"
    else
      echo "STUDIO_BUS_DAEMONS_LEFT_RUNNING (pass stop --daemons to stop)"
    fi
    echo "STUDIO_BUS_STOPPED"
    ;;

  status)
    hub_pid="$(read_pid "$HUB_PID_FILE")"
    disp_pid="$(read_pid "$DISPATCH_PID_FILE")"
    hub_state="down"
    disp_state="down"
    if pid_alive "$hub_pid"; then hub_state="up"; fi
    if pid_alive "$disp_pid"; then disp_state="up"; fi
    shep_pid="$(read_pid "$SHEPHERD_PID_FILE")"
    shep_state="down"
    if pid_alive "$shep_pid"; then shep_state="up"; fi
    bridge_pid="$(read_pid "$BOT_BRIDGE_PID_FILE")"
    bridge_state="down"
    if pid_alive "$bridge_pid"; then bridge_state="up"; fi
    daemon_flag="off"
    [[ -f "$DAEMONS_FLAG" ]] && daemon_flag="on"
    echo "STUDIO_BUS_STATUS hub=$hub_state pid=${hub_pid:-none} dispatch=$disp_state pid=${disp_pid:-none} shepherd=$shep_state pid=${shep_pid:-none} bot_bridge=$bridge_state pid=${bridge_pid:-none} daemons=$daemon_flag state=$STATE_DIR"
    status_mind_daemons || true
    if [[ "$daemon_flag" == "on" ]] || want_daemons; then
      status_seat_daemons || true
    fi
    if [[ "$hub_state" == "up" && "$disp_state" == "up" && "$shep_state" == "up" ]]; then
      exit 0
    fi
    exit 1
    ;;
esac
