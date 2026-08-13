"""ACP inject harvests RESULT without waiting for session/prompt RPC."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import importlib.util
import json
import stat
import os
import struct
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
INJECT_PY = ROOT / "scripts" / "directors" / "acp_inject.py"
DISPATCH_PY = ROOT / "scripts" / "a2a" / "dispatch.py"
FOOTER = ROOT / "scripts" / "directors" / "common_footer.txt"
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _load(path: Path, name: str, env: dict[str, str] | None = None) -> ModuleType:
    if env:
        os.environ.update(env)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _ws_accept(key: str) -> str:
    digest = hashlib.sha1((key + WS_GUID).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


async def _ws_handshake(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = await reader.read(1024)
        if not chunk:
            raise ConnectionError("eof during handshake")
        data += chunk
    key = ""
    for line in data.decode("iso-8859-1").split("\r\n"):
        if line.lower().startswith("sec-websocket-key:"):
            key = line.split(":", 1)[1].strip()
            break
    if not key:
        raise ConnectionError("missing Sec-WebSocket-Key")
    resp = (
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {_ws_accept(key)}\r\n"
        "\r\n"
    )
    writer.write(resp.encode("ascii"))
    await writer.drain()


async def _ws_recv(reader: asyncio.StreamReader) -> str:
    while True:
        header = await reader.readexactly(2)
        opcode = header[0] & 0x0F
        masked = (header[1] & 0x80) != 0
        length = header[1] & 0x7F
        if length == 126:
            (length,) = struct.unpack("!H", await reader.readexactly(2))
        elif length == 127:
            (length,) = struct.unpack("!Q", await reader.readexactly(8))
        mask = await reader.readexactly(4) if masked else b""
        payload = await reader.readexactly(length)
        if masked:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        if opcode == 0x8:
            raise ConnectionError("WS closed by peer")
        if opcode == 0x9:
            continue
        if opcode in (0x1, 0x0):
            return payload.decode("utf-8")


async def _ws_send(writer: asyncio.StreamWriter, text: str) -> None:
    data = text.encode("utf-8")
    header = bytearray([0x81])
    n = len(data)
    if n < 126:
        header.append(n)
    elif n < 65536:
        header.append(126)
        header.extend(struct.pack("!H", n))
    else:
        header.append(127)
        header.extend(struct.pack("!Q", n))
    writer.write(header + data)
    await writer.drain()


def _chunk_notice(text: str, session_id: str = "sess-test") -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {
            "sessionId": session_id,
            "update": {
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": "text", "text": text},
            },
        },
    }


class FakeAcpServer:
    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.methods: list[str] = []
        self.cancels = 0
        self.port = 0
        self._server: asyncio.AbstractServer | None = None
        self._closing = asyncio.Event()

    async def start(self) -> int:
        self._server = await asyncio.start_server(self._client, "127.0.0.1", 0)
        sockets = self._server.sockets or []
        self.port = int(sockets[0].getsockname()[1])
        return self.port

    async def stop(self) -> None:
        self._closing.set()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await _ws_handshake(reader, writer)
            while not self._closing.is_set():
                try:
                    raw = await asyncio.wait_for(_ws_recv(reader), timeout=0.25)
                except asyncio.TimeoutError:
                    continue
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                method = str(msg.get("method") or "")
                mid = msg.get("id")
                self.methods.append(method)
                if method == "initialize":
                    await _ws_send(
                        writer,
                        json.dumps({"jsonrpc": "2.0", "id": mid, "result": {"protocolVersion": 1}}),
                    )
                elif method == "session/new":
                    await _ws_send(
                        writer,
                        json.dumps({"jsonrpc": "2.0", "id": mid, "result": {"sessionId": "sess-test"}}),
                    )
                elif method == "session/load":
                    await _ws_send(writer, json.dumps({"jsonrpc": "2.0", "id": mid, "result": {}}))
                elif method == "session/prompt":
                    if self.mode != "hang":
                        await _ws_send(writer, json.dumps(_chunk_notice("working...\nRES")))
                        await _ws_send(
                            writer,
                            json.dumps(
                                _chunk_notice(
                                    "ULT bc-id=none pr=none a2a=task-harvest notes=early-ok\n"
                                )
                            ),
                        )
                    if self.mode == "rpc":
                        await _ws_send(
                            writer,
                            json.dumps({"jsonrpc": "2.0", "id": mid, "result": {"stopReason": "end_turn"}}),
                        )
                    # hang / harvest / timeout-result: do not send session/prompt RPC result
                elif method == "session/cancel":
                    self.cancels += 1
                    if mid is not None:
                        await _ws_send(writer, json.dumps({"jsonrpc": "2.0", "id": mid, "result": {}}))
        except (ConnectionError, asyncio.IncompleteReadError, asyncio.CancelledError):
            return
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass


def _prepare_seat(mod: ModuleType, tmp_path: Path, port: int) -> Path:
    state = tmp_path / "a2a-state"
    seat_dir = state / "floor"
    seat_dir.mkdir(parents=True)
    (seat_dir / "acp.secret").write_text("test-secret\n", encoding="utf-8")
    (seat_dir / "acp.url").write_text(f"ws://127.0.0.1:{port}/ws\n", encoding="utf-8")
    (seat_dir / "acp.inject.stale").write_text("prior-timeout\n", encoding="utf-8")
    fake_send = tmp_path / "fake-send.sh"
    fake_send.write_text("#!/bin/bash\necho A2A_SEND_OK\nexit 0\n", encoding="utf-8")
    fake_send.chmod(fake_send.stat().st_mode | stat.S_IEXEC)
    os.environ["GCS_A2A_SEND"] = str(fake_send)
    mod.STATE_DIR = state
    mod.ROOT = ROOT
    return seat_dir


PROMPT = (
    "A2A_TASK_ID=task-harvest\n"
    "A2A_CONTEXT=ctx-1\n"
    "MESSAGE:\n"
    "from=ops ping harvest\n"
)


@pytest.mark.parametrize(
    "blob, expected_prefix",
    [
        ("RESULT bc-id=none pr=none a2a=none notes=ok\n", "RESULT "),
        ("chatter\nPARK_ACK seat=floor notes=parked\n", "PARK_ACK "),
        ("QA_A_RESULT merged=none skipped=none conflicts=none notes=idle\n", "QA_A_RESULT "),
        ("QA_B_RESULT merged=1 skipped=none conflicts=none notes=merged\n", "QA_B_RESULT "),
        ("no contract line here\n", None),
    ],
)
def test_extract_result_line(blob: str, expected_prefix: str | None) -> None:
    mod = _load(INJECT_PY, "gcs_acp_inject_extract")
    line = mod.extract_result_line(blob)
    if expected_prefix is None:
        assert line is None
    else:
        assert line is not None
        assert line.startswith(expected_prefix)


def test_inject_ok_on_result_without_prompt_rpc(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    async def scenario() -> tuple[int, FakeAcpServer, Path, float]:
        server = FakeAcpServer("harvest")
        port = await server.start()
        mod = _load(
            INJECT_PY,
            "gcs_acp_inject_harvest",
            {"GCS_ROOT": str(ROOT), "GCS_A2A_STATE": str(tmp_path / "a2a-state")},
        )
        seat_dir = _prepare_seat(mod, tmp_path, port)
        started = time.monotonic()
        try:
            rc = await asyncio.wait_for(mod.inject("floor", PROMPT, timeout=8.0), timeout=5.0)
        finally:
            elapsed = time.monotonic() - started
            await server.stop()
        return rc, server, seat_dir, elapsed

    rc, server, seat_dir, elapsed = asyncio.run(scenario())
    out = capsys.readouterr()
    blob = out.out + out.err
    assert rc == 0, blob
    assert elapsed < 3.0, f"inject stalled waiting for session/prompt RPC ({elapsed:.2f}s)\n{blob}"
    assert "ACP_INJECT_OK" in blob
    assert "ACP_INJECT_TIMEOUT" not in blob
    assert "ACP_INJECT_HARVEST" in blob
    assert "session/prompt" in server.methods
    assert server.cancels >= 1
    assert not (seat_dir / "acp.inject.stale").is_file()
    marker = seat_dir / "runs" / "task-harvest.duplex"
    assert marker.is_file(), blob


def test_inject_timeout_with_result_is_success(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    async def scenario() -> int:
        server = FakeAcpServer("rpc")
        port = await server.start()
        mod = _load(
            INJECT_PY,
            "gcs_acp_inject_timeout_ok",
            {"GCS_ROOT": str(ROOT), "GCS_A2A_STATE": str(tmp_path / "a2a-state")},
        )
        _prepare_seat(mod, tmp_path, port)

        async def timed_out_prompt(self: Any, *_args: Any, **_kwargs: Any) -> str:
            self._chunks = ["RESULT bc-id=none pr=none a2a=task-harvest notes=timeout-ok\n"]
            raise asyncio.TimeoutError

        mod.AcpClient.session_prompt = timed_out_prompt  # type: ignore[method-assign]
        try:
            return await asyncio.wait_for(mod.inject("floor", PROMPT, timeout=2.0), timeout=5.0)
        finally:
            await server.stop()

    rc = asyncio.run(scenario())
    out = capsys.readouterr()
    blob = out.out + out.err
    assert rc == 0, blob
    assert "ACP_INJECT_OK" in blob
    assert "ACP_INJECT_TIMEOUT" not in blob


def test_inject_timeout_without_result_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    async def scenario() -> tuple[int, Path]:
        server = FakeAcpServer("hang")
        port = await server.start()
        mod = _load(
            INJECT_PY,
            "gcs_acp_inject_timeout_fail",
            {"GCS_ROOT": str(ROOT), "GCS_A2A_STATE": str(tmp_path / "a2a-state")},
        )
        seat_dir = _prepare_seat(mod, tmp_path, port)
        try:
            rc = await asyncio.wait_for(mod.inject("floor", PROMPT, timeout=0.4), timeout=3.0)
        finally:
            await server.stop()
        return rc, seat_dir

    rc, seat_dir = asyncio.run(scenario())
    blob = capsys.readouterr().out + capsys.readouterr().err
    assert rc == 1, blob
    assert (seat_dir / "acp.inject.stale").is_file()


def test_duplex_extract_matches_inject() -> None:
    inject = _load(INJECT_PY, "gcs_acp_inject_duplex_cmp")
    duplex = _load(ROOT / "scripts" / "a2a" / "duplex.py", "gcs_a2a_duplex_cmp")
    blob = "chatter\nRESULT bc-id=none pr=none a2a=t-1 notes=ok\n"
    assert inject.extract_result_line(blob) == duplex.extract_result_line(blob)
    rec = {"parts": [{"kind": "data", "data": {"from": "ops"}}]}
    assert duplex.extract_caller(rec) == "ops"


def test_compose_extra_and_footer_forbid_caller_send_ack() -> None:
    dispatch = _load(DISPATCH_PY, "gcs_a2a_dispatch_compose")
    extra = dispatch._compose_extra("t-1", "c-1", "hello")
    lowered = extra.lower()
    assert "a2a_task_id=t-1" in lowered
    assert "result" in lowered
    assert "duplex" in lowered
    assert "send.sh" in lowered or "a2a_send" in lowered
    assert "do not" in lowered
    footer = FOOTER.read_text(encoding="utf-8").lower()
    assert "duplex" in footer
    assert "send.sh" in footer
    assert "do not" in footer
