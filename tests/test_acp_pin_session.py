"""ACP inject --pin-session: hand off to grok agent serve, do not remint.

Success is mail delivered (session/prompt accepted). Disconnect without
session/cancel so the live serve owns the turn. RESULT-only is not success.
Leftover dispatch (no --pin-session) is covered in test_acp_inject.py.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
ACP_INJECT = ROOT / "scripts" / "directors" / "acp_inject.py"

RESULT_LINE = "RESULT bc-id=none pr=none a2a=task-1 notes=park-ok"
STATUS_LINE = "STATUS quoting token tick-1. Working."


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _chunk(text: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {
            "update": {
                "sessionUpdate": "agent_message_chunk",
                "content": {"text": text},
            }
        },
    }


def _tool_update(tool_call_id: str = "tc-stale", title: str = "leftover") -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {
            "update": {
                "sessionUpdate": "tool_call",
                "toolCallId": tool_call_id,
                "title": title,
            }
        },
    }


def _queue_changed(size: int = 1) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "method": "x.ai/queue/changed",
        "params": {"size": size},
    }


def _capture_prompt_harvest(mod: ModuleType, monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    orig = mod.AcpClient.session_prompt

    async def wrap(self: Any, session_id: str, text: str, timeout: float, **kwargs: Any) -> str:
        try:
            reply = await orig(self, session_id, text, timeout, **kwargs)
            flags.append(
                {
                    "harvested_early": bool(getattr(self, "harvested_early", False)),
                    "prompt_accepted": bool(getattr(self, "_prompt_accepted", False)),
                    "tool_events": int(getattr(self, "_tool_events", 0) or 0),
                    "chars": len(reply),
                    "reply": reply,
                }
            )
            return reply
        except BaseException:
            flags.append(
                {
                    "harvested_early": bool(getattr(self, "harvested_early", False)),
                    "prompt_accepted": bool(getattr(self, "_prompt_accepted", False)),
                    "tool_events": int(getattr(self, "_tool_events", 0) or 0),
                    "chars": len("".join(self._chunks)),
                    "reply": "".join(self._chunks),
                }
            )
            raise

    monkeypatch.setattr(mod.AcpClient, "session_prompt", wrap)
    return flags


class FakeAcpWs:
    """ACP WebSocket stub. Completes initialize/session; never finishes prompt RPC."""

    def __init__(
        self,
        *,
        prompt_chunks: list[str] | None = None,
        prompt_updates: list[dict[str, Any]] | None = None,
    ) -> None:
        self._incoming: asyncio.Queue[Any] = asyncio.Queue()
        self.sent: list[dict[str, Any]] = []
        self.prompt_rpc_ids: list[Any] = []
        self.cancel_sessions: list[str] = []
        self.blocked_prompts: list[Any] = []
        self.auth_method_ids: list[str] = []
        self.prompt_inflight = False
        self.closed = False
        self._prompt_chunks = list(prompt_chunks or [])
        self._prompt_updates = list(prompt_updates or [])

    async def send(self, text: str) -> None:
        msg = json.loads(text)
        self.sent.append(msg)
        method = msg.get("method")
        rid = msg.get("id")
        params = msg.get("params") or {}
        if method == "initialize":
            await self._incoming.put(
                {
                    "jsonrpc": "2.0",
                    "id": rid,
                    "result": {
                        "protocolVersion": 1,
                        "authMethods": [{"id": "cached_token", "name": "cached_token"}],
                    },
                }
            )
        elif method == "authenticate":
            mid = str(params.get("methodId") or params.get("method_id") or "")
            self.auth_method_ids.append(mid)
            await self._incoming.put({"jsonrpc": "2.0", "id": rid, "result": {}})
        elif method == "session/new":
            await self._incoming.put(
                {"jsonrpc": "2.0", "id": rid, "result": {"sessionId": "sess-harvest"}}
            )
        elif method == "session/load":
            await self._incoming.put({"jsonrpc": "2.0", "id": rid, "result": {}})
        elif method == "session/prompt":
            if self.prompt_inflight:
                self.blocked_prompts.append(rid)
                await self._incoming.put(
                    {
                        "jsonrpc": "2.0",
                        "id": rid,
                        "error": {"code": -32000, "message": "shell.prompt.start_blocked"},
                    }
                )
                return
            self.prompt_inflight = True
            self.prompt_rpc_ids.append(rid)
            for part in self._prompt_chunks:
                await self._incoming.put(_chunk(part))
            for upd in self._prompt_updates:
                await self._incoming.put(upd)
        elif method == "session/cancel":
            sid = str(params.get("sessionId") or "")
            self.cancel_sessions.append(sid)
            self.prompt_inflight = False
            if rid is not None:
                await self._incoming.put({"jsonrpc": "2.0", "id": rid, "result": {}})

    async def recv(self) -> str:
        item = await self._incoming.get()
        if item is None:
            raise ConnectionError("WS closed")
        if isinstance(item, str):
            return item
        return json.dumps(item)

    async def close(self) -> None:
        self.closed = True


def _prep_seat(mod: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    state = tmp_path / "a2a-state"
    seat_dir = state / "floor"
    seat_dir.mkdir(parents=True)
    (seat_dir / "acp.url").write_text("ws://127.0.0.1:8740/ws?server-key=test\n", encoding="utf-8")
    (seat_dir / "acp.secret").write_text("test\n", encoding="utf-8")
    monkeypatch.setattr(mod, "STATE_DIR", state)
    monkeypatch.setattr(mod, "ROOT", ROOT)
    monkeypatch.setenv("GCS_A2A_STATE", str(state))
    monkeypatch.setenv("GCS_A2A_TASK_ID", "task-1")
    monkeypatch.setenv("GCS_A2A_CONTEXT", "ctx-1")
    monkeypatch.setenv("GCS_A2A_FROM", "ops")
    return seat_dir


def _patch_connect(mod: ModuleType, ws: FakeAcpWs, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_connect(self: Any) -> None:
        ws._incoming = asyncio.Queue()
        self._ws = ws
        self._use_stdlib = True
        self._reader_task = asyncio.create_task(self._read_loop())

    monkeypatch.setattr(mod.AcpClient, "connect", fake_connect)


def test_pin_helpers_result_only_is_hangup_not_accept() -> None:
    mod = _load(ACP_INJECT, "gcs_acp_pin_helpers")
    assert hasattr(mod, "prompt_chunk_is_accept_signal")
    assert hasattr(mod, "stream_is_hangup_only")
    assert mod.prompt_chunk_is_accept_signal("thinking about the ticket") is True
    assert mod.prompt_chunk_is_accept_signal(RESULT_LINE) is False
    assert mod.prompt_chunk_is_accept_signal("PONG") is False
    assert mod.stream_is_hangup_only(RESULT_LINE) is True
    assert mod.stream_is_hangup_only(RESULT_LINE, tool_events=2) is True
    assert mod.stream_is_hangup_only("PONG") is True
    assert mod.stream_is_hangup_only("") is False
    assert mod.stream_is_hangup_only("", tool_events=2) is False


def test_inject_pin_session_success_does_not_remint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    mod = _load(ACP_INJECT, "gcs_acp_inject_pin")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    (seat_dir / "acp.session").write_text("sess-pinned\n", encoding="utf-8")
    (seat_dir / "acp.inject.stale").write_text("leftover\n", encoding="utf-8")
    duplex_calls: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        mod,
        "_duplex_after_inject",
        lambda seat, prompt, reply: duplex_calls.append((seat, prompt, reply)),
    )
    ws = FakeAcpWs(prompt_chunks=[f"{STATUS_LINE}\n", f"{RESULT_LINE}\n"])
    _patch_connect(mod, ws, monkeypatch)

    rc = asyncio.run(mod.inject("floor", "STATUS ping", timeout=2.0, pin_session=True))
    out = capsys.readouterr()
    blob = out.out + out.err

    assert rc == 0, blob
    assert "ACP_INJECT_OK" in out.out
    assert duplex_calls
    assert (seat_dir / "acp.session").read_text(encoding="utf-8").strip() == "sess-pinned"
    assert any(m.get("method") == "session/load" for m in ws.sent)
    assert not any(m.get("method") == "session/new" for m in ws.sent)
    assert not (seat_dir / "acp.inject.stale").is_file()
    assert ws.cancel_sessions == []
    assert ws.auth_method_ids == ["cached_token"]


def test_pin_session_accepted_prompt_disconnect_does_not_cancel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    mod = _load(ACP_INJECT, "gcs_acp_inject_pin_accept")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    (seat_dir / "acp.session").write_text("sess-pinned\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *_a, **_k: None)
    flags = _capture_prompt_harvest(mod, monkeypatch)
    ws = FakeAcpWs(prompt_chunks=["thinking about the ticket\n"])
    _patch_connect(mod, ws, monkeypatch)

    started = time.monotonic()
    rc = asyncio.run(mod.inject("floor", "STATUS continue", timeout=2.0, pin_session=True))
    elapsed = time.monotonic() - started
    out = capsys.readouterr()
    blob = out.out + out.err

    assert rc == 0, blob
    assert "ACP_INJECT_OK" in out.out
    assert "ACP_INJECT_HANDOFF" in out.out
    assert "ACP_INJECT_TIMEOUT" not in blob
    assert "ACP_INJECT_CANCEL" not in blob
    assert flags and flags[0]["prompt_accepted"] is True
    assert elapsed < 1.0, f"waited {elapsed:.2f}s; must not babysit until RESULT"
    assert ws.cancel_sessions == []
    assert ws.closed is True
    assert ws.prompt_inflight is True
    assert (seat_dir / "acp.session").read_text(encoding="utf-8").strip() == "sess-pinned"


def test_pin_session_timeout_does_not_cancel_handed_off_turn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    mod = _load(ACP_INJECT, "gcs_acp_inject_pin_silent")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    (seat_dir / "acp.session").write_text("sess-pinned\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *_a, **_k: None)
    ws = FakeAcpWs(prompt_chunks=[])
    _patch_connect(mod, ws, monkeypatch)

    rc = asyncio.run(mod.inject("floor", "STATUS hang", timeout=0.6, pin_session=True))
    out = capsys.readouterr()
    blob = out.out + out.err
    assert rc == 0, blob
    assert "ACP_INJECT_OK" in out.out
    assert "ACP_INJECT_TIMEOUT" not in blob
    assert "ACP_INJECT_CANCEL" not in blob
    assert ws.cancel_sessions == []
    assert ws.closed is True
    assert ws.prompt_inflight is True
    assert (seat_dir / "acp.session").read_text(encoding="utf-8").strip() == "sess-pinned"
    assert not (seat_dir / "acp.inject.stale").is_file()


def test_pin_session_queue_changed_is_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    mod = _load(ACP_INJECT, "gcs_acp_inject_pin_queue")
    _prep_seat(mod, tmp_path, monkeypatch)
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *_a, **_k: None)
    flags = _capture_prompt_harvest(mod, monkeypatch)
    ws = FakeAcpWs(prompt_chunks=[], prompt_updates=[_queue_changed()])
    _patch_connect(mod, ws, monkeypatch)

    rc = asyncio.run(
        mod.inject("floor", "TASK_ASSIGN: work the ticket.", timeout=2.0, pin_session=True)
    )
    out = capsys.readouterr()
    blob = out.out + out.err
    assert rc == 0, blob
    assert "ACP_INJECT_OK" in out.out
    assert flags and flags[0]["prompt_accepted"] is True
    assert ws.cancel_sessions == []
    assert ws.prompt_inflight is True


def test_result_only_stream_is_not_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    mod = _load(ACP_INJECT, "gcs_acp_inject_result_only")
    _prep_seat(mod, tmp_path, monkeypatch)
    duplex_calls: list[Any] = []
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *_a, **_k: duplex_calls.append(_a))
    flags = _capture_prompt_harvest(mod, monkeypatch)
    ws = FakeAcpWs(prompt_chunks=[f"{RESULT_LINE}\n"])
    _patch_connect(mod, ws, monkeypatch)

    rc = asyncio.run(mod.inject("floor", "STATUS ping", timeout=0.4, pin_session=True))
    out = capsys.readouterr()
    blob = out.out + out.err

    assert rc == 1, blob
    assert flags and flags[0]["harvested_early"] is False
    assert RESULT_LINE in flags[0]["reply"]
    assert "ACP_INJECT_OK" not in out.out
    assert "ACP_INJECT_TIMEOUT" in blob
    assert "ACP_INJECT_CANCEL" not in blob
    assert not duplex_calls
    assert ws.cancel_sessions == []
    assert ws.closed is True


def test_pin_session_prompt_fail_does_not_cancel_or_remint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    mod = _load(ACP_INJECT, "gcs_acp_inject_pin_fail")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    (seat_dir / "acp.session").write_text("sess-pinned\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *_a, **_k: None)
    ws = FakeAcpWs(prompt_chunks=[])
    _patch_connect(mod, ws, monkeypatch)

    async def boom(self: Any, session_id: str, text: str, timeout: float, **kwargs: Any) -> str:
        raise RuntimeError("session/prompt error: shell.prompt.start_blocked")

    monkeypatch.setattr(mod.AcpClient, "session_prompt", boom)
    rc = asyncio.run(mod.inject("floor", "retry", timeout=2.0, pin_session=True))
    out = capsys.readouterr()
    blob = out.out + out.err
    assert rc == 1, blob
    assert "ACP_INJECT_FAIL" in blob
    assert "ACP_INJECT_CANCEL" not in blob
    assert ws.cancel_sessions == []
    assert (seat_dir / "acp.session").read_text(encoding="utf-8").strip() == "sess-pinned"
    assert not (seat_dir / "acp.inject.stale").is_file()


def test_pin_session_cli_flag_present() -> None:
    src = ACP_INJECT.read_text(encoding="utf-8")
    assert "--pin-session" in src
    assert "pin_session" in src
    assert "ACP_INJECT_HANDOFF" in src
    assert "cached_token" in src
