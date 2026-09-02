#!/usr/bin/env python3
"""Grok-catalog MCP client: what grok does with GROK_HOME/config.toml.

A Grok Build mind (qa-a) calls chrome-devtools via this catalog: grok loads
`[mcp_servers.chrome-devtools]`, starts stdio `npx -y chrome-devtools-mcp@latest`,
then `tools/call` `navigate_page` for http://127.0.0.1:5173/.

This module is the pytest stand-in for grok's native MCP client. mind.py does
not import it — Python is mailbox + pin + stay-up, not a second browser loop.

Do not copy GROK_HOME into Cursor `.cursor/mcp.json`. Two catalogs.

Stdlib only. No live Chrome in unit tests (bind a fake stdio server).
"""
from __future__ import annotations

import json
import os
import select
import subprocess
import sys
import time
import tomllib
from pathlib import Path
from typing import Any

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))
from seat_grok_mcp import (  # noqa: E402
    CHROME_DEVTOOLS_SERVER,
    chrome_devtools_open_client_tool,
    chrome_devtools_screenshot_tool,
)

PROTOCOL = "2024-11-05"
CLIENT_NAME = "gcs-grok-catalog"
CLIENT_VERSION = "1.0.0"
DEFAULT_TIMEOUT = 10.0


def load_mcp_servers(grok_home: Path) -> dict[str, Any]:
    cfg = Path(grok_home) / "config.toml"
    if not cfg.is_file():
        raise FileNotFoundError(f"GROK_HOME config.toml missing: {cfg}")
    parsed = tomllib.loads(cfg.read_text(encoding="utf-8"))
    servers = parsed.get("mcp_servers") or {}
    if not isinstance(servers, dict):
        raise ValueError(f"GROK_HOME config.toml missing [mcp_servers]: {cfg}")
    return servers


def mcp_stdio_argv(spec: dict[str, Any]) -> list[str]:
    command = str(spec.get("command") or "").strip()
    if not command:
        raise ValueError("mcp server missing command")
    raw_args = spec.get("args") or []
    if not isinstance(raw_args, list):
        raise ValueError("mcp server args must be a list")
    return [command, *[str(a) for a in raw_args]]


def _deadline_remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("MCP stdio timeout")
    return remaining


def _fd(stream: Any) -> int:
    return int(stream.fileno())


def _read_exact(stream: Any, n: int, deadline: float) -> bytes:
    buf = bytearray()
    fd = _fd(stream)
    while len(buf) < n:
        remaining = _deadline_remaining(deadline)
        ready, _, _ = select.select([fd], [], [], remaining)
        if not ready:
            raise TimeoutError("MCP stdio timeout")
        chunk = os.read(fd, n - len(buf))
        if not chunk:
            raise RuntimeError("MCP stdout closed")
        buf.extend(chunk)
    return bytes(buf)


def _readline(stream: Any, deadline: float) -> bytes:
    buf = bytearray()
    fd = _fd(stream)
    while True:
        remaining = _deadline_remaining(deadline)
        ready, _, _ = select.select([fd], [], [], remaining)
        if not ready:
            raise TimeoutError("MCP stdio timeout")
        ch = os.read(fd, 1)
        if not ch:
            raise RuntimeError("MCP stdout closed")
        buf.extend(ch)
        if buf.endswith(b"\n"):
            return bytes(buf)


def _write_message(proc: subprocess.Popen[bytes], obj: dict[str, Any]) -> None:
    if proc.stdin is None:
        raise RuntimeError("MCP stdin missing")
    blob = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    proc.stdin.write(f"Content-Length: {len(blob)}\r\n\r\n".encode("ascii"))
    proc.stdin.write(blob)
    proc.stdin.flush()


def _read_message(proc: subprocess.Popen[bytes], deadline: float) -> dict[str, Any]:
    if proc.stdout is None:
        raise RuntimeError("MCP stdout missing")
    headers: dict[str, str] = {}
    while True:
        line = _readline(proc.stdout, deadline)
        if line in (b"\r\n", b"\n"):
            break
        text = line.decode("utf-8", errors="replace").strip()
        if not text:
            break
        if ":" not in text:
            return json.loads(text)
        key, value = text.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    length = int(headers.get("content-length") or "0")
    body = _read_exact(proc.stdout, length, deadline) if length else b"{}"
    return json.loads(body.decode("utf-8"))


class GrokCatalogSession:
    """One stdio MCP session against a GROK_HOME catalog server."""

    def __init__(
        self,
        grok_home: Path,
        server: str,
        *,
        env: dict[str, str] | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.grok_home = Path(grok_home)
        self.server = server
        self.timeout = timeout
        spec = load_mcp_servers(self.grok_home).get(server)
        if not isinstance(spec, dict):
            raise KeyError(f"GROK_HOME has no [mcp_servers.{server}]")
        argv = mcp_stdio_argv(spec)
        run_env = dict(env) if env is not None else os.environ.copy()
        run_env.setdefault("GCS_ROOT", str(Path(__file__).resolve().parents[2]))
        run_env.setdefault("PYTHONUNBUFFERED", "1")
        self.proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(self.grok_home),
            env=run_env,
            bufsize=0,
        )
        self._id = 0
        try:
            self._initialize()
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        if self.proc.poll() is not None:
            return
        if self.proc.stdin is not None:
            try:
                self.proc.stdin.close()
            except BrokenPipeError:
                pass
        self.proc.terminate()
        try:
            self.proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.proc.kill()

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _deadline(self) -> float:
        return time.monotonic() + self.timeout

    def _initialize(self) -> None:
        reply = self.request(
            "initialize",
            {
                "protocolVersion": PROTOCOL,
                "capabilities": {},
                "clientInfo": {"name": CLIENT_NAME, "version": CLIENT_VERSION},
            },
        )
        if "error" in reply:
            raise RuntimeError(f"MCP initialize failed: {reply['error']}")
        _write_message(self.proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        req_id = self._next_id()
        msg: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            msg["params"] = params
        _write_message(self.proc, msg)
        return _read_message(self.proc, self._deadline())

    def __enter__(self) -> GrokCatalogSession:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def _rpc_result(reply: dict[str, Any]) -> dict[str, Any]:
    if "error" in reply:
        err = reply.get("error")
        return {
            "isError": True,
            "content": [{"type": "text", "text": json.dumps(err)}],
        }
    result = reply.get("result") or {}
    if not isinstance(result, dict):
        return {"isError": True, "content": [{"type": "text", "text": str(result)}]}
    return result


def list_mcp_tools(
    grok_home: Path,
    server: str,
    *,
    env: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[str]:
    """tools/list against a GROK_HOME catalog server (grok-equivalent)."""
    with GrokCatalogSession(grok_home, server, env=env, timeout=timeout) as session:
        reply = session.request("tools/list")
        tools = (reply.get("result") or {}).get("tools") or []
        names: list[str] = []
        for tool in tools:
            if isinstance(tool, dict) and tool.get("name"):
                names.append(str(tool["name"]))
        return names


def call_mcp_tool(
    grok_home: Path,
    server: str,
    name: str,
    arguments: dict[str, Any] | None = None,
    *,
    env: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """tools/call against a GROK_HOME catalog server (grok-equivalent)."""
    with GrokCatalogSession(grok_home, server, env=env, timeout=timeout) as session:
        reply = session.request(
            "tools/call",
            {"name": name, "arguments": arguments or {}},
        )
        return _rpc_result(reply)


def call_chrome_devtools_navigate_page(
    grok_home: Path,
    url: str | None = None,
    *,
    env: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Grok catalog chrome-devtools navigate_page for visual QA.

    Live grok issues this tools/call. mind.py does not.
    """
    tool = chrome_devtools_open_client_tool(url)
    if tool["server"] != CHROME_DEVTOOLS_SERVER:
        raise RuntimeError("chrome-devtools contract server mismatch")
    return call_mcp_tool(
        grok_home,
        str(tool["server"]),
        str(tool["name"]),
        dict(tool["arguments"]),
        env=env,
        timeout=timeout,
    )


def _tool_names(reply: dict[str, Any]) -> list[str]:
    tools = (reply.get("result") or {}).get("tools") or []
    names: list[str] = []
    for tool in tools:
        if isinstance(tool, dict) and tool.get("name"):
            names.append(str(tool["name"]))
    return names


def _combine_text(*results: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for result in results:
        for item in result.get("content") or []:
            if isinstance(item, dict) and item.get("text"):
                out.append({"type": "text", "text": str(item["text"])})
    return out


def call_chrome_devtools_visual_qa(
    grok_home: Path,
    url: str | None = None,
    *,
    env: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """One grok-catalog session: navigate_page then take_screenshot.

    Visual QA of the playtest origin is not two disconnected MCP processes.
    Live grok keeps one chrome-devtools stdio session. mind.py does not.
    """
    nav_tool = chrome_devtools_open_client_tool(url)
    shot_tool = chrome_devtools_screenshot_tool()
    origin = str((nav_tool.get("arguments") or {}).get("url") or "")
    with GrokCatalogSession(
        grok_home,
        CHROME_DEVTOOLS_SERVER,
        env=env,
        timeout=timeout,
    ) as session:
        names = _tool_names(session.request("tools/list"))
        if "navigate_page" not in names or "take_screenshot" not in names:
            return {
                "isError": True,
                "url": origin,
                "content": [
                    {
                        "type": "text",
                        "text": f"chrome-devtools missing visual QA tools: {names}",
                    }
                ],
            }
        nav = _rpc_result(
            session.request(
                "tools/call",
                {
                    "name": str(nav_tool["name"]),
                    "arguments": dict(nav_tool["arguments"]),
                },
            )
        )
        shot = _rpc_result(
            session.request(
                "tools/call",
                {
                    "name": str(shot_tool["name"]),
                    "arguments": dict(shot_tool["arguments"]),
                },
            )
        )
        errored = bool(nav.get("isError") or shot.get("isError"))
        return {
            "isError": errored,
            "url": origin,
            "navigate_page": nav,
            "take_screenshot": shot,
            "content": _combine_text(nav, shot),
        }


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 2:
        print(
            "usage: grok_catalog_mcp.py GROK_HOME list|navigate|visual [URL]",
            file=sys.stderr,
        )
        return 2
    grok_home = Path(args[0])
    action = args[1]
    if action == "list":
        names = list_mcp_tools(grok_home, CHROME_DEVTOOLS_SERVER)
        print("\n".join(names))
        return 0
    if action == "navigate":
        url = args[2] if len(args) > 2 else None
        result = call_chrome_devtools_navigate_page(grok_home, url)
        print(json.dumps(result))
        return 1 if result.get("isError") else 0
    if action == "visual":
        url = args[2] if len(args) > 2 else None
        result = call_chrome_devtools_visual_qa(grok_home, url)
        print(json.dumps(result))
        return 1 if result.get("isError") else 0
    print(f"unknown action: {action}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
