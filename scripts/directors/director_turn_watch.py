#!/usr/bin/env python3
"""LIV-41: a director turn without watching its own grunt is FAIL.

Grok Build minds/directors spawn Extra High and monitor the bc-id: they
invoke scripts/cloud/spawn-waiter.sh or the cloud_wait plugin so
wait-notify.ts A2A-pings THIS seat FLEET_DONE. Spawn-only (GCS #75) is
not enough. Theatre (prose, ls/cat/rg of waiter/watch scripts,
GCS_SPAWN_WAITER=0) is not watching. fleet-shepherd is orphan-only.

Never Bot CloudAgent. Living Sky LIV, never Black Swan.

Stdlib only. Does not import mind.py (mind imports this). Does not remint
the GCS #75 spawn-only judge.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Iterable

LAUNCH_NEEDLE = "launch-cloud-extra-high"
WAITER_NEEDLE = "spawn-waiter"
WAIT_NOTIFY_NEEDLE = "wait-notify"
WATCH_SCRIPT_NEEDLE = "watch-cloud-agent"
CLOUD_LAUNCH_TOOL = "cloud_launch"
CLOUD_WAIT_TOOL = "cloud_wait"
CLOUD_WAIT_ALIASES = frozenset({"cloud_wait", "spawn_waiter", "spawn-waiter"})

_BOT_NAMES = frozenset(
    {
        "donald",
        "orchestrator",
        "grok-bot",
        "bot",
        "bot-cloudagent",
        "grok bot",
    }
)

_INSPECT_TOOL_NAMES = frozenset(
    {"list_dir", "listdir", "read", "grep", "ls", "cat", "rg", "glob"}
)
_INSPECT_ARGV_RE = re.compile(
    r"(?im)^\s*(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*"
    r"(?:\S*/)?"
    r"(?:ls|cat|rg|grep)\b"
)
_EXEMPT_RE = re.compile(
    r"\bA2A_REPLY\b|\bFLEET_DONE\b|\bPR_READY\b",
    re.IGNORECASE,
)
_LAUNCHISH_RE = re.compile(
    r"(?:\bLAUNCH\b|TASK_ASSIGN|\bplayability\b)",
    re.IGNORECASE,
)
_BC_ID_RE = re.compile(r"\bbc-[0-9A-Za-z_-]+\b")
_RESULT_BC_RE = re.compile(r"\bbc-id\s*=\s*(\S+)", re.IGNORECASE)
_NAME_FLAG_RE = re.compile(r"--name(?:\s+|=)(\S+)", re.IGNORECASE)
_SEAT_FLAG_RE = re.compile(r"--seat(?:\s+|=)(\S+)", re.IGNORECASE)
_NOTIFIED_OK = frozenset({"waiter", "webhook", "shepherd"})


def is_bot_cloudagent(name: str, bot_agent_id: str = "") -> bool:
    raw = (name or "").strip()
    if not raw:
        return False
    lowered = raw.lower()
    if lowered in _BOT_NAMES:
        return True
    if "bot cloudagent" in lowered:
        return True
    bot_id = (bot_agent_id or os.environ.get("GCS_BOT_AGENT_ID") or "").strip()
    if bot_id and raw == bot_id:
        return True
    return False


def watch_exempt(mail: str) -> bool:
    return bool(_EXEMPT_RE.search(mail or ""))


def _flatten_json(data: Any) -> Iterable[dict[str, Any]]:
    if isinstance(data, dict):
        yield data
        for value in data.values():
            yield from _flatten_json(value)
    elif isinstance(data, list):
        for item in data:
            yield from _flatten_json(item)


def _json_objects(text: str) -> list[dict[str, Any]]:
    objs: list[dict[str, Any]] = []
    blob = text or ""
    if not blob.strip():
        return objs
    stripped = blob.strip()
    try:
        objs.extend(_flatten_json(json.loads(stripped)))
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    idx = 0
    length = len(blob)
    while idx < length:
        while idx < length and blob[idx] not in "{[":
            idx += 1
        if idx >= length:
            break
        try:
            value, end = decoder.raw_decode(blob, idx)
        except json.JSONDecodeError:
            idx += 1
            continue
        objs.extend(_flatten_json(value))
        idx = max(end, idx + 1)
    return objs


def _join_argv(val: Any) -> str:
    if isinstance(val, str) and val.strip():
        return val.strip()
    if isinstance(val, (list, tuple)):
        parts = [str(x) for x in val if str(x).strip()]
        return " ".join(parts)
    return ""


def _invoked_command(obj: dict[str, Any]) -> str:
    chunks: list[str] = []
    for key in ("command", "cmd"):
        joined = _join_argv(obj.get(key))
        if joined:
            chunks.append(joined)
    for key in ("argv", "args"):
        joined = _join_argv(obj.get(key))
        if joined:
            chunks.append(joined)
    arguments = obj.get("arguments")
    if isinstance(arguments, dict):
        for key in ("command", "cmd", "argv", "args"):
            joined = _join_argv(arguments.get(key))
            if joined:
                chunks.append(joined)
    for nested in ("rawInput", "input", "params"):
        inner = obj.get(nested)
        if isinstance(inner, dict):
            sub = _invoked_command(inner)
            if sub:
                chunks.append(sub)
        elif isinstance(inner, str) and inner.strip():
            chunks.append(inner.strip())
    return "\n".join(chunks)


def _tool_names(obj: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for key in ("name", "toolName", "tool", "title"):
        raw = obj.get(key)
        if isinstance(raw, str) and raw.strip():
            names.append(raw.strip())
    return names


def _is_inspect_only(obj: dict[str, Any], command: str) -> bool:
    for name in _tool_names(obj):
        token = name.split()[0].replace("-", "_").lower() if name.strip() else ""
        if token in _INSPECT_TOOL_NAMES:
            return True
    lines = [ln.strip() for ln in command.splitlines() if ln.strip()]
    if lines and all(_INSPECT_ARGV_RE.search(ln) for ln in lines):
        return True
    return False


def _meta_name(obj: dict[str, Any], command: str) -> str:
    arguments = obj.get("arguments")
    if isinstance(arguments, dict):
        for key in ("name", "seat"):
            named = str(arguments.get(key) or "").strip()
            if named:
                return named
    named = str(obj.get("name") or "").strip()
    if named and named.lower() not in {
        CLOUD_LAUNCH_TOOL,
        CLOUD_WAIT_TOOL,
        "spawn_waiter",
        "shell",
        "bash",
    }:
        if is_bot_cloudagent(named):
            return named
    match = _NAME_FLAG_RE.search(command or "")
    if match:
        return match.group(1).strip().strip("'\"")
    seat = _SEAT_FLAG_RE.search(command or "")
    if seat:
        return seat.group(1).strip().strip("'\"")
    return ""


def _waiter_disabled(command: str) -> bool:
    blob = command or ""
    if re.search(r"\bGCS_SPAWN_WAITER=0\b", blob) or re.search(
        r"\bCLOUD_SPAWN_WAITER=0\b", blob
    ):
        return True
    return False


def _is_launcher_invoke(command: str) -> bool:
    blob = command or ""
    if LAUNCH_NEEDLE not in blob.lower():
        return False
    if _INSPECT_ARGV_RE.search(blob) and LAUNCH_NEEDLE in blob.lower():
        return False
    return True


def _is_waiter_invoke(command: str) -> bool:
    blob = command or ""
    low = blob.lower()
    if _waiter_disabled(blob):
        return False
    if "fleet-shepherd" in low:
        return False
    needles = (WAITER_NEEDLE, WAIT_NOTIFY_NEEDLE, WATCH_SCRIPT_NEEDLE)
    if not any(n in low for n in needles) and "scripts/cloud/watch.sh" not in low:
        return False
    if _INSPECT_ARGV_RE.search(blob):
        return False
    return True


def _event_is_watch(obj: dict[str, Any]) -> bool:
    names = [n.lower() for n in _tool_names(obj)]
    command = _invoked_command(obj)
    if _is_inspect_only(obj, command):
        return False
    meta = _meta_name(obj, command)
    if meta and is_bot_cloudagent(meta):
        return False
    if _waiter_disabled(command):
        return False
    tokens = {n.replace("-", "_") for n in names}
    if tokens & CLOUD_WAIT_ALIASES:
        return True
    if _is_waiter_invoke(command):
        return True
    return False


def _event_is_grunt(obj: dict[str, Any]) -> bool:
    names = [n.lower() for n in _tool_names(obj)]
    command = _invoked_command(obj)
    if _is_inspect_only(obj, command):
        return False
    if CLOUD_LAUNCH_TOOL in names:
        return True
    if _is_launcher_invoke(command):
        return True
    return False


def turn_watched(assistant: str, bot_agent_id: str = "") -> bool:
    """True when this turn invoked spawn-waiter / cloud_wait / wait-notify.

    Prose, inspect argv, waiter-skip, shepherd, and Bot CloudAgent names
    are not watching.
    """
    del bot_agent_id
    blob = assistant or ""
    if re.search(r"CLOUD_WAITER_SPAWNED\s+id=", blob) and "CLOUD_WAITER_SKIPPED" not in blob:
        if "GCS_SPAWN_WAITER=0" not in blob:
            return True
    for obj in _json_objects(assistant):
        if _event_is_watch(obj):
            return True
    return False


def turn_has_grunt(assistant: str, open_bc_ids: list[str] | None = None) -> bool:
    if open_bc_ids:
        return True
    blob = assistant or ""
    if "CLOUD_LAUNCH_OK" in blob:
        return True
    match = _RESULT_BC_RE.search(blob)
    if match:
        value = match.group(1).strip().strip("'\"")
        if value and value.lower() not in {"none", "null", "-"}:
            return True
    if _BC_ID_RE.search(blob) and "CLOUD_LAUNCH_OK" in blob:
        return True
    for obj in _json_objects(assistant):
        if _event_is_grunt(obj):
            return True
    return False


def watch_required(mail: str, open_bc_ids: list[str] | None = None) -> bool:
    if watch_exempt(mail):
        return False
    if open_bc_ids:
        return True
    return bool(_LAUNCHISH_RE.search(mail or ""))


def _entry_unwatched(entry: dict[str, Any]) -> bool:
    if not isinstance(entry, dict) or not entry.get("bc_id"):
        return False
    if entry.get("notified") and str(entry.get("status") or "") == "closed":
        return False
    if entry.get("notified_by") in _NOTIFIED_OK:
        return False
    pid = entry.get("waiter_pid")
    try:
        pid_i = int(pid)
    except (TypeError, ValueError):
        return True
    if pid_i <= 0:
        return True
    try:
        os.kill(pid_i, 0)
    except OSError:
        return True
    return False


def unwatched_bc_ids(seat: str, state_dir: str | Path | None = None) -> list[str]:
    """Open fleet.jsonl bc-ids for this seat with no live waiter."""
    if state_dir is None:
        raw = (os.environ.get("GCS_A2A_STATE") or "").strip()
        state_dir = Path(raw) if raw else None
    if state_dir is None:
        return []
    path = Path(state_dir) / seat / "fleet.jsonl"
    if not path.is_file():
        return []
    found: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if _entry_unwatched(rec):
            bc_id = str(rec.get("bc_id") or "").strip()
            if bc_id:
                found.append(bc_id)
    return found


def wrap_prompt_if_required(mail: str, open_bc_ids: list[str] | None = None) -> str:
    """Tell the mind it MUST watch. Python does not wait() for it."""
    ids = list(open_bc_ids or [])
    if not watch_required(mail, open_bc_ids=ids):
        return mail
    owned = ", ".join(ids) if ids else "(this turn's CLOUD_LAUNCH_OK bc-id)"
    header = (
        "=== LIV-41 DIRECTORS-WATCH (FAIL CLOSED) ===\n"
        f"You spawn AND monitor YOUR OWN Cursor Cloud bc-ids. Owned={owned}. "
        "This turn MUST invoke cloud_wait or scripts/cloud/spawn-waiter.sh "
        "--id <bc-id> so wait-notify A2A-pings THIS seat FLEET_DONE. "
        "A director turn without watching its own grunt is FAIL. "
        "Demonstrate, don't theatre: prose or ls/cat/rg of spawn-waiter.sh "
        "or watch-cloud-agent.sh is not watching. Do NOT block this session "
        "on watch-cloud-agent.sh. Do not dump watching to Donald or "
        "fleet-shepherd. Never Bot CloudAgent (donald/orchestrator). "
        "GCS_SPAWN_WAITER=0 / CLOUD_WAITER_SKIPPED is not watching. "
        "Model grok-4.6 xhigh fast=false. Linear=Living Sky LIV, never Black Swan.\n"
        "=== END LIV-41 WATCH ===\n\n"
    )
    return header + (mail or "")


def judge_director_watch(
    *,
    mail: str,
    assistant: str,
    open_bc_ids: list[str] | None = None,
    seat: str = "",
    bot_agent_id: str = "",
) -> dict[str, Any]:
    """FAIL when the director owns a grunt and did not actually watch it."""
    del seat
    ids = list(open_bc_ids or [])
    watched = turn_watched(assistant, bot_agent_id=bot_agent_id)
    has_grunt = turn_has_grunt(assistant, open_bc_ids=ids)
    if watch_exempt(mail):
        return {
            "fail": False,
            "reason": "exempt",
            "watched": watched,
            "has_grunt": has_grunt,
        }
    if not has_grunt:
        return {
            "fail": False,
            "reason": "not-required",
            "watched": watched,
            "has_grunt": False,
        }
    if watched:
        return {
            "fail": False,
            "reason": "watched",
            "watched": True,
            "has_grunt": True,
        }
    return {
        "fail": True,
        "reason": "no-watch",
        "watched": False,
        "has_grunt": True,
    }
