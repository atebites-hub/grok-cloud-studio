#!/usr/bin/env python3
"""Stdlib JSON-RPC stdio MCP server for Grok Cloud Studio.

Planes:
  --plane a2a     tools: a2a_list_seats, a2a_send
  --plane cloud   tools: cloud_launch, cloud_status, cloud_result
  --plane all     both (default)

Framing: Content-Length (MCP) or NDJSON when GCS_MCP_NDJSON=1.
A first stdin line that starts with `{` latches NDJSON for the session
so initialize still replies when the client omits Content-Length.
Initialize is not shutdown: stay on the pipe until stdin EOF.
Never prints credentials.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def resolve_gcs_root(start: Path | None = None) -> Path:
    """Repo root after grok plugin install copies a plugin off the tree.

    Prefer GCS_ROOT, then GROK_HOME/gcs-root (stamped by
    install_mind_grok_plugins), then a walk-up looking for scripts/mcp.
    """
    env = (os.environ.get("GCS_ROOT") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    grok_home = (os.environ.get("GROK_HOME") or "").strip()
    if grok_home:
        stamp = Path(grok_home).expanduser() / "gcs-root"
        try:
            text = stamp.read_text(encoding="utf-8").strip()
        except OSError:
            text = ""
        if text:
            return Path(text).expanduser().resolve()
    here = (start or Path(__file__).resolve()).parent
    for cand in (here, *here.parents):
        if (cand / "scripts" / "mcp" / "gcs_mcp.py").is_file():
            return cand
    return Path(__file__).resolve().parents[2]


ROOT = resolve_gcs_root()
_LIB_DIR = ROOT / "scripts" / "a2a"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
import lib  # noqa: E402

PROTOCOL = "2024-11-05"
SERVER_NAME = "gcs-mcp"
SERVER_VERSION = "1.0.0"
# None = not yet seen a frame. First `{` line latches NDJSON for the session
# so initialize replies match the client even when GCS_MCP_NDJSON is unset.
_stdio_ndjson: bool | None = None


def a2a_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "a2a_list_seats",
            "description": "List Grok Cloud Studio A2A seats from docs/a2a/registry.json.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "a2a_send",
            "description": "Send a text ping to a seat via the local A2A hub (scripts/a2a/send.sh).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "seat": {"type": "string", "description": "Seat id, e.g. floor or ops"},
                    "text": {"type": "string", "description": "Message body"},
                },
                "required": ["seat", "text"],
                "additionalProperties": False,
            },
        },
    ]


def cloud_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "cloud_launch",
            "description": (
                "Launch a Cursor Cloud Extra High agent. Requires GCS_CLOUD_REPO or "
                "CLOUD_REPO_URL. Never returns API keys."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "name": {"type": "string", "description": "Short agent name"},
                },
                "required": ["prompt"],
                "additionalProperties": False,
            },
        },
        {
            "name": "cloud_status",
            "description": "Compact status for a Cursor Cloud agent bc-id.",
            "inputSchema": {
                "type": "object",
                "properties": {"id": {"type": "string", "description": "bc-id"}},
                "required": ["id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "cloud_result",
            "description": "Result JSON for a Cursor Cloud agent bc-id (prUrl, runStatus, summary).",
            "inputSchema": {
                "type": "object",
                "properties": {"id": {"type": "string", "description": "bc-id"}},
                "required": ["id"],
                "additionalProperties": False,
            },
        },
    ]


def tools_for(plane: str) -> list[dict[str, Any]]:
    if plane == "a2a":
        return a2a_tools()
    if plane == "cloud":
        return cloud_tools()
    return a2a_tools() + cloud_tools()


def _run(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["GCS_ROOT"] = str(ROOT)
    return subprocess.run(
        args,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=env,
    )


def _text_result(text: str, is_error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "a2a_list_seats":
        seats = list(lib.launch_seats(ROOT))
        skipped = sorted(lib.skip_seats(ROOT))
        return _text_result(json.dumps({"seats": seats, "skipSeats": skipped}, indent=2))
    if name == "a2a_send":
        seat = str(arguments.get("seat") or "").strip()
        text = str(arguments.get("text") or "")
        if not seat or not text:
            return _text_result("seat and text are required", True)
        proc = _run(["bash", str(ROOT / "scripts" / "a2a" / "send.sh"), seat, text], timeout=60)
        out = (proc.stdout or "") + (proc.stderr or "")
        return _text_result(out.strip() or f"rc={proc.returncode}", proc.returncode != 0)
    if name == "cloud_launch":
        prompt = str(arguments.get("prompt") or "").strip()
        agent_name = str(arguments.get("name") or "").strip()
        if not prompt:
            return _text_result("prompt is required", True)
        cmd = ["bash", str(ROOT / "scripts" / "launch-cloud-extra-high.sh")]
        if agent_name:
            cmd.extend(["--name", agent_name])
        cmd.append(prompt)
        proc = _run(cmd, timeout=180)
        out = (proc.stdout or "") + (proc.stderr or "")
        return _text_result(out.strip() or f"rc={proc.returncode}", proc.returncode != 0)
    if name == "cloud_status":
        agent_id = str(arguments.get("id") or "").strip()
        if not agent_id:
            return _text_result("id is required", True)
        proc = _run(["bash", str(ROOT / "scripts" / "cloud" / "status-cloud-agent.sh"), agent_id])
        out = (proc.stdout or "") + (proc.stderr or "")
        return _text_result(out.strip() or f"rc={proc.returncode}", proc.returncode != 0)
    if name == "cloud_result":
        agent_id = str(arguments.get("id") or "").strip()
        if not agent_id:
            return _text_result("id is required", True)
        proc = _run(["bash", str(ROOT / "scripts" / "cloud" / "result-cloud-agent.sh"), agent_id])
        out = (proc.stdout or "") + (proc.stderr or "")
        return _text_result(out.strip() or f"rc={proc.returncode}", proc.returncode != 0)
    return _text_result(f"unknown tool: {name}", True)


def handle(msg: dict[str, Any], plane: str) -> dict[str, Any] | None:
    method = msg.get("method")
    req_id = msg.get("id")
    if method == "initialize":
        # Reply and keep serving. Do not close stdio after this result.
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": PROTOCOL,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        }
    if method == "notifications/initialized" or method == "initialized":
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools_for(plane)}}
    if method == "tools/call":
        params = msg.get("params") or {}
        name = str(params.get("name") or "")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            arguments = {}
        result = call_tool(name, arguments)
        return {"jsonrpc": "2.0", "id": req_id, "result": result}
    if req_id is None:
        return None
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"method not found: {method}"},
    }


def write_message(obj: dict[str, Any], ndjson: bool) -> None:
    use_ndjson = _stdio_ndjson if _stdio_ndjson is not None else ndjson
    blob = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    if use_ndjson:
        sys.stdout.buffer.write(blob + b"\n")
    else:
        header = f"Content-Length: {len(blob)}\r\n\r\n".encode("ascii")
        sys.stdout.buffer.write(header + blob)
    sys.stdout.buffer.flush()


def read_message(ndjson: bool) -> dict[str, Any] | None:
    global _stdio_ndjson
    if _stdio_ndjson is True or (ndjson and _stdio_ndjson is None):
        _stdio_ndjson = True
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        return json.loads(line.decode("utf-8"))
    headers: dict[str, str] = {}
    first = True
    while True:
        raw = sys.stdin.buffer.readline()
        if not raw:
            return None
        if first:
            first = False
            if raw.lstrip().startswith(b"{"):
                _stdio_ndjson = True
                return json.loads(raw.decode("utf-8"))
            _stdio_ndjson = False
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Grok Cloud Studio MCP stdio server")
    parser.add_argument("--plane", choices=("a2a", "cloud", "all"), default="all")
    parser.add_argument("--ndjson", action="store_true")
    args = parser.parse_args(argv)
    ndjson = args.ndjson or os.environ.get("GCS_MCP_NDJSON") == "1"
    while True:
        try:
            msg = read_message(ndjson)
        except json.JSONDecodeError as exc:
            write_message(
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}},
                ndjson,
            )
            continue
        if msg is None:
            return 0
        reply = handle(msg, args.plane)
        if reply is not None:
            write_message(reply, ndjson)


if __name__ == "__main__":
    raise SystemExit(main())
