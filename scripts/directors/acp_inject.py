#!/usr/bin/env python3
"""Inject a prompt into a per-seat grok agent serve (ACP over WebSocket).

Usage:
  acp_inject.py <seat> <extra-text...>
  acp_inject.py --seat <seat> --file <path>
  acp_inject.py --seat <seat> --stdin
  acp_inject.py --seat <seat> --pin-session ...

Reads .a2a-state/<seat>/{acp.url,acp.secret,acp.session}.
Persists session id after session/new. Prefer session/load on later injects.

Leftover dispatch (default): harvest streamed RESULT / PARK_ACK / QA_*_RESULT,
duplex, then session/cancel so the next ping is not start_blocked.

--pin-session: HANDOFF only on this-prompt tool or non-RESULT session/update.
Never 1s silence. Never queue/changed alone. Stay on the websocket after
session/prompt start until HANDOFF or the 30s accept deadline. After
no-accept, remint once (one session/new on the same socket). Do not
session/cancel a handed-off live turn. RESULT-only is duplex, not HANDOFF.

Stdlib + optional websockets; falls back to a minimal WS client.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import importlib.util
import json
import os
import re
import secrets
import struct
import sys
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

ROOT = Path(os.environ.get("GCS_ROOT", Path(__file__).resolve().parents[2]))
STATE_DIR = Path(os.environ.get("GCS_A2A_STATE", str(ROOT / ".a2a-state")))
DEFAULT_TIMEOUT = float(os.environ.get("GCS_ACP_INJECT_TIMEOUT", "180"))
ACCEPT_DEADLINE_SEC = float(os.environ.get("GCS_ACP_ACCEPT_DEADLINE", "30"))

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

RESULT_LINE_RE = re.compile(
    r"^(RESULT|QA_A_RESULT|QA_B_RESULT|PARK_ACK)\b.*$",
    re.MULTILINE,
)
_STATUS_LINE_RE = re.compile(r"^STATUS\b", re.MULTILINE)
_PONG_ONLY_RE = re.compile(r"^\s*(PONG|pong|ok|OK)\s*$")
_WORK_UPDATES = frozenset({"tool_call", "tool_call_update", "agent_thought_chunk"})


def extract_result_line(text: str) -> str | None:
    """Return the last Director contract line, if any."""
    if not text:
        return None
    found: str | None = None
    for match in RESULT_LINE_RE.finditer(text):
        found = match.group(0).strip()
    return found


def pin_accept_wait(timeout: float) -> float:
    """Pin-session waits at most the 30s accept deadline (tests may pass less)."""
    return min(float(timeout), float(ACCEPT_DEADLINE_SEC))


def _work_body_without_result_lines(text: str) -> str:
    """Assistant text excluding RESULT / PARK_ACK / QA_*_RESULT hang-up lines."""
    if not text:
        return ""
    kept: list[str] = []
    for line in str(text).splitlines():
        if RESULT_LINE_RE.match(line.strip()):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def prompt_chunk_is_accept_signal(text: str) -> bool:
    """True when streamed assistant text is a non-RESULT session/update.

    STATUS is accept. RESULT hang-up and PONG are not. Any other non-empty
    body (including short thinking) is accept.
    """
    raw = "" if text is None else str(text)
    if _STATUS_LINE_RE.search(raw):
        return True
    body = _work_body_without_result_lines(raw)
    if not body:
        return False
    if _PONG_ONLY_RE.match(body):
        return False
    return True


def is_handoff_signal(text: str, *, tool_events: int = 0, queued: bool = False) -> bool:
    """HANDOFF only on this-prompt tool or non-RESULT session/update.

    queue/changed alone is never HANDOFF. Leftover tools with empty or
    RESULT-only text are not this-prompt. Silence is never HANDOFF.
    """
    del queued  # tracked for logs; never a HANDOFF signal by itself
    raw = "" if text is None else str(text)
    if prompt_chunk_is_accept_signal(raw):
        return True
    body = _work_body_without_result_lines(raw)
    if tool_events > 0 and body and not _PONG_ONLY_RE.match(body):
        return True
    return False


def stream_is_hangup_only(text: str, *, tool_events: int = 0) -> bool:
    """RESULT-only or PONG-only. Leftover tools without RESULT are not hang-up."""
    raw = "" if text is None else str(text)
    if is_handoff_signal(raw, tool_events=tool_events):
        return False
    body = _work_body_without_result_lines(raw)
    if extract_result_line(raw) and not body:
        return True
    if tool_events > 0:
        return False
    stripped = (body or raw).strip()
    return bool(stripped and _PONG_ONLY_RE.match(stripped))


def _duplex_after_inject(seat: str, prompt: str, reply: str) -> None:
    path = ROOT / "scripts" / "a2a" / "duplex.py"
    if not path.is_file():
        return
    spec = importlib.util.spec_from_file_location("gcs_a2a_duplex", path)
    if spec is None or spec.loader is None:
        return
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    record = mod.record_from_env(prompt)
    if not record.get("taskId"):
        return
    try:
        result = mod.duplex_from_output(
            state_dir=STATE_DIR,
            seat=seat,
            record=record,
            output_text=reply,
        )
        if result.get("ok"):
            print(
                f"ACP_INJECT_DUPLEX seat={seat} task={result.get('taskId')} "
                f"caller={result.get('caller') or 'none'}",
                flush=True,
            )
    except Exception as e:  # noqa: BLE001 — inject succeeded even if duplex fails
        print(f"ACP_INJECT_DUPLEX_ERR seat={seat} err={e}", file=sys.stderr)


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
        self._harvested: Optional[asyncio.Future] = None
        self.harvested_early = False
        self._use_stdlib = not _HAS_WEBSOCKETS
        self._echo_chunks = False
        self._tool_events = 0
        self._prompt_accepted = False
        self._queued = False
        self._accepted: Optional[asyncio.Event] = None

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
                    kind = str(update.get("sessionUpdate") or "")
                    if kind == "agent_message_chunk":
                        t = ((update.get("content") or {}).get("text")) or ""
                        if t:
                            self._chunks.append(t)
                            if self._echo_chunks:
                                sys.stdout.write(t)
                                sys.stdout.flush()
                            self._maybe_complete_harvest()
                            self._maybe_signal_accepted()
                    elif kind in _WORK_UPDATES:
                        self._tool_events += 1
                        self._maybe_complete_harvest()
                        self._maybe_signal_accepted()
                elif isinstance(method, str) and "queue/changed" in method:
                    # Submit ack only. Never HANDOFF on queue/changed alone.
                    self._queued = True
                    self._maybe_signal_accepted()
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
            if self._harvested and not self._harvested.done():
                self._harvested.set_exception(e)

    def _maybe_complete_harvest(self) -> None:
        fut = self._harvested
        if fut is None or fut.done():
            return
        line = extract_result_line("".join(self._chunks))
        if line:
            fut.set_result(line)

    def _maybe_signal_accepted(self) -> None:
        """HANDOFF only on this-prompt tool or non-RESULT session/update."""
        if self._accepted is None or self._accepted.is_set():
            return
        text = "".join(self._chunks)
        if is_handoff_signal(text, tool_events=self._tool_events, queued=self._queued):
            self._accepted.set()

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

    async def session_cancel(self, session_id: str) -> None:
        """Best-effort cancel; tolerate missing/unsupported cancel on older daemons."""
        try:
            await self.request(
                "session/cancel",
                {"sessionId": session_id},
                timeout=5.0,
            )
        except Exception:
            try:
                await self._send_raw(
                    {
                        "jsonrpc": "2.0",
                        "method": "session/cancel",
                        "params": {"sessionId": session_id},
                    }
                )
            except Exception:
                pass

    async def session_prompt(
        self,
        session_id: str,
        text: str,
        timeout: float,
        *,
        pin_session: bool = False,
    ) -> str:
        """Wait for leftover RESULT harvest, or pin-session HANDOFF.

        Pin-session stays on the websocket until this-prompt tool or a
        non-RESULT session/update, or the accept deadline. Silence,
        queue/changed alone, leftover empty tools, and RESULT-only are
        not HANDOFF.
        """
        self._chunks = []
        self._tool_events = 0
        self._echo_chunks = True
        self.harvested_early = False
        self._prompt_accepted = False
        self._queued = False
        rid = self._next_id
        self._next_id += 1
        loop = asyncio.get_running_loop()
        rpc_fut: asyncio.Future = loop.create_future()
        harvest_fut: asyncio.Future = loop.create_future()
        self._pending[rid] = rpc_fut
        self._harvested = harvest_fut
        self._accepted = asyncio.Event()
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
        accepted_task: Optional[asyncio.Task] = None
        if pin_session:
            accepted_task = asyncio.create_task(self._accepted.wait())
            wait_set: set[asyncio.Future] = {rpc_fut, accepted_task}
            wait_timeout = pin_accept_wait(timeout)
        else:
            wait_set = {rpc_fut, harvest_fut}
            wait_timeout = timeout
        try:
            done, _pending_futs = await asyncio.wait(
                wait_set,
                timeout=wait_timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            reply = "".join(self._chunks)
            if rpc_fut in done and not rpc_fut.cancelled():
                exc = rpc_fut.exception()
                if exc is not None:
                    raise exc
                msg = rpc_fut.result()
                if "error" in msg:
                    raise RuntimeError(f"session/prompt error: {msg['error']}")
            if pin_session:
                if is_handoff_signal(
                    reply, tool_events=self._tool_events, queued=self._queued
                ):
                    return self._finish_prompt(rid, rpc_fut, reply, accepted=True)
                self._pending.pop(rid, None)
                raise asyncio.TimeoutError
            if harvest_fut in done and not harvest_fut.cancelled() and harvest_fut.exception() is None:
                self.harvested_early = True
                return reply
            if rpc_fut in done and not rpc_fut.cancelled():
                return reply
            self._pending.pop(rid, None)
            if extract_result_line(reply):
                self.harvested_early = True
                return reply
            raise asyncio.TimeoutError
        finally:
            if accepted_task is not None and not accepted_task.done():
                accepted_task.cancel()
                try:
                    await accepted_task
                except asyncio.CancelledError:
                    pass
            self._echo_chunks = False

    def _finish_prompt(
        self,
        rid: int,
        fut: asyncio.Future,
        reply: str,
        *,
        accepted: bool,
    ) -> str:
        if accepted:
            self._prompt_accepted = True
        if extract_result_line(reply) and not fut.done():
            self.harvested_early = True
            self._pending.pop(rid, None)
        elif accepted and not fut.done():
            self._pending.pop(rid, None)
        return reply


async def _remint_once(
    client: AcpClient,
    *,
    session_path: Path,
    session_id: str,
) -> None:
    """After no-accept, one session/new on the same websocket. Never reconnect."""
    try:
        new_id = await client.session_new()
    except Exception as e:  # noqa: BLE001 — still a timeout fail
        print(f"ACP_INJECT_REMINT_FAIL old={session_id} err={e}", file=sys.stderr)
        return
    _write_text(session_path, new_id)
    print(
        f"ACP_INJECT_REMINT old={session_id} new={new_id} reason=no-accept",
        flush=True,
    )


async def inject(
    seat: str,
    prompt: str,
    *,
    timeout: float,
    force_new: bool = False,
    pin_session: bool = False,
) -> int:
    url = _ensure_url(seat)
    sd = _seat_dir(seat)
    session_path = sd / "acp.session"
    stale_path = sd / "acp.inject.stale"
    cwd = str(ROOT)

    if pin_session:
        # Keep the pinned id unless this inject no-accept remints it.
        force_new = False
    elif stale_path.is_file() and not force_new:
        force_new = True
        print(f"ACP_INJECT_STALE seat={seat} forcing new session", flush=True)

    client = AcpClient(url, cwd)
    await client.connect()
    session_id: Optional[str] = None
    try:
        await client.initialize()
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
        # Mark in-flight before leftover prompt so dispatch lock-TTL SIGKILL still force-news.
        # Pin-session must not write this flag (a live turn is not stale).
        if not pin_session:
            _write_text(stale_path, f"in-flight timeout={timeout}\n")
        # Wrap as EXTRA TURN so Directors match footer expectations
        full = (
            "=== EXTRA TURN INSTRUCTIONS (ACP inject / persistent seat) ===\n"
            f"{prompt.rstrip()}\n"
        )
        harvested = False
        try:
            reply = await client.session_prompt(
                session_id, full, timeout=timeout, pin_session=pin_session
            )
            harvested = bool(client.harvested_early)
        except asyncio.TimeoutError:
            reply = "".join(client._chunks)
            tools = int(getattr(client, "_tool_events", 0) or 0)
            queued = bool(getattr(client, "_queued", False))
            if pin_session:
                if is_handoff_signal(reply, tool_events=tools, queued=queued):
                    harvested = bool(extract_result_line(reply))
                    client._prompt_accepted = True
                else:
                    reason = "hangup-only" if stream_is_hangup_only(reply, tool_events=tools) else "no-accept"
                    print(
                        f"ACP_INJECT_TIMEOUT seat={seat} session={session_id} "
                        f"timeout={timeout} reason={reason}",
                        file=sys.stderr,
                        flush=True,
                    )
                    await _remint_once(client, session_path=session_path, session_id=session_id)
                    return 1
            elif extract_result_line(reply):
                harvested = True
            else:
                print(
                    f"ACP_INJECT_TIMEOUT seat={seat} session={session_id} timeout={timeout}",
                    file=sys.stderr,
                    flush=True,
                )
                _write_text(stale_path, f"timeout={timeout}\n")
                print(
                    f"ACP_INJECT_CANCEL seat={seat} session={session_id}",
                    file=sys.stderr,
                    flush=True,
                )
                await client.session_cancel(session_id)
                return 1
        except Exception as e:
            print(f"ACP_INJECT_FAIL seat={seat} session={session_id} err={e}", file=sys.stderr)
            if not pin_session:
                print(
                    f"ACP_INJECT_CANCEL seat={seat} session={session_id}",
                    file=sys.stderr,
                    flush=True,
                )
                try:
                    await client.session_cancel(session_id)
                except Exception:
                    pass
            return 1
        _duplex_after_inject(seat, prompt, reply)
        if reply and not reply.endswith("\n"):
            sys.stdout.write("\n")
            sys.stdout.flush()
        try:
            stale_path.unlink(missing_ok=True)
        except OSError:
            pass
        if harvested and not pin_session:
            print(
                f"ACP_INJECT_HARVEST seat={seat} session={session_id}",
                flush=True,
            )
        if pin_session and getattr(client, "_prompt_accepted", False):
            print(
                f"ACP_INJECT_HANDOFF seat={seat} session={session_id}",
                flush=True,
            )
        print(
            f"ACP_INJECT_OK seat={seat} session={session_id} reused={int(reused)} chars={len(reply)}",
            flush=True,
        )
        if harvested and not pin_session:
            await client.session_cancel(session_id)
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
    parser.add_argument(
        "--pin-session",
        action="store_true",
        help=(
            "Keep the pinned acp.session id. Stay on the websocket after "
            "session/prompt start. HANDOFF only on this-prompt tool or a "
            "non-RESULT session/update. Never 1s silence or queue/changed "
            "alone. After no-accept, remint once on the same socket. "
            "Do not session/cancel a handed-off live turn."
        ),
    )
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
            inject(
                seat,
                prompt,
                timeout=args.timeout,
                force_new=args.force_new_session,
                pin_session=args.pin_session,
            )
        )
    except KeyboardInterrupt:
        return 130
    except asyncio.TimeoutError:
        print(f"ACP_INJECT_TIMEOUT seat={seat} timeout={args.timeout}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"ACP_INJECT_FAIL seat={seat} err={e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
