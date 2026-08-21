#!/usr/bin/env python3
"""Minimal local A2A HTTP+JSON hub for Grok Cloud Studio seats.

Stdlib only. Serves Agent Cards, Send Message, Get/List/Cancel Task.
This hub is the protocol ack bus: it appends per-seat inbox JSONL and
returns TASK_STATE_COMPLETED + a receipt artifact.

Auto-wake of Grok Build Director seats is handled separately by
scripts/a2a/wake-daemon.py (inbox.jsonl → pin-session ACP session/prompt into
live grok agent serve), scripts/a2a/dispatch.py (fallback inbox poller), and
scripts/a2a/start-studio-bus.sh. The hub itself does not launch Directors.

Docs: docs/ARCHITECTURE.md
A2A: https://a2a-protocol.org/latest/
"""
from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

HOST = os.environ.get("GCS_A2A_HOST", "127.0.0.1")
PORT = int(os.environ.get("GCS_A2A_PORT", "8732"))
ROOT = Path(os.environ.get("GCS_ROOT", Path(__file__).resolve().parents[2]))
CARDS_DIR = ROOT / "docs" / "a2a" / "cards"
REGISTRY_PATH = ROOT / "docs" / "a2a" / "registry.json"
STATE_DIR = Path(os.environ.get("GCS_A2A_STATE", str(ROOT / ".a2a-state")))

SEAT_RE = re.compile(r"^[a-z0-9-]+$")
TASK_STATE_SUBMITTED = "TASK_STATE_SUBMITTED"
TASK_STATE_WORKING = "TASK_STATE_WORKING"
TASK_STATE_COMPLETED = "TASK_STATE_COMPLETED"
TASK_STATE_CANCELED = "TASK_STATE_CANCELED"
ROLE_USER = "ROLE_USER"
ROLE_AGENT = "ROLE_AGENT"

_lock = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _seat_dir(seat: str) -> Path:
    d = STATE_DIR / seat
    d.mkdir(parents=True, exist_ok=True)
    return d


def _tasks_path(seat: str) -> Path:
    return _seat_dir(seat) / "tasks.json"


def _inbox_path(seat: str) -> Path:
    return _seat_dir(seat) / "inbox.jsonl"


def _load_tasks(seat: str) -> dict[str, Any]:
    p = _tasks_path(seat)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_tasks(seat: str, tasks: dict[str, Any]) -> None:
    p = _tasks_path(seat)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(tasks, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)


def _append_inbox(seat: str, record: dict[str, Any]) -> None:
    with _inbox_path(seat).open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _load_card(seat: str) -> dict[str, Any] | None:
    path = CARDS_DIR / f"{seat}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _load_registry() -> dict[str, Any]:
    if REGISTRY_PATH.is_file():
        return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return {"version": "1.0.0", "hub": f"http://{HOST}:{PORT}", "seats": {}}


def _json_response(handler: BaseHTTPRequestHandler, code: int, body: Any) -> None:
    data = json.dumps(body, indent=2).encode("utf-8") + b"\n"
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(data)


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length") or "0")
    raw = handler.rfile.read(length) if length else b"{}"
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def _parse_path(path: str) -> tuple[str | None, str | None, str | None, str | None]:
    """Return (seat, action, task_id, subaction)."""
    parsed = urlparse(path)
    parts = [p for p in parsed.path.split("/") if p]
    if not parts:
        return None, None, None, None
    if parts[0] == "health" and len(parts) == 1:
        return None, "health", None, None
    if parts[0] == "registry" and len(parts) == 1:
        return None, "registry", None, None
    if parts[0] != "a2a" or len(parts) < 2:
        return None, None, None, None
    seat = parts[1]
    if not SEAT_RE.match(seat):
        return None, None, None, None
    rest = parts[2:]
    if not rest:
        return seat, "root", None, None
    if rest[0] == ".well-known" and len(rest) == 2 and rest[1] == "agent-card.json":
        return seat, "agent-card", None, None
    if rest[0] == "agent-card.json" and len(rest) == 1:
        return seat, "agent-card", None, None
    if rest[0] == "message:send" and len(rest) == 1:
        return seat, "message-send", None, None
    if rest[0] == "tasks":
        if len(rest) == 1:
            return seat, "tasks-list", None, None
        tid = rest[1]
        if tid.endswith(":cancel"):
            return seat, "task-cancel", tid[: -len(":cancel")], "cancel"
        if len(rest) == 2:
            return seat, "task-get", tid, None
        if len(rest) == 2 or (len(rest) == 3 and rest[2] == ""):
            return seat, "task-get", tid, None
    if len(rest) == 2 and rest[0] == "tasks" and rest[1].endswith(":cancel"):
        return seat, "task-cancel", rest[1][: -len(":cancel")], "cancel"
    return seat, "unknown", None, None


class A2AHandler(BaseHTTPRequestHandler):
    server_version = "GrokCloudStudioA2AHub/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[a2a] {self.address_string()} {fmt % args}")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        seat, action, task_id, _ = _parse_path(self.path)
        if action == "health":
            _json_response(
                self,
                200,
                {
                    "ok": True,
                    "service": "gcs-a2a-hub",
                    "host": HOST,
                    "port": PORT,
                    "stateDir": str(STATE_DIR),
                    "time": _now(),
                },
            )
            return
        if action == "registry":
            _json_response(self, 200, _load_registry())
            return
        if action == "agent-card" and seat:
            card = _load_card(seat)
            if card is None:
                _json_response(self, 404, {"error": f"unknown seat: {seat}"})
                return
            _json_response(self, 200, card)
            return
        if action == "tasks-list" and seat:
            if _load_card(seat) is None:
                _json_response(self, 404, {"error": f"unknown seat: {seat}"})
                return
            with _lock:
                tasks = list(_load_tasks(seat).values())
            _json_response(self, 200, {"tasks": tasks})
            return
        if action == "task-get" and seat and task_id:
            with _lock:
                tasks = _load_tasks(seat)
                task = tasks.get(task_id)
            if not task:
                _json_response(self, 404, {"error": f"task not found: {task_id}"})
                return
            _json_response(self, 200, task)
            return
        _json_response(self, 404, {"error": "not found", "path": self.path})

    def do_POST(self) -> None:
        seat, action, task_id, _ = _parse_path(self.path)
        if action == "message-send" and seat:
            if _load_card(seat) is None:
                _json_response(self, 404, {"error": f"unknown seat: {seat}"})
                return
            try:
                body = _read_json(self)
            except json.JSONDecodeError as e:
                _json_response(self, 400, {"error": f"invalid json: {e}"})
                return
            msg = body.get("message") or body
            message_id = msg.get("messageId") or str(uuid.uuid4())
            role = msg.get("role") or ROLE_USER
            parts = msg.get("parts") or []
            if not parts and "text" in body:
                parts = [{"kind": "text", "text": body["text"]}]
            task_id_new = str(uuid.uuid4())
            context_id = body.get("contextId") or msg.get("contextId") or str(uuid.uuid4())
            text_bits = []
            for p in parts:
                if isinstance(p, dict):
                    if "text" in p:
                        text_bits.append(str(p["text"]))
                    elif p.get("kind") == "data" and "data" in p:
                        text_bits.append(json.dumps(p["data"]))
            receipt_text = " ".join(text_bits).strip() or "(empty)"
            task = {
                "id": task_id_new,
                "contextId": context_id,
                "status": {
                    "state": TASK_STATE_COMPLETED,
                    "timestamp": _now(),
                    "message": {
                        "messageId": str(uuid.uuid4()),
                        "role": ROLE_AGENT,
                        "parts": [
                            {
                                "kind": "text",
                                "text": f"ACK seat={seat} messageId={message_id}",
                            }
                        ],
                    },
                },
                "history": [
                    {
                        "messageId": message_id,
                        "role": role,
                        "parts": parts,
                    }
                ],
                "artifacts": [
                    {
                        "artifactId": str(uuid.uuid4()),
                        "name": "receipt",
                        "parts": [
                            {
                                "kind": "data",
                                "data": {
                                    "seat": seat,
                                    "messageId": message_id,
                                    "receivedAt": _now(),
                                    "preview": receipt_text[:500],
                                    "note": "Simple ack hub — seats poll inbox JSONL or an orchestrator bridges.",
                                },
                            }
                        ],
                    }
                ],
                "metadata": {
                    "hub": "gcs-a2a",
                    "kind": "ack",
                },
            }
            inbox_record = {
                "receivedAt": _now(),
                "taskId": task_id_new,
                "contextId": context_id,
                "messageId": message_id,
                "role": role,
                "parts": parts,
                "from": body.get("from") or (msg.get("metadata") or {}).get("from"),
                "raw": body,
            }
            with _lock:
                tasks = _load_tasks(seat)
                tasks[task_id_new] = task
                _save_tasks(seat, tasks)
                _append_inbox(seat, inbox_record)
            _json_response(self, 200, {"task": task})
            return
        if action == "task-cancel" and seat and task_id:
            with _lock:
                tasks = _load_tasks(seat)
                task = tasks.get(task_id)
                if not task:
                    _json_response(self, 404, {"error": f"task not found: {task_id}"})
                    return
                state = (task.get("status") or {}).get("state")
                if state in (TASK_STATE_COMPLETED, TASK_STATE_CANCELED):
                    _json_response(self, 200, {"task": task, "note": "already terminal"})
                    return
                task["status"] = {
                    "state": TASK_STATE_CANCELED,
                    "timestamp": _now(),
                    "message": {
                        "messageId": str(uuid.uuid4()),
                        "role": ROLE_AGENT,
                        "parts": [{"kind": "text", "text": "canceled"}],
                    },
                }
                tasks[task_id] = task
                _save_tasks(seat, tasks)
            _json_response(self, 200, {"task": task})
            return
        _json_response(self, 404, {"error": "not found", "path": self.path})


def main() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    httpd = ThreadingHTTPServer((HOST, PORT), A2AHandler)
    print(
        f"gcs-a2a-hub listening on http://{HOST}:{PORT} "
        f"(cards={CARDS_DIR} state={STATE_DIR})"
    )
    print("endpoints: GET /health  GET /registry  GET /a2a/{seat}/.well-known/agent-card.json")
    print("           POST /a2a/{seat}/message:send  GET /a2a/{seat}/tasks[/{id}]  POST .../tasks/{id}:cancel")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
        httpd.shutdown()


if __name__ == "__main__":
    main()
