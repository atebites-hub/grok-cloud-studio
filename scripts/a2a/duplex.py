#!/usr/bin/env python3
"""Write Director RESULT back onto an A2A task and notify the caller seat.

Idempotent per taskId (.duplex marker). Local studio only. Stdlib.

Hub enqueue is TASK_STATE_SUBMITTED. set_task_state marks COMPLETED after
the Grok Build mind harvests and the runner exits 0. That COMPLETE / A2A
ACK is a receipt, not mind-turn done. RESULT duplex is optional overlay,
not a fake ACP HANDOFF.

A2A_REPLY must succeed after Director RESULT and must not 404 skipSeat
donald (no shipped Agent Card; not an ACP inject target). Map donald →
floor-ops, then orchestrator. If neither card exists, skip notify without
failing the task reply. Hub TASK_STATE_SUBMITTED / later COMPLETED is a
receipt, not mind-turn done, not Director RESULT.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(os.environ.get("GCS_ROOT", Path(__file__).resolve().parents[2]))
STATE_DIR = Path(os.environ.get("GCS_A2A_STATE", str(ROOT / ".a2a-state")))
SEND = Path(os.environ.get("GCS_A2A_SEND", str(ROOT / "scripts" / "a2a" / "send.sh")))
HUB = os.environ.get("GCS_A2A_HUB", "http://127.0.0.1:8732")

RESULT_LINE_RE = re.compile(
    r"^(RESULT|QA_A_RESULT|QA_B_RESULT|PARK_ACK)\b.*$",
    re.MULTILINE,
)
FROM_TEXT_RE = re.compile(r"\bfrom=([a-z0-9-]+)\b", re.IGNORECASE)
SEAT_RE = re.compile(r"^[a-z0-9-]+$")
SendFn = Callable[[str, str], bool]
# skipSeats that 404 on hub message:send (no Agent Card). Prefer Palemon
# floor-ops (Donald-clone Director), then orchestrator (Bot card).
NOTIFY_FALLBACKS: dict[str, tuple[str, ...]] = {
    "donald": ("floor-ops", "orchestrator"),
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def extract_result_line(text: str) -> str | None:
    if not text:
        return None
    found: str | None = None
    for match in RESULT_LINE_RE.finditer(text):
        found = match.group(0).strip()
    return found


def _from_data(obj: Any) -> str | None:
    if not isinstance(obj, dict):
        return None
    raw = obj.get("from") or obj.get("fromSeat") or obj.get("caller")
    if raw is None:
        meta = obj.get("metadata")
        if isinstance(meta, dict):
            raw = meta.get("from")
    if raw is None:
        return None
    seat = str(raw).strip().lower().replace("_", "-")
    if SEAT_RE.match(seat):
        return seat
    return None


def extract_caller(record: dict[str, Any]) -> str | None:
    direct = _from_data(record)
    if direct:
        return direct
    raw = record.get("raw")
    if isinstance(raw, dict):
        nested = _from_data(raw) or _from_data(raw.get("message") or {})
        if nested:
            return nested
    parts = record.get("parts")
    if isinstance(parts, list):
        for part in parts:
            if not isinstance(part, dict):
                continue
            if part.get("kind") == "data" or "data" in part:
                nested = _from_data(part.get("data") or {})
                if nested:
                    return nested
            text = part.get("text")
            if isinstance(text, str):
                match = FROM_TEXT_RE.search(text)
                if match:
                    return match.group(1).lower()
    return None


def _cards_dir(root: Path | None = None) -> Path:
    return Path(root or ROOT) / "docs" / "a2a" / "cards"


def has_hub_card(seat: str, root: Path | None = None) -> bool:
    """True when hub will accept POST /a2a/{seat}/message:send (Agent Card)."""
    if not seat or not SEAT_RE.match(seat):
        return False
    return (_cards_dir(root) / f"{seat}.json").is_file()


def resolve_notify_seat(
    caller: str | None,
    *,
    working_seat: str | None = None,
    root: Path | None = None,
) -> str | None:
    """Seat that can receive A2A_REPLY without a hub 404.

    donald (skipSeat, no card) maps to floor-ops then orchestrator. A candidate
    equal to the working seat is skipped so the Director is not pinged for its
    own RESULT. Missing card → None (caller should skip notify).
    """
    if not caller:
        return None
    seat = str(caller).strip().lower().replace("_", "-")
    if not SEAT_RE.match(seat):
        return None
    work = (working_seat or "").strip().lower().replace("_", "-")
    fallbacks = NOTIFY_FALLBACKS.get(seat)
    candidates = list(fallbacks) if fallbacks else [seat]
    for cand in candidates:
        if work and cand == work:
            continue
        if has_hub_card(cand, root):
            return cand
    return None


def _tasks_path(state_dir: Path, seat: str) -> Path:
    return Path(state_dir) / seat / "tasks.json"


def set_task_state(
    state_dir: Path,
    seat: str,
    task_id: str,
    state: str,
    *,
    text: str | None = None,
) -> dict[str, Any] | None:
    """Update an existing hub task's status. No-op if the task is missing.

    Mail stays TASK_STATE_SUBMITTED until the Grok Build mind harvests and
    finishes (runner exit 0). Do not invent a task here.
    """
    tid = str(task_id or "").strip()
    if not tid:
        return None
    path = _tasks_path(state_dir, seat)
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(loaded, dict):
        return None
    task = loaded.get(tid)
    if not isinstance(task, dict):
        return None
    status = dict(task.get("status") or {})
    status["state"] = state
    status["timestamp"] = now_iso()
    if text:
        status["message"] = {
            "messageId": str(uuid.uuid4()),
            "role": "ROLE_AGENT",
            "parts": [{"kind": "text", "text": text}],
        }
    task["status"] = status
    loaded[tid] = task
    tmp = path.with_suffix(".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps(loaded, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return task


def _duplex_marker(state_dir: Path, seat: str, task_id: str) -> Path:
    d = Path(state_dir) / seat / "runs"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{task_id}.duplex"


def write_task_reply(
    state_dir: Path,
    seat: str,
    task_id: str,
    text: str,
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    path = _tasks_path(state_dir, seat)
    if not path.is_file():
        tasks: dict[str, Any] = {}
    else:
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            loaded = {}
        tasks = loaded if isinstance(loaded, dict) else {}
    task = tasks.get(task_id)
    if not isinstance(task, dict):
        task = {
            "id": task_id,
            "status": {"state": "TASK_STATE_COMPLETED", "timestamp": now_iso()},
            "history": [],
            "artifacts": [],
        }
    artifacts = list(task.get("artifacts") or [])
    artifacts.append(
        {
            "artifactId": str(uuid.uuid4()),
            "name": "director-result",
            "parts": [
                {"kind": "text", "text": text},
                {
                    "kind": "data",
                    "data": {
                        "seat": seat,
                        "taskId": task_id,
                        "repliedAt": now_iso(),
                        **(extra or {}),
                    },
                },
            ],
        }
    )
    history = list(task.get("history") or [])
    history.append(
        {
            "messageId": str(uuid.uuid4()),
            "role": "ROLE_AGENT",
            "parts": [{"kind": "text", "text": text}],
        }
    )
    task["artifacts"] = artifacts
    task["history"] = history
    status = dict(task.get("status") or {})
    status["state"] = "TASK_STATE_COMPLETED"
    status["timestamp"] = now_iso()
    status["message"] = {
        "messageId": str(uuid.uuid4()),
        "role": "ROLE_AGENT",
        "parts": [{"kind": "text", "text": text}],
    }
    task["status"] = status
    tasks[task_id] = task
    tmp = path.with_suffix(".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps(tasks, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return task


def default_send(seat: str, text: str) -> bool:
    if not SEND.is_file():
        return False
    try:
        proc = subprocess.run(
            ["bash", str(SEND), "--from", "duplex", seat, text],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def notify_caller(
    from_seat: str,
    text: str,
    *,
    send_fn: SendFn | None = None,
    working_seat: str | None = None,
    root: Path | None = None,
) -> bool:
    target = resolve_notify_seat(from_seat, working_seat=working_seat, root=root)
    if not target:
        return False
    sender = send_fn or default_send
    return sender(target, text)


def duplex_from_output(
    *,
    state_dir: Path,
    seat: str,
    record: dict[str, Any],
    output_text: str,
    send_fn: SendFn | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    task_id = str(record.get("taskId") or record.get("id") or "").strip()
    if not task_id:
        return {"ok": False, "reason": "no-task"}
    marker = _duplex_marker(state_dir, seat, task_id)
    if marker.is_file():
        return {"ok": True, "skipped": "already", "taskId": task_id}
    line = extract_result_line(output_text)
    if not line:
        return {"ok": False, "reason": "no-result", "taskId": task_id}
    write_task_reply(state_dir, seat, task_id, line, extra={"via": "duplex"})
    caller = extract_caller(record)
    notified = False
    notify_skipped: str | None = None
    target = resolve_notify_seat(caller, working_seat=seat, root=root)
    if target:
        ping = (
            f"A2A_REPLY seat={seat} task={task_id} context={record.get('contextId') or ''} "
            f"{line}"
        )
        notified = notify_caller(
            caller, ping, send_fn=send_fn, working_seat=seat, root=root
        )
        if not notified:
            notify_skipped = "send-fail"
    elif caller and caller != seat:
        key = str(caller).strip().lower().replace("_", "-")
        notify_skipped = "skipSeat" if key in NOTIFY_FALLBACKS else "no-card"
    marker.write_text(
        json.dumps(
            {
                "taskId": task_id,
                "at": now_iso(),
                "caller": caller,
                "notifySeat": target,
                "notifySkipped": notify_skipped,
            }
        )
        + "\n"
    )
    return {
        "ok": True,
        "taskId": task_id,
        "result": line,
        "caller": caller,
        "notify_seat": target,
        "notified": notified,
        "notify_skipped": notify_skipped,
    }


def record_from_env(extra_prompt: str = "") -> dict[str, Any]:
    task_id = (os.environ.get("GCS_A2A_TASK_ID") or "").strip()
    context_id = (os.environ.get("GCS_A2A_CONTEXT") or "").strip()
    from_seat = (os.environ.get("GCS_A2A_FROM") or "").strip()
    if not task_id:
        match = re.search(r"A2A_TASK_ID=(\S+)", extra_prompt)
        if match:
            task_id = match.group(1).strip()
    if not context_id:
        match = re.search(r"A2A_CONTEXT=(\S+)", extra_prompt)
        if match:
            context_id = match.group(1).strip()
    parts: list[dict[str, Any]] = []
    if from_seat:
        parts.append({"kind": "data", "data": {"from": from_seat}})
    if extra_prompt:
        parts.append({"kind": "text", "text": extra_prompt})
    return {"taskId": task_id, "contextId": context_id, "parts": parts, "from": from_seat or None}
