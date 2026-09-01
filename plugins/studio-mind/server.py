#!/usr/bin/env python3
"""Studio-mind MCP: ticket, a2a_send, cloud_launch.

Grok is the agent. This process only exposes tools. Python mind.py does not
parse grok stdout for function calls. Installed into seat GROK_HOME with
`grok plugin install --trust` (not `--plugin-dir` on headless grok).
The stdio handshake must not close on initialize.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


def _resolve_gcs_root() -> Path:
    """Repo root after `grok plugin install` copies this file into GROK_HOME.

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
    here = Path(__file__).resolve().parent
    for cand in (here, *here.parents):
        if (cand / "scripts" / "mcp" / "gcs_mcp.py").is_file() and (
            cand / "scripts" / "directors" / "mind.py"
        ).is_file():
            return cand
    return Path(__file__).resolve().parents[2]


ROOT = _resolve_gcs_root()
os.environ.setdefault("GCS_ROOT", str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "mcp"))
sys.path.insert(0, str(ROOT / "scripts" / "directors"))

from gcs_mcp import read_message, write_message  # noqa: E402
from mind import PLUGINS, call_plugin  # noqa: E402

PROTOCOL = "2024-11-05"


def tools() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name, plugin in PLUGINS.items():
        out.append(
            {
                "name": name,
                "description": (plugin.call.__doc__ or name).strip(),
                "inputSchema": plugin.schema,
            }
        )
    return out


def handle(msg: dict[str, Any]) -> dict[str, Any] | None:
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
                "serverInfo": {"name": "studio-mind", "version": "1.0.0"},
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
        text = call_plugin(name, arguments)
        is_error = text.startswith("PLUGIN_ERR")
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": text}],
                "isError": is_error,
            },
        }
    if req_id is None:
        return None
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"method not found: {method}"},
    }


def main() -> int:
    # Stay connected after initialize. EOF on stdin is the only shutdown.
    # notifications/initialized is silent; tools/list uses the same pid.
    ndjson = os.environ.get("GCS_MCP_NDJSON") == "1"
    while True:
        try:
            msg = read_message(ndjson)
        except Exception as exc:
            write_message(
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": str(exc)},
                },
                ndjson,
            )
            continue
        if msg is None:
            return 0
        reply = handle(msg)
        if reply is not None:
            write_message(reply, ndjson)


if __name__ == "__main__":
    raise SystemExit(main())
