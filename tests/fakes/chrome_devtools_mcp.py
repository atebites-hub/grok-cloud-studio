#!/usr/bin/env python3
"""Fake chrome-devtools MCP stdio server (Content-Length). No live Chrome.

LIV-42 pytest stand-in for `npx -y chrome-devtools-mcp@latest`. Production grok
still launches the xAI catalog package from GROK_HOME/config.toml. This process
only implements tools/list and tools/call for navigate_page (plus the other
visual-QA names grok would see).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

PROTOCOL = "2024-11-05"
SERVER_NAME = "chrome-devtools"
PLAYTEST_URL = "http://127.0.0.1:5173/"


def _tool(name: str, description: str, properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": properties,
            "additionalProperties": True,
        },
    }


def tools() -> list[dict[str, Any]]:
    url_prop = {"url": {"type": "string", "description": "Target URL"}}
    return [
        _tool("navigate_page", "Go to a URL, or back, forward, or reload.", url_prop),
        _tool("new_page", "Open a new page. May include a URL.", url_prop),
        _tool("list_pages", "List open pages.", {}),
        _tool("take_screenshot", "Take a screenshot of the current page.", {}),
        _tool("take_snapshot", "Take a text snapshot of the current page.", {}),
    ]


def write_message(obj: dict[str, Any]) -> None:
    blob = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(blob)}\r\n\r\n".encode("ascii"))
    sys.stdout.buffer.write(blob)
    sys.stdout.buffer.flush()


def read_message() -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        raw = sys.stdin.buffer.readline()
        if not raw:
            return None
        if raw in (b"\r\n", b"\n"):
            break
        line = raw.decode("utf-8", errors="replace").strip()
        if not line:
            break
        if ":" not in line:
            return json.loads(line)
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    length = int(headers.get("content-length") or "0")
    body = sys.stdin.buffer.read(length) if length else b"{}"
    return json.loads(body.decode("utf-8"))


def _record(name: str, arguments: dict[str, Any]) -> None:
    raw = os.environ.get("GCS_CHROME_DEVTOOLS_FAKE_LOG", "").strip()
    if not raw:
        return
    path = Path(raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {"name": name, "arguments": arguments, "pid": os.getpid()}
            )
            + "\n"
        )


def _text(text: str, is_error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        arguments = {}
    _record(name, arguments)
    if name == "navigate_page":
        url = str(arguments.get("url") or "").strip()
        if not url:
            return _text("url is required for navigate_page", True)
        return _text(f"Navigated to {url}")
    if name == "new_page":
        url = str(arguments.get("url") or PLAYTEST_URL)
        return _text(f"Opened {url}")
    if name == "list_pages":
        return _text("pages=[] (fake; no live Chrome)")
    if name == "take_screenshot":
        return _text("screenshot omitted (fake; no live Chrome)")
    if name == "take_snapshot":
        return _text("snapshot omitted (fake; no live Chrome)")
    return _text(f"unknown tool: {name}", True)


def handle(msg: dict[str, Any]) -> dict[str, Any] | None:
    method = msg.get("method")
    req_id = msg.get("id")
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": PROTOCOL,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": "fake"},
            },
        }
    if method == "notifications/initialized" or method == "initialized":
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools()}}
    if method == "tools/call":
        params = msg.get("params") or {}
        name = str(params.get("name") or "")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            arguments = {}
        return {"jsonrpc": "2.0", "id": req_id, "result": call_tool(name, arguments)}
    if req_id is None:
        return None
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"method not found: {method}"},
    }


def main() -> int:
    while True:
        try:
            msg = read_message()
        except json.JSONDecodeError as exc:
            write_message(
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}}
            )
            continue
        if msg is None:
            return 0
        reply = handle(msg)
        if reply is not None:
            write_message(reply)


if __name__ == "__main__":
    raise SystemExit(main())
