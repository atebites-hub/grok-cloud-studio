#!/usr/bin/env python3
"""Inject a prompt into a per-seat grok agent serve (ACP over WebSocket).

Usage:
  acp_inject.py <seat> <extra-text...>
  acp_inject.py --seat <seat> --file <path>
  acp_inject.py --seat <seat> --stdin

Reads .a2a-state/<seat>/{acp.url,acp.secret,acp.session}.
Persists session id after session/new. Prefer session/load on later injects.
Stdlib + optional websockets; falls back to a minimal WS client.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import secrets
import struct
import sys
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

ROOT = Path(os.environ.get("GCS_ROOT", Path(__file__).resolve().parents[2]))
STATE_DIR = Path(os.environ.get("GCS_A2A_STATE", str(ROOT / ".a2a-state")))
DEFAULT_TIMEOUT = float(os.environ.get("GCS_ACP_INJECT_TIMEOUT", "900"))

_LIB_DIR = Path(__file__).resolve().parents[1] / "a2a"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
from lib import seat_acp_port  # noqa: E402

try:
    import websockets  # type: ignore
    from websockets.client import connect as ws_connect  # type: ignore

    _HAS_WEBSOCKETS = True
except ImportError:
    _HAS_WEBSOCKETS = False


def _seat_dir(seat: str) -> Path:
    d = STATE_DIR / seat
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _write_text(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text.rstrip() + "\n", encoding="utf-8")
    tmp.replace(path)


def _ensure_url(seat: str) -> str:
    sd = _seat_dir(seat)
    url_path = sd / "acp.url"
    secret_path = sd / "acp.secret"
    if url_path.is_file():
        return _read_text(url_path)
    if not secret_path.is_file():
        raise SystemExit(f"ACP_INJECT_FAIL seat={seat} missing acp.url/acp.secret (daemon not started?)")
    secret = _read_text(secret_path)
    try:
        port = seat_acp_port(seat, ROOT)
    except KeyError as exc:
        raise SystemExit(f"ACP_INJECT_FAIL seat={seat} {exc}") from exc
    url = f"ws://127.0.0.1:{port}/ws?server-key={secret}"
    _write_text(url_path, url)
    return url


class _StdlibWs:
    """Minimal client for text JSON-RPC frames (RFC6455)."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self._reader = reader
        self._writer = writer

    @classmethod
    async def connect(cls, url: str) -> "_StdlibWs":
        parsed = urlparse(url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "wss" else 80)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        reader, writer = await asyncio.open_connection(host, port)
        key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        writer.write(req.encode("ascii"))
        await writer.drain()
        # Read status line + headers
        status = await reader.readline()
        if b"101" not in status:
            rest = await reader.read(512)
            raise ConnectionError(f"WS handshake failed: {status!r} {rest[:200]!r}")
        while True:
            line = await reader.readline()
            if line in (b"\r\n", b"\n", b""):
                break
        return cls(reader, writer)

    async def send(self, text: str) -> None:
        data = text.encode("utf-8")
        # Client frames must be masked
        mask = secrets.token_bytes(4)
        header = bytearray()
        header.append(0x81)  # FIN + text
        n = len(data)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", n))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", n))
        header.extend(mask)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        self._writer.write(header + masked)
        await self._writer.drain()

    async def recv(self) -> str:
        while True:
            h = await self._reader.readexactly(2)
            fin = (h[0] & 0x80) != 0
            opcode = h[0] & 0x0F
            masked = (h[1] & 0x80) != 0
            ln = h[1] & 0x7F
            if ln == 126:
                (ln,) = struct.unpack("!H", await self._reader.readexactly(2))
            elif ln == 127:
                (ln,) = struct.unpack("!Q", await self._reader.readexactly(8))
            mask = await self._reader.readexactly(4) if masked else b""
            payload = await self._reader.readexactly(ln)
            if masked:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            if opcode == 0x8:  # close
                raise ConnectionError("WS closed by peer")
            if opcode == 0x9:  # ping → pong
                # send pong
                frame = bytearray([0x8A, 0x80 | len(payload)])
                m = secrets.token_bytes(4)
                frame.extend(m)
                frame.extend(bytes(b ^ m[i % 4] for i, b in enumerate(payload)))
                self._writer.write(frame)
                await self._writer.drain()
                continue
            if opcode in (0x1, 0x0):  # text / continuation
                text = payload.decode("utf-8")
                if not fin:
                    # accumulate (rare for JSON-RPC)
                    more = [text]
                    while True:
                        part = await self.recv()
                        more.append(part)
                        break
                    return "".join(more)
                return text
            # binary / other — ignore
            continue

    async def close(self) -> None:
        try:
            self._writer.close()
            await self._writer.wait_closed()
        except Exception:
            pass


class AcpClient:
    def __init__(self, url: str, cwd: str):
        self.url = url
        self.cwd = cwd
        self._ws: Any = None
        self._next_id = 1
        self._pending: dict[int, asyncio.Future] = {}
        self._reader_task: Optional[asyncio.Task] = None
        self._chunks: list[str] = []
        self._prompt_done: Optional[asyncio.Future] = None
        self._use_stdlib = not _HAS_WEBSOCKETS
        self._echo_chunks = False

    async def connect(self) -> None:
        if _HAS_WEBSOCKETS:
            self._ws = await ws_connect(self.url, max_size=16_000_000)
            self._use_stdlib = False
        else:
            self._ws = await _StdlibWs.connect(self.url)
            self._use_stdlib = True
        self._reader_task = asyncio.create_task(self._read_loop())

    async def close(self) -> None:
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass

    async def _send_raw(self, obj: dict[str, Any]) -> None:
        data = json.dumps(obj, ensure_ascii=False)
        await self._ws.send(data)

    async def _read_loop(self) -> None:
        try:
            while True:
                raw = await self._ws.recv()
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="replace")
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                mid = msg.get("id")
                if mid is not None and mid in self._pending:
                    fut = self._pending.pop(mid)
                    if not fut.done():
                        fut.set_result(msg)
                    continue
                method = msg.get("method")
                if method == "session/update":
                    params = msg.get("params") or {}
                    update = params.get("update") or {}
                    if update.get("sessionUpdate") == "agent_message_chunk":
                        t = ((update.get("content") or {}).get("text")) or ""
                        if t and self._echo_chunks:
                            self._chunks.append(t)
                            sys.stdout.write(t)
                            sys.stdout.flush()
                elif method in ("_x.ai/session/prompt_complete",):
                    # sometimes arrives before JSON-RPC result
                    pass
                # Permission requests — auto-approve if asked
                elif method and "request_permission" in method:
                    req_id = msg.get("id")
                    if req_id is not None:
                        options = ((msg.get("params") or {}).get("options")) or []
                        oid = "allow-always"
                        for o in options:
                            if isinstance(o, dict) and o.get("optionId"):
                                oid = str(o["optionId"])
                                break
                        await self._send_raw(
                            {
                                "jsonrpc": "2.0",
                                "id": req_id,
                                "result": {
                                    "outcome": {
                                        "outcome": "selected",
                                        "optionId": oid,
                                    }
                                },
                            }
                        )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(e)
            self._pending.clear()
            if self._prompt_done and not self._prompt_done.done():
                self._prompt_done.set_exception(e)

    async def request(self, method: str, params: dict[str, Any], timeout: float = 60.0) -> dict[str, Any]:
        rid = self._next_id
        self._next_id += 1
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[rid] = fut
        await self._send_raw({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        try:
            msg = await asyncio.wait_for(fut, timeout=timeout)
        except Exception:
            self._pending.pop(rid, None)
            raise
        if "error" in msg:
            raise RuntimeError(f"{method} error: {msg['error']}")
        return msg.get("result") or {}

    async def initialize(self) -> dict[str, Any]:
        return await self.request(
            "initialize",
            {
                "protocolVersion": 1,
                "clientCapabilities": {
                    "fs": {"readTextFile": True, "writeTextFile": True},
                    "terminal": True,
                },
                "clientInfo": {"name": "gcs-a2a-acp-inject", "version": "0.1"},
            },
            timeout=60.0,
        )

    async def session_new(self, system_prompt: Optional[str] = None) -> str:
        meta: dict[str, Any] = {"yoloMode": True}
        if system_prompt:
            meta["systemPromptOverride"] = system_prompt
        result = await self.request(
            "session/new",
            {"cwd": self.cwd, "mcpServers": [], "_meta": meta},
            timeout=120.0,
        )
        sid = result.get("sessionId")
        if not sid:
            raise RuntimeError(f"session/new missing sessionId: {result}")
        return str(sid)

    async def session_load(self, session_id: str) -> None:
        await self.request(
            "session/load",
            {
                "sessionId": session_id,
                "cwd": self.cwd,
                "mcpServers": [],
                "_meta": {"yoloMode": True},
            },
            timeout=120.0,
        )

    async def session_prompt(self, session_id: str, text: str, timeout: float) -> str:
        self._chunks = []
        self._echo_chunks = True
        rid = self._next_id
        self._next_id += 1
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[rid] = fut
        await self._send_raw(
            {
                "jsonrpc": "2.0",
                "id": rid,
                "method": "session/prompt",
                "params": {
                    "sessionId": session_id,
                    "prompt": [{"type": "text", "text": text}],
                },
            }
        )
        try:
            msg = await asyncio.wait_for(fut, timeout=timeout)
        except Exception:
            self._pending.pop(rid, None)
            raise
        if "error" in msg:
            self._echo_chunks = False
            raise RuntimeError(f"session/prompt error: {msg['error']}")
        self._echo_chunks = False
        return "".join(self._chunks)


async def inject(seat: str, prompt: str, *, timeout: float, force_new: bool = False) -> int:
    url = _ensure_url(seat)
    sd = _seat_dir(seat)
    session_path = sd / "acp.session"
    cwd = str(ROOT)

    client = AcpClient(url, cwd)
    await client.connect()
    try:
        await client.initialize()
        session_id: Optional[str] = None
        reused = False
        if not force_new and session_path.is_file():
            prior = _read_text(session_path)
            if prior:
                try:
                    await client.session_load(prior)
                    session_id = prior
                    reused = True
                except Exception as e:
                    print(f"ACP_INJECT_SESSION_LOAD_FAIL seat={seat} err={e}; creating new", file=sys.stderr)
                    session_id = None
        if not session_id:
            # Prefer agent-profile baked into daemon; optional override empty.
            session_id = await client.session_new()
            _write_text(session_path, session_id)
            reused = False

        print(
            f"ACP_INJECT_BEGIN seat={seat} session={session_id} reused={int(reused)} url={url.split('?')[0]}",
            flush=True,
        )
        # Wrap as EXTRA TURN so Directors match footer expectations
        full = (
            "=== EXTRA TURN INSTRUCTIONS (ACP inject / persistent seat) ===\n"
            f"{prompt.rstrip()}\n"
        )
        reply = await client.session_prompt(session_id, full, timeout=timeout)
        if reply and not reply.endswith("\n"):
            sys.stdout.write("\n")
            sys.stdout.flush()
        print(
            f"ACP_INJECT_OK seat={seat} session={session_id} reused={int(reused)} chars={len(reply)}",
            flush=True,
        )
        return 0
    finally:
        await client.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Inject prompt into seat ACP daemon")
    parser.add_argument("seat_pos", nargs="?", help="Seat name (positional)")
    parser.add_argument("extra", nargs="*", help="Extra prompt text")
    parser.add_argument("--seat", default="", help="Seat name")
    parser.add_argument("--file", default="", help="Read prompt from file")
    parser.add_argument("--stdin", action="store_true", help="Read prompt from stdin")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--force-new-session", action="store_true")
    args = parser.parse_args()

    seat = (args.seat or args.seat_pos or "").strip()
    if not seat:
        parser.error("seat required")
    seat = seat.lower().replace("_", "-")

    if args.stdin:
        prompt = sys.stdin.read()
    elif args.file:
        prompt = Path(args.file).read_text(encoding="utf-8")
    elif args.extra:
        prompt = " ".join(args.extra)
    elif args.seat_pos and not args.extra:
        # allow: acp_inject.py --seat floor --file x  already handled; else need text
        parser.error("prompt text required (args, --file, or --stdin)")
    else:
        prompt = " ".join(args.extra)

    if not prompt.strip():
        print("ACP_INJECT_FAIL empty prompt", file=sys.stderr)
        return 2

    try:
        return asyncio.run(
            inject(seat, prompt, timeout=args.timeout, force_new=args.force_new_session)
        )
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        print(f"ACP_INJECT_FAIL seat={seat} err={e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
