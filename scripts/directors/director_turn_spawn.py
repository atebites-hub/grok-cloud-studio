#!/usr/bin/env python3
"""LIV-41: a director turn without a spawn when under floor is FAIL.

Grok Build minds/directors themselves invoke scripts/launch-cloud-extra-high.sh
or the cloud_launch plugin. Python does not fill the floor (that would be
Donald). Demonstrate: inspect invoked argv / tool name. Theatre (prose,
ls/cat/rg of the launcher, leftover CLOUD_LAUNCH_OK text) is not a spawn.

Count latest-run runStatus RUNNING. Floor is GCS_CLOUD_MIN_RUNNING (default 8).
Do not reuse --name gcs-liv41-mind-must-launch. Never Bot CloudAgent.
Living Sky LIV, never Black Swan.

Stdlib only. Does not import mind.py (mind imports this).
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Iterable

DEFAULT_MIN_RUNNING = 8
RESERVED_SPAWN_NAME = "gcs-liv41-mind-must-launch"
LAUNCH_REL = "scripts/launch-cloud-extra-high.sh"
LAUNCH_NEEDLE = "launch-cloud-extra-high"
CLOUD_LAUNCH_TOOL = "cloud_launch"

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
    r"\bACP_PING\b|"
    r"STATUS/CONTINUE|"
    r"CAPACITY_BEAT|"
    r"CLOUD_CAPACITY|"
    r"\bLAUNCH\b|"
    r"TASK_ASSIGN|"
    r"\bplayability\b"
    r")",
    re.IGNORECASE,
)
_NAME_FLAG_RE = re.compile(r"--name(?:\s+|=)(\S+)", re.IGNORECASE)


def min_running(raw: str | None = None) -> int:
    text = (raw if raw is not None else os.environ.get("GCS_CLOUD_MIN_RUNNING") or "").strip()
    if not text:
        return DEFAULT_MIN_RUNNING
    try:
        value = int(text)
    except ValueError:
        return DEFAULT_MIN_RUNNING
    return value if value > 0 else DEFAULT_MIN_RUNNING


def running_count(raw: str | None = None) -> int:
    """Fail-closed: missing GCS_CLOUD_RUNNING means 0 (under floor)."""
    text = (raw if raw is not None else os.environ.get("GCS_CLOUD_RUNNING") or "").strip()
    if not text:
        return 0
    try:
        return max(0, int(text))
    except ValueError:
        return 0


def under_floor(running: int, cap: int | None = None) -> bool:
    limit = min_running() if cap is None else cap
    return int(running) < int(limit)


def spawn_exempt(mail: str) -> bool:
    return bool(_EXEMPT_RE.search(mail or ""))


def spawn_required(mail: str) -> bool:
    if spawn_exempt(mail):
        return False
    return bool(_REQUIRED_RE.search(mail or ""))


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


def is_forbidden_spawn_name(name: str, bot_agent_id: str = "") -> bool:
    raw = (name or "").strip()
    if not raw:
        return False
    if raw.lower() == RESERVED_SPAWN_NAME.lower():
        return True
    return is_bot_cloudagent(raw, bot_agent_id=bot_agent_id)


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


def _name_from_command(command: str, obj: dict[str, Any]) -> str:
    arguments = obj.get("arguments")
    if isinstance(arguments, dict):
        named = str(arguments.get("name") or "").strip()
        if named:
            return named
    named = str(obj.get("name") or "").strip()
    if named and named.lower() not in {CLOUD_LAUNCH_TOOL, "shell", "bash"}:
        if named.lower() == RESERVED_SPAWN_NAME.lower() or is_bot_cloudagent(named):
            return named
    match = _NAME_FLAG_RE.search(command or "")
    if match:
        return match.group(1).strip().strip("'\"")
    return ""


def _is_launcher_invoke(command: str) -> bool:
    blob = command or ""
    if LAUNCH_NEEDLE not in blob.lower() and LAUNCH_REL not in blob:
        return False
    if _INSPECT_ARGV_RE.search(blob) and LAUNCH_NEEDLE in blob.lower():
        # ls/cat/rg ... launch-cloud-extra-high.sh
        return False
    return True


def _event_is_spawn(obj: dict[str, Any]) -> bool:
    names = [n.lower() for n in _tool_names(obj)]
    command = _invoked_command(obj)
    if _is_inspect_only(obj, command):
        return False
    spawn_name = _name_from_command(command, obj)
    if spawn_name and is_forbidden_spawn_name(spawn_name):
        return False
    if CLOUD_LAUNCH_TOOL in names:
        return True
    if _is_launcher_invoke(command):
        return True
    return False


def turn_spawned(assistant: str, bot_agent_id: str = "") -> bool:
    """True when this turn invoked cloud_launch or launch-cloud-extra-high.sh.

    Prose, inspect argv (ls/cat/rg), reserved FINISHED name, and Bot
    CloudAgent names are theatre / forbidden — not a spawn.
    """
    del bot_agent_id
    for obj in _json_objects(assistant):
        if _event_is_spawn(obj):
            return True
    return False


def wrap_prompt_if_required(mail: str, running: int, cap: int | None = None) -> str:
    """Tell the mind it MUST spawn. Python does not launch for it."""
    if not spawn_required(mail) or not under_floor(running, cap=cap):
        return mail
    limit = min_running() if cap is None else cap
    header = (
        "=== LIV-41 DIRECTORS-SPAWN (FAIL CLOSED) ===\n"
        f"Bound repo RUNNING={int(running)} floor={int(limit)}. Under floor. "
        "This turn MUST invoke cloud_launch or scripts/launch-cloud-extra-high.sh. "
        "A turn without a spawn is FAIL. Demonstrate, don't theatre: prose or "
        f"ls/cat/rg of the launcher is not a spawn. Do not reuse --name "
        f"{RESERVED_SPAWN_NAME}. Never Bot CloudAgent (donald/orchestrator). "
        "Do not send.sh donald to launch. Model grok-4.6 xhigh fast=false. "
        "Linear=Living Sky LIV, never Black Swan.\n"
        "=== END LIV-41 ===\n\n"
    )
    return header + (mail or "")


def judge_director_turn(
    *,
    mail: str,
    assistant: str,
    running_count: int,
    cap: int | None = None,
    bot_agent_id: str = "",
) -> dict[str, Any]:
    """FAIL when a spawn-required turn under floor did not actually spawn."""
    spawned = turn_spawned(assistant, bot_agent_id=bot_agent_id)
    if spawn_exempt(mail):
        return {
            "fail": False,
            "reason": "exempt",
            "spawned": spawned,
            "running": running_count,
        }
    if not spawn_required(mail):
        return {
            "fail": False,
            "reason": "not-required",
            "spawned": spawned,
            "running": running_count,
        }
    if not under_floor(running_count, cap=cap):
        return {
            "fail": False,
            "reason": "at-floor",
            "spawned": spawned,
            "running": running_count,
        }
    if spawned:
        return {
            "fail": False,
            "reason": "spawned",
            "spawned": True,
            "running": running_count,
        }
    return {
        "fail": True,
        "reason": "no-spawn",
        "spawned": False,
        "running": running_count,
    }
