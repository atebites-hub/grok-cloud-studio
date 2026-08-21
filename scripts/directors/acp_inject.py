#!/usr/bin/env python3
"""Inject a prompt into a per-seat grok agent serve (ACP over WebSocket).

Usage:
  acp_inject.py <seat> <extra-text...>
  acp_inject.py --seat <seat> --file <path>
  acp_inject.py --seat <seat> --stdin

Reads .a2a-state/<seat>/{acp.url,acp.secret,acp.session}.
Persists session id after session/new. Prefer session/load on later injects.

GROW `--pin-session`: stay on the websocket until a this-prompt STATUS
line or session/prompt RPC completion (or timeout). Do not HANDOFF on
keep-alive chatter, 40-80 char acknowledgements, leftover tools,
queue/changed, RESULT-only, or first tool — disconnecting there kills
the turn. HANDOFF reason=status|rpc-complete only (never queue, tool,
harvest, substantial-on-keepalive). Timeout with no work is
ACP_INJECT_TIMEOUT reason=no-accept (not HANDOFF). After N consecutive
no-accept/hangup fails on the same acp.session id, one session/new
(SESSION_DEAD). Do not session/cancel a handed-off live turn.
Not leftover-mint-per-ping.

Leftover dispatch (no pin): completes on streamed work/STATUS (or this-prompt
tool+text), not on session/prompt RPC end. Timeout and prompt-fail
session/cancel so grok 1.0.3 does not start_blocked.

RESULT / PARK_ACK / QA_*_RESULT is duplex only — RESULT-only is not success.
Leftover tool_call notifications with zero assistant chars are not work.
Authenticate ACP `cached_token` after initialize. Stdlib + optional websockets.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import importlib.util
import json
import os
import re
import secrets
import struct
import sys
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

ROOT = Path(os.environ.get("GCS_ROOT", Path(__file__).resolve().parents[2]))
STATE_DIR = Path(os.environ.get("GCS_A2A_STATE", str(ROOT / ".a2a-state")))
DEFAULT_TIMEOUT = float(os.environ.get("GCS_ACP_INJECT_TIMEOUT", "180"))
# No-start window for pin-session. Silence / queue-only / leftover-tools with
# empty text must nack here (never HANDOFF). If the actor DID start (this-prompt
# tool or non-RESULT update), stay connected until STATUS or session/prompt
# RPC completes, up to --timeout / GCS_ACP_INJECT_TIMEOUT. Keep-alive chatter
# is a start, not leave.
PIN_NACK_SEC = float(os.environ.get("GCS_ACP_ACCEPT_DEADLINE", "30"))
# Consecutive no-accept / hangup-only fails on the same pin-session id
# before one session/new (dead session: load works, actor never starts).
DEAD_STREAK_N = int(os.environ.get("GCS_ACP_DEAD_STREAK", "1"))
# Same markers duplex.py harvests. Inject completes on this line, not on RPC end.
_RESULT_LINE_RE = re.compile(
    r"^(RESULT|QA_A_RESULT|QA_B_RESULT|PARK_ACK)\b.*$",
    re.MULTILINE,
)
_STATUS_LINE_RE = re.compile(r"^STATUS\b", re.MULTILINE)
_PONG_ONLY_RE = re.compile(r"^\s*(PONG|pong|ok|OK)\s*$")
_WORK_UPDATES = frozenset({"tool_call", "tool_call_update", "agent_thought_chunk"})

_LIB_DIR = Path(__file__).resolve().parents[1] / "a2a"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
from lib import canonical_seat, seat_acp_port  # noqa: E402

try:
    import websockets  # type: ignore
    from websockets.client import connect as ws_connect  # type: ignore

    _HAS_WEBSOCKETS = True
except ImportError:
    _HAS_WEBSOCKETS = False


def extract_inject_result_line(text: str) -> str | None:
    """Last RESULT / PARK_ACK / QA_*_RESULT line in streamed assistant text."""
    if not text:
        return None
    found: str | None = None
    for match in _RESULT_LINE_RE.finditer(text):
        found = match.group(0).strip()
    return found


def _work_body_without_result_lines(text: str) -> str:
    """Assistant text excluding RESULT / PARK_ACK / QA_*_RESULT hang-up lines."""
    if not text:
        return ""
    kept: list[str] = []
    for line in str(text).splitlines():
        if _RESULT_LINE_RE.match(line.strip()):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def seat_produced_work(text: str, *, tool_events: int = 0) -> bool:
    """True when this prompt produced work/STATUS. PONG-only is not work.

    tool_events with zero assistant chars is leftover noise, not work.
    A RESULT hang-up line with no other text is not work, even with tools.
    """
    raw = "" if text is None else str(text)
    if _STATUS_LINE_RE.search(raw):
        return True
    body = _work_body_without_result_lines(raw)
    if not body:
        return False
    if _PONG_ONLY_RE.match(body):
        return False
    if tool_events > 0:
        return True
    return len(body) >= 40


def pin_session_handoff_reason(
    text: str,
    *,
    rpc_complete: bool = False,
    tool_events: int = 0,
) -> str | None:
    """Pin-session HANDOFF reason, or None if inject must stay connected.

    Only ``status`` (this-prompt STATUS line) or ``rpc-complete``
    (session/prompt RPC finished a started turn). Never queue, tool,
    harvest, or substantial-on-keepalive. Keep-alive chatter, leftover
    tools, RESULT-only, and 40-80 char acknowledgements are not leave
    until RPC completes a started turn.
    """
    raw = "" if text is None else str(text)
    if _STATUS_LINE_RE.search(raw):
        return "status"
    if not rpc_complete:
        return None
    if stream_is_hangup_only(raw, tool_events=tool_events):
        return None
    if prompt_chunk_is_accept_signal(raw):
        return "rpc-complete"
    return None


def pin_session_ready_to_leave(text: str) -> bool:
    """True when pin-session may disconnect before RPC: this-prompt STATUS only.

    Keep-alive chatter, leftover tools, queue/changed, RESULT-only, and
    40-80 char acknowledgements are not leave. session/prompt RPC
    completion is a separate leave path (HANDOFF reason=rpc-complete).
    Leftover dispatch still uses seat_produced_work.
    """
    return pin_session_handoff_reason(text, rpc_complete=False) == "status"


def prompt_chunk_is_accept_signal(text: str) -> bool:
    """True when streamed assistant text means serve accepted this prompt.

    STATUS is accept. RESULT hang-up and PONG are not. Any other non-empty
    body (including short thinking) is accept — not the same as work.
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


def stream_is_hangup_only(text: str, *, tool_events: int = 0) -> bool:
    """RESULT-only or PONG-only. Leftover tools without RESULT are not hang-up."""
    raw = "" if text is None else str(text)
    if seat_produced_work(raw, tool_events=tool_events):
        return False
    body = _work_body_without_result_lines(raw)
    if extract_inject_result_line(raw) and not body:
        return True
    if tool_events > 0:
        return False
    stripped = (body or raw).strip()
    return bool(stripped and _PONG_ONLY_RE.match(stripped))


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


def _dead_streak_path(sd: Path) -> Path:
    return sd / "acp.no_accept_streak"


def _read_dead_streak(sd: Path) -> tuple[str, int]:
    path = _dead_streak_path(sd)
    if not path.is_file():
        return "", 0
    sid = ""
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("session="):
            sid = line.split("=", 1)[1].strip()
        elif line.startswith("count="):
            try:
                count = int(line.split("=", 1)[1].strip() or "0")
            except ValueError:
                count = 0
    return sid, count


def _write_dead_streak(sd: Path, session_id: str, count: int) -> None:
    _write_text(_dead_streak_path(sd), f"session={session_id}\ncount={count}\n")


def _clear_dead_streak(sd: Path) -> None:
    try:
        _dead_streak_path(sd).unlink(missing_ok=True)
    except OSError:
        pass


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


def _ensure_url(seat: str) -> str:
    sd = _seat_dir(seat)
    url_path = sd / "acp.url"
    secret_path = sd / "acp.secret"
    if url_path.is_file():
        return _read_text(url_path)
    if not secret_path.is_file():
        raise SystemExit(
            f"ACP_INJECT_FAIL seat={seat} missing acp.url/acp.secret (daemon not started?)"
        )
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
            if opcode == 0x8:
                raise ConnectionError("WS closed by peer")
            if opcode == 0x9:
                frame = bytearray([0x8A, 0x80 | len(payload)])
                m = secrets.token_bytes(4)
                frame.extend(m)
                frame.extend(bytes(b ^ m[i % 4] for i, b in enumerate(payload)))
                self._writer.write(frame)
                await self._writer.drain()
                continue
            if opcode in (0x1, 0x0):
                text = payload.decode("utf-8")
                if not fin:
                    more = [text]
                    while True:
                        part = await self.recv()
                        more.append(part)
                        break
                    return "".join(more)
                return text
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
        self._result_seen: Optional[asyncio.Event] = None
        self._harvested_early = False
        self._tool_events = 0
        self._prompt_accepted = False
        self._queued = False
        self._accepted: Optional[asyncio.Event] = None
        self._pin_wait = False
        self._handoff_reason: Optional[str] = None

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
                            self._maybe_signal_done()
                            self._maybe_signal_accepted()
                    elif kind in _WORK_UPDATES:
                        self._tool_events += 1
                        self._maybe_signal_done()
                        self._maybe_signal_accepted()
                elif isinstance(method, str) and "queue/changed" in method:
                    self._queued = True
                elif method in ("_x.ai/session/prompt_complete",):
                    pass
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

    def _maybe_signal_done(self) -> None:
        """Release leftover harvest on work/STATUS; pin-session only on STATUS."""
        if self._result_seen is None or self._result_seen.is_set():
            return
        text = "".join(self._chunks)
        if self._pin_wait:
            if pin_session_ready_to_leave(text):
                self._result_seen.set()
            return
        if seat_produced_work(text, tool_events=self._tool_events):
            self._result_seen.set()

    def _maybe_signal_accepted(self) -> None:
        """Real start: non-RESULT assistant text (STATUS, thinking, Donald).

        Queue/changed and leftover tools with empty text are not a start.
        First tool + short text is a start, not HANDOFF.
        """
        if self._accepted is None or self._accepted.is_set():
            return
        if prompt_chunk_is_accept_signal("".join(self._chunks)):
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
        result = await self.request(
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
        await self.authenticate_cached_token(result)
        return result

    async def authenticate_cached_token(self, init_result: dict[str, Any] | None = None) -> None:
        """Use GROK_HOME/auth.json via ACP authenticate methodId=cached_token."""
        methods: list[Any] = []
        if isinstance(init_result, dict):
            methods = list(init_result.get("authMethods") or init_result.get("auth_methods") or [])
        ids: list[str] = []
        for item in methods:
            if isinstance(item, dict):
                ids.append(str(item.get("id") or item.get("methodId") or ""))
            elif item:
                ids.append(str(item))
        if ids and "cached_token" not in ids:
            return
        try:
            await self.request(
                "authenticate",
                {"methodId": "cached_token"},
                timeout=30.0,
            )
            print("ACP_INJECT_AUTH method=cached_token", flush=True)
        except Exception as e:  # noqa: BLE001 — older daemons may lack authenticate
            print(f"ACP_INJECT_AUTH_WARN method=cached_token err={e}", file=sys.stderr)

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
        """Wait for work/STATUS (leftover) or pin-session STATUS/RPC.

        Pin-session stays on the websocket until a this-prompt STATUS line,
        session/prompt RPC completes, or timeout. Keep-alive chatter,
        leftover tools, queue/changed, RESULT-only, and first tool are
        not HANDOFF. Nack-window silence is not a start. Leftover dispatch:
        harvest work/STATUS; leftover tools are not work.
        """
        self._chunks = []
        self._tool_events = 0
        self._echo_chunks = True
        self._harvested_early = False
        self._prompt_accepted = False
        self._queued = False
        self._pin_wait = pin_session
        self._handoff_reason = None
        self._result_seen = asyncio.Event()
        self._accepted = asyncio.Event()
        rid = self._next_id
        self._next_id += 1
        loop = asyncio.get_running_loop()
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
        harvest = asyncio.create_task(self._result_seen.wait())
        accepted_wait: Optional[asyncio.Task] = None
        if pin_session:
            accepted_wait = asyncio.create_task(self._accepted.wait())
        wait_set: set[asyncio.Future] = {fut, harvest}
        if accepted_wait is not None:
            wait_set.add(accepted_wait)
        t0 = time.monotonic()
        try:
            first_timeout = timeout
            if pin_session:
                first_timeout = min(timeout, max(0.05, float(PIN_NACK_SEC)))
            await asyncio.wait(
                wait_set,
                timeout=first_timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            reply = "".join(self._chunks)
            if fut.done():
                msg = fut.result()
                if "error" in msg:
                    raise RuntimeError(f"session/prompt error: {msg['error']}")
            if pin_session_ready_to_leave(reply):
                return self._return_prompt_stream(
                    rid, fut, reply, accepted=pin_session, handoff_reason="status"
                )
            if pin_session:
                started_turn = bool(
                    self._accepted.is_set() or prompt_chunk_is_accept_signal(reply)
                )
                if not started_turn and not fut.done():
                    self._pending.pop(rid, None)
                    raise asyncio.TimeoutError()
                if not fut.done():
                    remaining = timeout - (time.monotonic() - t0)
                    if remaining > 0:
                        await asyncio.wait(
                            {fut, harvest},
                            timeout=remaining,
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                    reply = "".join(self._chunks)
                    if fut.done():
                        msg = fut.result()
                        if "error" in msg:
                            raise RuntimeError(
                                f"session/prompt error: {msg['error']}"
                            )
                    if pin_session_ready_to_leave(reply):
                        return self._return_prompt_stream(
                            rid, fut, reply, accepted=True, handoff_reason="status"
                        )
                if stream_is_hangup_only(reply, tool_events=self._tool_events):
                    self._pending.pop(rid, None)
                    raise asyncio.TimeoutError()
                if fut.done():
                    reason = pin_session_handoff_reason(
                        reply,
                        rpc_complete=True,
                        tool_events=self._tool_events,
                    )
                    if reason in ("status", "rpc-complete"):
                        return self._return_prompt_stream(
                            rid,
                            fut,
                            reply,
                            accepted=True,
                            handoff_reason=reason,
                        )
                self._pending.pop(rid, None)
                raise asyncio.TimeoutError()
            if seat_produced_work(reply, tool_events=self._tool_events):
                return self._return_prompt_stream(rid, fut, reply, accepted=False)
            if stream_is_hangup_only(reply, tool_events=self._tool_events):
                self._pending.pop(rid, None)
                raise asyncio.TimeoutError()
            if fut.done():
                return reply
            self._pending.pop(rid, None)
            raise asyncio.TimeoutError()
        finally:
            for task in (harvest, accepted_wait):
                if task is not None and not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            self._echo_chunks = False
            self._pin_wait = False

    def _return_prompt_stream(
        self,
        rid: int,
        fut: asyncio.Future,
        reply: str,
        *,
        accepted: bool,
        handoff_reason: Optional[str] = None,
    ) -> str:
        if accepted:
            self._prompt_accepted = True
            if handoff_reason in ("status", "rpc-complete"):
                self._handoff_reason = handoff_reason
        if seat_produced_work(reply, tool_events=self._tool_events) and not fut.done():
            self._harvested_early = True
            self._pending.pop(rid, None)
        elif accepted and not fut.done():
            self._pending.pop(rid, None)
        return reply


async def _maybe_remint_dead_pin_session(
    client: AcpClient,
    *,
    sd: Path,
    session_path: Path,
    session_id: str,
    evidence: str,
) -> None:
    """After N consecutive no-accept/hangup fails on this id, one session/new."""
    prev_id, count = _read_dead_streak(sd)
    if prev_id != session_id:
        count = 0
    count += 1
    _write_dead_streak(sd, session_id, count)
    if count < DEAD_STREAK_N:
        return
    try:
        new_id = await client.session_new()
    except Exception as e:  # noqa: BLE001 — still a timeout fail
        print(
            f"ACP_INJECT_SESSION_DEAD_FAIL old={session_id} err={e}",
            file=sys.stderr,
        )
        return
    _write_text(session_path, new_id)
    _clear_dead_streak(sd)
    print(
        f"ACP_INJECT_SESSION_DEAD old={session_id} new={new_id} evidence={evidence}",
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
    seat = canonical_seat(seat, ROOT)
    url = _ensure_url(seat)
    sd = _seat_dir(seat)
    session_path = sd / "acp.session"
    stale_path = sd / "acp.inject.stale"
    cwd = str(ROOT)

    if pin_session:
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
                    print(
                        f"ACP_INJECT_SESSION_LOAD_FAIL seat={seat} err={e}; creating new",
                        file=sys.stderr,
                    )
                    session_id = None
        if not session_id:
            session_id = await client.session_new()
            _write_text(session_path, session_id)
            reused = False
        elif pin_session:
            prev_id, streak = _read_dead_streak(sd)
            if prev_id == session_id and streak >= DEAD_STREAK_N:
                old_id = session_id
                session_id = await client.session_new()
                _write_text(session_path, session_id)
                _clear_dead_streak(sd)
                reused = False
                print(
                    f"ACP_INJECT_SESSION_DEAD old={old_id} new={session_id} "
                    f"evidence=no-accept-streak",
                    flush=True,
                )

        print(
            f"ACP_INJECT_BEGIN seat={seat} session={session_id} reused={int(reused)} url={url.split('?')[0]}",
            flush=True,
        )
        if not pin_session:
            _write_text(stale_path, f"in-flight timeout={timeout}\n")
        full = (
            "=== EXTRA TURN INSTRUCTIONS (ACP inject / persistent seat) ===\n"
            f"{prompt.rstrip()}\n"
        )
        harvested_early = False
        cancelled_hung = False
        try:
            reply = await client.session_prompt(
                session_id, full, timeout=timeout, pin_session=pin_session
            )
            harvested_early = bool(getattr(client, "_harvested_early", False))
        except asyncio.TimeoutError:
            reply = "".join(client._chunks)
            tools = int(getattr(client, "_tool_events", 0) or 0)
            if pin_session:
                started_turn = prompt_chunk_is_accept_signal(reply)
                if stream_is_hangup_only(reply, tool_events=tools):
                    print(
                        f"ACP_INJECT_TIMEOUT seat={seat} session={session_id} "
                        f"timeout={timeout} reason=hangup-only",
                        file=sys.stderr,
                        flush=True,
                    )
                    await _maybe_remint_dead_pin_session(
                        client,
                        sd=sd,
                        session_path=session_path,
                        session_id=session_id,
                        evidence="hangup-only-streak",
                    )
                    return 1
                if pin_session_ready_to_leave(reply):
                    harvested_early = True
                    client._prompt_accepted = True
                    client._handoff_reason = "status"
                elif started_turn:
                    print(
                        f"ACP_INJECT_TIMEOUT seat={seat} session={session_id} "
                        f"timeout={timeout} reason=no-accept",
                        file=sys.stderr,
                        flush=True,
                    )
                    return 1
                else:
                    print(
                        f"ACP_INJECT_TIMEOUT seat={seat} session={session_id} "
                        f"timeout={timeout} reason=no-accept",
                        file=sys.stderr,
                        flush=True,
                    )
                    await _maybe_remint_dead_pin_session(
                        client,
                        sd=sd,
                        session_path=session_path,
                        session_id=session_id,
                        evidence="no-accept-streak",
                    )
                    return 1
            else:
                print(
                    f"ACP_INJECT_CANCEL seat={seat} session={session_id}",
                    file=sys.stderr,
                    flush=True,
                )
                try:
                    await client.session_cancel(session_id)
                except Exception:
                    pass
                cancelled_hung = True
                if seat_produced_work(reply, tool_events=tools):
                    harvested_early = True
                else:
                    print(
                        f"ACP_INJECT_TIMEOUT seat={seat} session={session_id} timeout={timeout}",
                        file=sys.stderr,
                        flush=True,
                    )
                    _write_text(stale_path, f"timeout={timeout}\n")
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
        if reply and not reply.endswith("\n"):
            sys.stdout.write("\n")
            sys.stdout.flush()
        _duplex_after_inject(seat, prompt, reply)
        if harvested_early:
            print(
                f"ACP_INJECT_RESULT_HARVEST seat={seat} session={session_id}",
                flush=True,
            )
        if pin_session and getattr(client, "_prompt_accepted", False):
            reason = getattr(client, "_handoff_reason", None)
            if reason in ("status", "rpc-complete"):
                print(
                    f"ACP_INJECT_HANDOFF seat={seat} session={session_id} reason={reason}",
                    flush=True,
                )
        print(
            f"ACP_INJECT_OK seat={seat} session={session_id} reused={int(reused)} chars={len(reply)}",
            flush=True,
        )
        if pin_session:
            _clear_dead_streak(sd)
        try:
            stale_path.unlink(missing_ok=True)
        except OSError:
            pass
        if harvested_early and not pin_session and not cancelled_hung:
            print(
                f"ACP_INJECT_CANCEL seat={seat} session={session_id}",
                file=sys.stderr,
                flush=True,
            )
            try:
                await client.session_cancel(session_id)
            except Exception:
                pass
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
            "GROW wake: session/load the pinned id (or session/new once if "
            "missing). Stay on the websocket until a this-prompt STATUS "
            "line or session/prompt RPC completes. Do not HANDOFF on "
            "keep-alive chatter, queue/changed, leftover tools, or first "
            "tool. HANDOFF reason=status|rpc-complete. After N "
            "no-accept/hangup fails on the same id, one session/new "
            "(dead session). Disconnect without session/cancel after a "
            "true HANDOFF."
        ),
    )
    args = parser.parse_args()

    seat = (args.seat or args.seat_pos or "").strip()
    if not seat:
        parser.error("seat required")
    seat = canonical_seat(seat, ROOT)

    if args.stdin:
        prompt = sys.stdin.read()
    elif args.file:
        prompt = Path(args.file).read_text(encoding="utf-8")
    elif args.extra:
        prompt = " ".join(args.extra)
    elif args.seat_pos and not args.extra:
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
