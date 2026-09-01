#!/usr/bin/env python3
"""LIV-41: a director turn without spawning/watching its own grunt is FAIL.

Grok Build leftover ACP and mind turns that own a Cursor Cloud create
(Director-owns-launch / LAUNCH / TASK_ASSIGN) MUST invoke
scripts/launch-cloud-extra-high.sh (or cloud_launch) AND leave a waiter
(spawn-waiter.sh / CLOUD_WAITER_SPAWNED). Theatre (prose, ls/cat/rg of
the launcher, leftover CLOUD_LAUNCH_OK text, blocking watch-cloud-agent.sh,
GCS_SPAWN_WAITER=0) is not spawn/watch.

Does not remint GCS #75 (spawn-only / reason=no-spawn / under-floor) or
GCS #91 (watch-only / reason=no-watch). Combined FAIL is
reason=no-spawn-watch.

Unique --name (example gcs-liv41-own-grunt-floor2105). Refuse twin of
RUNNING gcs-liv59-anti-twin-floor2105. Never Bot CloudAgent. Extra High
stays grok-4.6 xhigh fast=false. Empty GitHub checks are not merge.

Stdlib only. Does not import mind.py or acp_inject.py.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Iterable

LAUNCH_REL = "scripts/launch-cloud-extra-high.sh"
LAUNCH_NEEDLE = "launch-cloud-extra-high"
WAITER_NEEDLE = "spawn-waiter"
WAIT_NOTIFY_NEEDLE = "wait-notify"
WATCH_BLOCK_NEEDLE = "watch-cloud-agent"
CLOUD_LAUNCH_TOOL = "cloud_launch"
CLOUD_WAIT_TOOL = "cloud_wait"
CLOUD_WAIT_ALIASES = frozenset({"cloud_wait", "spawn_waiter", "spawn-waiter"})
UNIQUE_NAME = "gcs-liv41-own-grunt-floor2105"
REFUSED_RUNNING_TWIN = "gcs-liv59-anti-twin-floor2105"

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
_REQUIRED_RE = re.compile(
    r"(?:"
    r"Director-owns-launch|"
    r"\bLAUNCH ONLY\b|"
    r"TASK_ASSIGN|"
    r"CLOUD_LAUNCH|"
    r"\bplayability\b|"
    r"\bLAUNCH\b"
    r")",
    re.IGNORECASE,
)
_NAME_FLAG_RE = re.compile(r"--name(?:\s+|=)(\S+)", re.IGNORECASE)
_SKIP_WAITER_RE = re.compile(
    r"GCS_SPAWN_WAITER=0|CLOUD_SPAWN_WAITER=0|CLOUD_WAITER_SKIPPED",
    re.IGNORECASE,
)
_WAITER_SPAWNED_RE = re.compile(r"\bCLOUD_WAITER_SPAWNED\b")
_WRAP_MARK = "=== LIV-41 OWN-GRUNT"


def is_bot_cloudagent(name: str, bot_agent_id: str = "") -> bool:
    raw = (name or "").strip().strip("'\"")
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


def is_refused_twin_name(name: str) -> bool:
    """True for the live RUNNING Extra High name (and hyphen suffix twins)."""
    raw = (name or "").strip().strip("'\"")
    if not raw:
        return False
    lowered = raw.lower()
    needle = REFUSED_RUNNING_TWIN.lower()
    if lowered == needle:
        return True
    return lowered.startswith(needle + "-")


def own_grunt_exempt(mail: str) -> bool:
    return bool(_EXEMPT_RE.search(mail or ""))


def own_grunt_required(mail: str) -> bool:
    if own_grunt_exempt(mail):
        return False
    return bool(_REQUIRED_RE.search(mail or ""))


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


def _name_from_event(obj: dict[str, Any], command: str) -> str:
    arguments = obj.get("arguments")
    if isinstance(arguments, dict):
        named = str(arguments.get("name") or "").strip().strip("'\"")
        if named:
            return named
    match = _NAME_FLAG_RE.search(command or "")
    if match:
        return match.group(1).strip().strip("'\"")
    return ""


def _is_launcher_invoke(command: str) -> bool:
    blob = command or ""
    if LAUNCH_NEEDLE not in blob.lower() and LAUNCH_REL not in blob:
        return False
    if _INSPECT_ARGV_RE.search(blob):
        return False
    return True


def _events(assistant: str, tool_updates: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    objs = _json_objects(assistant)
    for update in tool_updates or []:
        if isinstance(update, dict):
            objs.append(update)
    return objs


def _event_is_launcher(obj: dict[str, Any]) -> bool:
    names = [n.lower() for n in _tool_names(obj)]
    command = _invoked_command(obj)
    if _is_inspect_only(obj, command):
        return False
    if CLOUD_LAUNCH_TOOL in names:
        return True
    return _is_launcher_invoke(command)


def _event_is_waiter(obj: dict[str, Any]) -> bool:
    names = [n.lower().replace("-", "_") for n in _tool_names(obj)]
    command = _invoked_command(obj)
    if _is_inspect_only(obj, command):
        return False
    if any(alias.replace("-", "_") in names for alias in CLOUD_WAIT_ALIASES):
        return True
    blob = command.lower()
    if WATCH_BLOCK_NEEDLE in blob:
        return False
    if WAITER_NEEDLE in blob or WAIT_NOTIFY_NEEDLE in blob:
        return True
    return False


def _name_forbidden(name: str) -> str:
    """Return detail key if this Extra High --name is refused, else empty."""
    if not name:
        return ""
    if is_bot_cloudagent(name):
        return "bot"
    if is_refused_twin_name(name):
        return "twin"
    return ""


def _waiter_skipped(assistant: str, command: str) -> bool:
    blob = f"{command}\n{assistant or ''}"
    return bool(_SKIP_WAITER_RE.search(blob))


def wrap_prompt_if_required(mail: str) -> str:
    """Tell the mind it MUST spawn and watch. Python does not launch for it."""
    text = mail or ""
    if text.startswith(_WRAP_MARK):
        return text
    if not own_grunt_required(text):
        return text
    header = (
        f"{_WRAP_MARK} (FAIL CLOSED) ===\n"
        "This director-owns-launch turn MUST spawn AND watch YOUR Cursor Cloud "
        f"grunt via {LAUNCH_REL} (or cloud_launch). "
        "A turn without spawn/watch is FAIL (reason=no-spawn-watch). "
        f"Unique --name (example {UNIQUE_NAME}). "
        f"Refuse twin of RUNNING {REFUSED_RUNNING_TWIN}. "
        "Never Bot CloudAgent (donald/orchestrator). "
        "Do not block on watch-cloud-agent.sh; waiter is spawn-waiter.sh. "
        "GCS_SPAWN_WAITER=0 is FAIL. Model grok-4.6 xhigh fast=false. "
        "Empty GitHub checks are not merge.\n"
        "=== END LIV-41 ===\n\n"
    )
    return header + text


def judge_director_own_grunt(
    *,
    mail: str,
    assistant: str = "",
    tool_updates: list[dict[str, Any]] | None = None,
    bot_agent_id: str = "",
) -> dict[str, Any]:
    """FAIL when a director-owns-launch turn did not spawn and watch."""
    del bot_agent_id
    spawned = False
    watched = False
    spawn_name = ""
    forbidden = ""
    for obj in _events(assistant, tool_updates):
        command = _invoked_command(obj)
        if _event_is_launcher(obj):
            named = _name_from_event(obj, command)
            bad = _name_forbidden(named)
            if bad:
                forbidden = bad
                continue
            spawned = True
            spawn_name = named or spawn_name
            if not _waiter_skipped(assistant, command):
                watched = True
        if _event_is_waiter(obj):
            watched = True
    if spawned and _WAITER_SPAWNED_RE.search(assistant or ""):
        watched = True
    if spawned and _SKIP_WAITER_RE.search(assistant or "") and not watched:
        watched = False

    if own_grunt_exempt(mail):
        return {
            "fail": False,
            "reason": "exempt",
            "spawned": spawned,
            "watched": watched,
            "name": spawn_name,
        }
    if not own_grunt_required(mail):
        return {
            "fail": False,
            "reason": "not-required",
            "spawned": spawned,
            "watched": watched,
            "name": spawn_name,
        }
    if forbidden and not spawned:
        return {
            "fail": True,
            "reason": "no-spawn-watch",
            "detail": forbidden,
            "spawned": False,
            "watched": False,
            "name": spawn_name,
        }
    if not spawned:
        return {
            "fail": True,
            "reason": "no-spawn-watch",
            "detail": "missing-spawn",
            "spawned": False,
            "watched": False,
            "name": spawn_name,
        }
    if not watched:
        return {
            "fail": True,
            "reason": "no-spawn-watch",
            "detail": "missing-watch",
            "spawned": True,
            "watched": False,
            "name": spawn_name,
        }
    return {
        "fail": False,
        "reason": "own-grunt",
        "spawned": True,
        "watched": True,
        "name": spawn_name,
        "detail": "",
    }
