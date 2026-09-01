#!/usr/bin/env python3
"""Fake grok agent serve: ACP JSON-RPC over a stdlib WebSocket.

GROW wake FAT uses this as the live serve pid. Inbox mail must land as
ACP ``session/prompt`` on this socket. This process never implements
``grok --resume``. No Hermes. No secrets. Stdlib only.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import signal
import struct
import sys
from pathlib import Path
from typing import Any

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
DEFAULT_STATUS = "STATUS quoting token fat-wake-1. Working."


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


class FakeAcpServe:
    """One listening ACP websocket. Journal is the FAT evidence."""

    def __init__(
        self,
        *,
        journal: Path,
        session_id: str,
        status_text: str,
    ) -> None:
        self.journal_path = journal
        self.session_id = session_id
        self.status_text = status_text
        self.port = 0
        self.pid = os.getpid()
        self.methods: list[str] = []
        self.prompts: list[str] = []
        self.session_ids: list[str] = []
        self._lock = asyncio.Lock()

    def snapshot(self) -> dict[str, Any]:
        return {
            "pid": self.pid,
            "port": self.port,
            "methods": list(self.methods),
            "prompts": list(self.prompts),
            "session_ids": list(self.session_ids),
            "resume_seen": False,
        }

    async def record(self, method: str, **extra: Any) -> None:
        async with self._lock:
            self.methods.append(method)
            if method == "session/prompt":
                self.prompts.append(str(extra.get("text") or ""))
            if method in ("session/load", "session/new") and extra.get("session_id"):
                self.session_ids.append(str(extra["session_id"]))
            _atomic_json(self.journal_path, self.snapshot())


async def _read_http_headers(reader: asyncio.StreamReader) -> bytes:
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = await asyncio.wait_for(reader.read(1024), timeout=2.0)
        if not chunk:
            break
        buf += chunk
        if len(buf) > 64_000:
            raise ConnectionError("headers too large")
    return buf


def _header_value(headers: bytes, name: str) -> str:
    target = name.lower().encode("ascii") + b":"
    for raw in headers.split(b"\r\n"):
        low = raw.lower()
        if low.startswith(target):
            return raw.split(b":", 1)[1].strip().decode("ascii", errors="replace")
    return ""


async def _read_frame(reader: asyncio.StreamReader) -> tuple[int, bytes]:
    h = await reader.readexactly(2)
    opcode = h[0] & 0x0F
    masked = (h[1] & 0x80) != 0
    ln = h[1] & 0x7F
    if ln == 126:
        (ln,) = struct.unpack("!H", await reader.readexactly(2))
    elif ln == 127:
        (ln,) = struct.unpack("!Q", await reader.readexactly(8))
    mask = await reader.readexactly(4) if masked else b""
    payload = await reader.readexactly(ln)
    if masked:
        payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    return opcode, payload


async def _send_frame(writer: asyncio.StreamWriter, opcode: int, payload: bytes) -> None:
    header = bytearray([0x80 | (opcode & 0x0F)])
    n = len(payload)
    if n < 126:
        header.append(n)
    elif n < 65536:
        header.append(126)
        header.extend(struct.pack("!H", n))
    else:
        header.append(127)
        header.extend(struct.pack("!Q", n))
    writer.write(header + payload)
    await writer.drain()


async def _send_text(writer: asyncio.StreamWriter, obj: dict[str, Any]) -> None:
    await _send_frame(writer, 0x1, json.dumps(obj, ensure_ascii=False).encode("utf-8"))


def _prompt_text(params: dict[str, Any]) -> str:
    bits: list[str] = []
    prompt = params.get("prompt")
    if isinstance(prompt, list):
        for part in prompt:
            if isinstance(part, dict) and part.get("text") is not None:
                bits.append(str(part.get("text")))
    return "\n".join(bits)


async def _handle(
    serve: FakeAcpServe,
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    try:
        raw = await _read_http_headers(reader)
        if b"upgrade: websocket" not in raw.lower():
            return
        key = _header_value(raw, "Sec-WebSocket-Key")
        if not key:
            return
        digest = hashlib.sha1((key + WS_GUID).encode("ascii")).digest()
        accept = base64.b64encode(digest).decode("ascii")
        writer.write(
            (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept}\r\n"
                "\r\n"
            ).encode("ascii")
        )
        await writer.drain()
        while True:
            opcode, payload = await _read_frame(reader)
            if opcode == 0x8:
                await _send_frame(writer, 0x8, b"")
                return
            if opcode == 0x9:
                await _send_frame(writer, 0xA, payload)
                continue
            if opcode not in (0x1, 0x0):
                continue
            try:
                msg = json.loads(payload.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if not isinstance(msg, dict):
                continue
            await _dispatch_rpc(serve, writer, msg)
    except (asyncio.IncompleteReadError, asyncio.TimeoutError, ConnectionError, OSError):
        return
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            return


async def _dispatch_rpc(
    serve: FakeAcpServe,
    writer: asyncio.StreamWriter,
    msg: dict[str, Any],
) -> None:
    method = str(msg.get("method") or "")
    rid = msg.get("id")
    params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
    if method == "initialize":
        await serve.record(method)
        await _send_text(
            writer,
            {
                "jsonrpc": "2.0",
                "id": rid,
                "result": {
                    "protocolVersion": 1,
                    "authMethods": [{"id": "cached_token", "name": "cached_token"}],
                },
            },
        )
        return
    if method == "authenticate":
        await serve.record(method)
        await _send_text(writer, {"jsonrpc": "2.0", "id": rid, "result": {}})
        return
    if method == "session/load":
        sid = str(params.get("sessionId") or serve.session_id)
        await serve.record(method, session_id=sid)
        await _send_text(writer, {"jsonrpc": "2.0", "id": rid, "result": {}})
        return
    if method == "session/new":
        await serve.record(method, session_id=serve.session_id)
        await _send_text(
            writer,
            {"jsonrpc": "2.0", "id": rid, "result": {"sessionId": serve.session_id}},
        )
        return
    if method == "session/prompt":
        text = _prompt_text(params)
        sid = str(params.get("sessionId") or "")
        await serve.record(method, text=text, session_id=sid)
        await _send_text(
            writer,
            {
                "jsonrpc": "2.0",
                "method": "session/update",
                "params": {
                    "update": {
                        "sessionUpdate": "agent_message_chunk",
                        "content": {"text": serve.status_text},
                    }
                },
            },
        )
        await _send_text(writer, {"jsonrpc": "2.0", "id": rid, "result": {}})
        return
    if method == "session/cancel":
        await serve.record(method)
        if rid is not None:
            await _send_text(writer, {"jsonrpc": "2.0", "id": rid, "result": {}})
        return
    if rid is not None:
        await _send_text(
            writer,
            {
                "jsonrpc": "2.0",
                "id": rid,
                "error": {"code": -32601, "message": f"unknown method {method}"},
            },
        )


async def _run(args: argparse.Namespace) -> int:
    serve = FakeAcpServe(
        journal=Path(args.journal),
        session_id=args.session,
        status_text=args.status_text,
    )
    host, port_s = args.bind.rsplit(":", 1)
    bind_port = int(port_s)

    async def on_connect(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await _handle(serve, reader, writer)

    server = await asyncio.start_server(on_connect, host, bind_port)
    serve.port = int(server.sockets[0].getsockname()[1])
    _atomic_json(serve.journal_path, serve.snapshot())
    ready = f"FAKE_ACP_READY port={serve.port} pid={serve.pid}\n"
    sys.stdout.write(ready)
    sys.stdout.flush()
    if args.ready:
        Path(args.ready).write_text(ready, encoding="utf-8")

    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stopping.set)

    async with server:
        await stopping.wait()
        server.close()
        await server.wait_closed()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Fake ACP grok agent serve for GROW wake FAT")
    parser.add_argument("--bind", default="127.0.0.1:0", help="host:port (port 0 = ephemeral)")
    parser.add_argument("--journal", required=True, help="JSON evidence path")
    parser.add_argument("--ready", default="", help="Write FAKE_ACP_READY here when listening")
    parser.add_argument("--session", default="sess-pinned-grow-fat", help="Pinned ACP session id")
    parser.add_argument("--status-text", default=DEFAULT_STATUS, help="STATUS chunk after session/prompt")
    args = parser.parse_args()
    try:
        return asyncio.run(_run(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
