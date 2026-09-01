#!/usr/bin/env bash
# Bind a Grok Bot orchestrator into the local A2A bus (idempotent).
# Never prints API keys or the full agent id. Local studio only.
#
# Env:
#   GCS_BOT_AGENT_ID     required for bind (Grok Bot agent id)
#   GCS_BOT_SEAT         default orchestrator (docs/a2a) or donald (docs/studio/a2a)
#   GCS_BOT_AGENT_NAME   optional display name for the Agent Card
#   GCS_ROOT             repo root (default: this script's ../..)
#   GCS_A2A_STATE        local state dir (gitignored)
#   GCS_BOT_BIND_OPTIONAL=1  --check warns instead of FAIL on placeholder (CI clones)
#
# Usage:
#   scripts/a2a/bind-bot-agent.sh           # bind
#   scripts/a2a/bind-bot-agent.sh --check   # doctor
set -euo pipefail

PLACEHOLDER="REPLACE_WITH_YOUR_GROK_BOT_AGENT_ID"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${GCS_ROOT:-$SCRIPT_DIR/../..}" && pwd)"
export GCS_ROOT="$ROOT"

MODE="bind"
for arg in "$@"; do
  case "$arg" in
    --check|-c) MODE="check" ;;
    -h|--help)
      cat <<'EOF'
Usage: bind-bot-agent.sh [--check]

Bind GCS_BOT_AGENT_ID into docs/a2a/bot-agents.json (or docs/studio/a2a/),
registry skipSeats, a hub Agent Card, and gitignored .a2a-state/bot-bind.json.

Bot seats are NOT ACP inject targets. Standing Bot routines poll
.a2a-state/<seat>/bot-wake.txt and bot-wake.jsonl.

--check fails if any bot seat agentId is empty or REPLACE_WITH_YOUR_GROK_BOT_AGENT_ID
unless GCS_BOT_BIND_OPTIONAL=1 (CI clone checks).
EOF
      exit 0
      ;;
    *)
      echo "error: unknown argument $arg (try --help)" >&2
      exit 2
      ;;
  esac
done

if [[ -d "$ROOT/docs/studio/a2a" ]]; then
  A2A_REL="docs/studio/a2a"
  DEFAULT_SEAT="donald"
elif [[ -d "$ROOT/docs/a2a" ]]; then
  A2A_REL="docs/a2a"
  DEFAULT_SEAT="orchestrator"
else
  echo "ERR bot-bind missing A2A docs (docs/a2a or docs/studio/a2a)" >&2
  exit 1
fi

SEAT="$(echo "${GCS_BOT_SEAT:-$DEFAULT_SEAT}" | tr '[:upper:]' '[:lower:]' | tr '_' '-')"
AGENT_ID="${GCS_BOT_AGENT_ID:-}"
AGENT_NAME="${GCS_BOT_AGENT_NAME:-}"
STATE_DIR="${GCS_A2A_STATE:-$ROOT/.a2a-state}"
PORT="${GCS_A2A_PORT:-8732}"
OPTIONAL="${GCS_BOT_BIND_OPTIONAL:-0}"

if [[ ! "$SEAT" =~ ^[a-z][a-z0-9-]*$ ]]; then
  echo "ERR bot-bind invalid seat name" >&2
  exit 2
fi

if [[ "$MODE" == "bind" && -z "$AGENT_ID" ]]; then
  echo "ERR bot-bind GCS_BOT_AGENT_ID is required. Set it and re-run install or this script." >&2
  exit 2
fi

if [[ "$MODE" == "bind" && "$AGENT_ID" == "$PLACEHOLDER" ]]; then
  echo "ERR bot-bind agentId is still the placeholder. Set GCS_BOT_AGENT_ID to your Grok Bot id." >&2
  exit 2
fi

python3 - "$MODE" "$ROOT" "$A2A_REL" "$SEAT" "$AGENT_ID" "$AGENT_NAME" "$PLACEHOLDER" "$STATE_DIR" "$PORT" "$OPTIONAL" <<'PY'
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

mode, root_s, a2a_rel, seat, agent_id, agent_name, placeholder, state_s, port_s, optional_s = sys.argv[1:11]
root = Path(root_s)
a2a = root / a2a_rel
state = Path(state_s)
optional = optional_s == "1"
bots_path = a2a / "bot-agents.json"
registry_path = a2a / "registry.json"
cards_dir = a2a / "cards"
card_rel = f"{a2a_rel}/cards/{seat}.json"
hub = f"http://127.0.0.1:{port_s}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.is_file():
        return dict(default)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(default)
    return data if isinstance(data, dict) else dict(default)


def _dump(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _unbound(value: Any) -> bool:
    text = str(value or "").strip()
    return (not text) or text == placeholder


def _provider() -> dict[str, Any]:
    if cards_dir.is_dir():
        for path in sorted(cards_dir.glob("*.json")):
            try:
                card = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(card, dict) and isinstance(card.get("provider"), dict):
                return card["provider"]
    return {
        "organization": "Grok Cloud Studio",
        "url": "https://github.com/atebites-hub/grok-cloud-studio",
    }


def _display_name() -> str:
    if agent_name.strip():
        return agent_name.strip()
    if seat == "donald":
        return "Donald"
    return seat.replace("-", " ").title()


def _ensure_skip(registry: dict[str, Any], names: list[str]) -> None:
    raw = registry.get("skipSeats")
    skip: list[str] = [str(s) for s in raw] if isinstance(raw, list) else []
    for name in names:
        if name and name not in skip:
            skip.append(name)
    registry["skipSeats"] = skip


def _check() -> int:
    fail = 0
    warns = 0
    if not bots_path.is_file():
        print(f"ERR bot-bind missing {a2a_rel}/bot-agents.json", file=sys.stderr)
        return 1
    bots = _load(bots_path, {})
    seats = bots.get("seats") if isinstance(bots.get("seats"), dict) else {}
    if not seats:
        print("ERR bot-bind bot-agents.json has no seats", file=sys.stderr)
        return 1
    registry = _load(registry_path, {"skipSeats": [], "seats": {}})
    skip = {str(s) for s in (registry.get("skipSeats") or [])} if isinstance(registry.get("skipSeats"), list) else set()
    reg_seats = registry.get("seats") if isinstance(registry.get("seats"), dict) else {}
    for name, meta in seats.items():
        if not isinstance(meta, dict):
            print(f"ERR bot-bind seat={name} reason=invalid", file=sys.stderr)
            fail += 1
            continue
        if _unbound(meta.get("agentId")):
            msg = f"bot-bind seat={name} reason=unbound (empty or placeholder agentId)"
            if optional:
                print(f"WARN {msg}. Set GCS_BOT_AGENT_ID and re-run install or scripts/a2a/bind-bot-agent.sh", file=sys.stderr)
                warns += 1
            else:
                print(f"ERR {msg}", file=sys.stderr)
                fail += 1
        if name not in skip:
            print(f"ERR bot-bind seat={name} reason=not-in-skipSeats", file=sys.stderr)
            fail += 1
        card_path = cards_dir / f"{name}.json"
        if not card_path.is_file():
            print(f"ERR bot-bind seat={name} reason=missing-card", file=sys.stderr)
            fail += 1
        if name not in reg_seats:
            print(f"ERR bot-bind seat={name} reason=missing-registry-seat", file=sys.stderr)
            fail += 1
    if fail:
        return 1
    if warns:
        print(f"BOT_BIND_CHECK_OPTIONAL seats={','.join(sorted(seats))}")
        return 0
    print(f"BOT_BIND_CHECK_OK seats={','.join(sorted(seats))}")
    return 0


def _bind() -> int:
    bots = _load(
        bots_path,
        {
            "version": "1.0.0",
            "description": "Grok Bot seats on the local A2A bus (not grok agent serve / acp_inject).",
            "seats": {},
        },
    )
    seats = bots.get("seats") if isinstance(bots.get("seats"), dict) else {}
    for name in list(seats):
        meta = seats.get(name)
        if name == seat or not isinstance(meta, dict):
            continue
        if _unbound(meta.get("agentId")):
            del seats[name]
    prior = seats.get(seat) if isinstance(seats.get(seat), dict) else {}
    entry = dict(prior)
    entry["kind"] = "grok-bot"
    entry["agentId"] = agent_id.strip()
    entry["inbox"] = f".a2a-state/{seat}"
    if agent_name.strip():
        entry["name"] = agent_name.strip()
    entry.setdefault(
        "note",
        "Orchestrator Bot. Put Bot seats in registry skipSeats. bot-bridge is opt-in (GCS_BOT_BRIDGE=1). Not an ACP inject target. Never a Cursor CloudAgent.",
    )
    seats[seat] = entry
    bots["seats"] = seats
    bots.setdefault("version", "1.0.0")
    bots.setdefault(
        "description",
        "Grok Bot seats on the local A2A bus (not grok agent serve / acp_inject).",
    )
    _dump(bots_path, bots)

    registry = _load(
        registry_path,
        {
            "version": "1.0.0",
            "hub": hub,
            "protocolVersion": "1.0",
            "protocolBinding": "HTTP+JSON",
            "skipSeats": [],
            "seats": {},
        },
    )
    if registry.get("hub"):
        hub_url = str(registry["hub"]).rstrip("/")
    else:
        hub_url = hub
        registry["hub"] = hub
    skip_names = [seat, "donald"]
    skip_names.extend(str(n) for n in seats)
    _ensure_skip(registry, skip_names)
    reg_seats = registry.get("seats") if isinstance(registry.get("seats"), dict) else {}
    seat_reg = dict(reg_seats.get(seat) or {}) if isinstance(reg_seats.get(seat), dict) else {}
    seat_reg.setdefault("card", card_rel)
    seat_reg.setdefault("endpoint", f"{hub_url}/a2a/{seat}")
    seat_reg.setdefault("wellKnown", f"{hub_url}/a2a/{seat}/.well-known/agent-card.json")
    reg_seats[seat] = seat_reg
    registry["seats"] = reg_seats
    _dump(registry_path, registry)

    card_path = cards_dir / f"{seat}.json"
    if not card_path.is_file():
        display = _display_name()
        card = {
            "name": display,
            "description": (
                "Studio orchestrator on Grok Bot — assigns outcomes, deconflicts seats. "
                "Not an ACP inject target."
            ),
            "version": "1.0.0",
            "protocolVersion": "1.0",
            "provider": _provider(),
            "capabilities": {
                "streaming": False,
                "pushNotifications": False,
                "extendedAgentCard": False,
            },
            "defaultInputModes": ["text/plain", "application/json"],
            "defaultOutputModes": ["text/plain", "application/json"],
            "skills": [
                {
                    "id": "orchestrate",
                    "name": "Orchestrate",
                    "description": "Assign tasks and deconflict Directors",
                    "tags": ["orchestration", "bot"],
                }
            ],
            "supportedInterfaces": [
                {
                    "url": f"{hub_url}/a2a/{seat}",
                    "protocolBinding": "HTTP+JSON",
                    "protocolVersion": "1.0",
                }
            ],
        }
        _dump(card_path, card)

    seat_state = state / seat
    seat_state.mkdir(parents=True, exist_ok=True)
    _dump(
        state / "bot-bind.json",
        {"seat": seat, "agentId": agent_id.strip(), "boundAt": _now()},
    )
    print(f"BOT_BIND_OK seat={seat}")
    return 0


if mode == "check":
    raise SystemExit(_check())
raise SystemExit(_bind())
PY
