"""ACP inject HANDOFF: this-prompt tool or non-RESULT session/update only.

Contract:
- HANDOFF only on this-prompt tool or non-RESULT session/update.
- Never 1s silence. Never queue/changed alone.
- Remint-once after no-accept, on the same websocket after start.
- 30s accept deadline. Leftover dispatch still harvests RESULT.
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
INJECT_PY = ROOT / "scripts" / "directors" / "acp_inject.py"

RESULT_LINE = "RESULT bc-id=none pr=none a2a=task-1 notes=park-ok"
STATUS_LINE = "STATUS quoting token tick-1. Working."
BANNED_INJECT = (
    "Agent Kanban",
    "AK_BRIDGE",
    "ak start",
    "GROW",
)


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


def _tool_call(tool_call_id: str = "tc-1", title: str = "read") -> dict[str, Any]:
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


def _tool_call_update(tool_call_id: str = "tc-stale") -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {
            "update": {
                "sessionUpdate": "tool_call_update",
                "toolCallId": tool_call_id,
                "status": "completed",
            }
        },
    }


def _queue_changed(size: int = 1) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "method": "x.ai/queue/changed",
        "params": {"size": size},
    }


class FakeAcpWs:
    """ACP WebSocket stub. Completes initialize/session/new; prompt RPC stays open."""

    def __init__(
        self,
        *,
        prompt_chunks: list[str] | None = None,
        prompt_updates: list[dict[str, Any]] | None = None,
        new_session_id: str = "sess-fresh",
    ) -> None:
        self._incoming: asyncio.Queue[Any] = asyncio.Queue()
        self.sent: list[dict[str, Any]] = []
        self.prompt_rpc_ids: list[Any] = []
        self.cancel_sessions: list[str] = []
        self.connects = 0
        self.prompt_inflight = False
        self.closed = False
        self._prompt_chunks = list(prompt_chunks or [])
        self._prompt_updates = list(prompt_updates or [])
        self._new_session_ids = [new_session_id]
        self._new_i = 0

    async def send(self, text: str) -> None:
        msg = json.loads(text)
        self.sent.append(msg)
        method = msg.get("method")
        rid = msg.get("id")
        params = msg.get("params") or {}
        if method == "initialize":
            await self._incoming.put(
                {"jsonrpc": "2.0", "id": rid, "result": {"protocolVersion": 1}}
            )
        elif method == "session/new":
            if self._new_i < len(self._new_session_ids):
                sid = self._new_session_ids[self._new_i]
            else:
                sid = f"sess-fresh-{self._new_i + 1}"
            self._new_i += 1
            await self._incoming.put(
                {"jsonrpc": "2.0", "id": rid, "result": {"sessionId": sid}}
            )
        elif method == "session/load":
            await self._incoming.put({"jsonrpc": "2.0", "id": rid, "result": {}})
        elif method == "session/prompt":
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
        ws.connects += 1
        ws._incoming = asyncio.Queue()
        self._ws = ws
        self._use_stdlib = True
        self._reader_task = asyncio.create_task(self._read_loop())

    monkeypatch.setattr(mod.AcpClient, "connect", fake_connect)


def _capture_prompt(mod: ModuleType, monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
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
                    "chars": len("".join(getattr(self, "_chunks", []) or [])),
                    "reply": "".join(getattr(self, "_chunks", []) or []),
                }
            )
            raise

    monkeypatch.setattr(mod.AcpClient, "session_prompt", wrap)
    return flags


def test_inject_script_has_no_ak_mentions() -> None:
    text = INJECT_PY.read_text(encoding="utf-8")
    lowered = text.lower()
    for token in BANNED_INJECT:
        assert token.lower() not in lowered, token
    assert "agent kanban" not in lowered
    assert "ak_bridge" not in lowered


def test_handoff_predicate_and_accept_deadline() -> None:
    mod = _load(INJECT_PY, "gcs_acp_inject_handoff_pred")
    assert mod.ACCEPT_DEADLINE_SEC == 30.0
    assert mod.pin_accept_wait(180.0) == 30.0
    assert mod.pin_accept_wait(0.4) == 0.4
    assert mod.is_handoff_signal("thinking about the ticket") is True
    assert mod.is_handoff_signal(STATUS_LINE) is True
    assert mod.is_handoff_signal("Reading docs\n", tool_events=1) is True
    assert mod.is_handoff_signal(RESULT_LINE) is False
    assert mod.is_handoff_signal("PONG") is False
    assert mod.is_handoff_signal("") is False
    assert mod.is_handoff_signal("", tool_events=3) is False
    assert mod.is_handoff_signal("", queued=True) is False
    assert mod.is_handoff_signal(RESULT_LINE, tool_events=2) is False


def test_handoff_on_non_result_session_update(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Non-RESULT session/update is HANDOFF. Do not session/cancel the live turn."""
    mod = _load(INJECT_PY, "gcs_acp_inject_handoff_status")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    (seat_dir / "acp.session").write_text("sess-pinned\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *_a, **_k: None)
    flags = _capture_prompt(mod, monkeypatch)
    ws = FakeAcpWs(prompt_chunks=[f"{STATUS_LINE}\n"])
    _patch_connect(mod, ws, monkeypatch)

    started = time.monotonic()
    rc = asyncio.run(mod.inject("floor", "STATUS ping", timeout=2.0, pin_session=True))
    elapsed = time.monotonic() - started
    captured = capsys.readouterr()
    blob = captured.out + captured.err

    assert rc == 0, blob
    assert "ACP_INJECT_HANDOFF" in blob
    assert "ACP_INJECT_OK" in blob
    assert "ACP_INJECT_TIMEOUT" not in blob
    assert "ACP_INJECT_CANCEL" not in blob
    assert flags and flags[0]["prompt_accepted"] is True
    assert elapsed < 1.0, f"waited {elapsed:.2f}s; STATUS must HANDOFF without babysitting RPC"
    assert ws.cancel_sessions == []
    assert ws.closed is True
    assert ws.prompt_inflight is True
    assert ws.connects == 1
    assert (seat_dir / "acp.session").read_text(encoding="utf-8").strip() == "sess-pinned"


def test_handoff_on_this_prompt_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """This-prompt tool + assistant text is HANDOFF, not leftover noise."""
    mod = _load(INJECT_PY, "gcs_acp_inject_handoff_tool")
    _prep_seat(mod, tmp_path, monkeypatch)
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *_a, **_k: None)
    flags = _capture_prompt(mod, monkeypatch)
    ws = FakeAcpWs(
        prompt_chunks=["Reading docs\n"],
        prompt_updates=[_tool_call("tc-1", "read")],
    )
    _patch_connect(mod, ws, monkeypatch)

    rc = asyncio.run(mod.inject("floor", "work the ticket", timeout=2.0, pin_session=True))
    captured = capsys.readouterr()
    blob = captured.out + captured.err
    assert rc == 0, blob
    assert "ACP_INJECT_HANDOFF" in blob
    assert "ACP_INJECT_OK" in blob
    assert "ACP_INJECT_TIMEOUT" not in blob
    assert "ACP_INJECT_CANCEL" not in blob
    assert flags and flags[0]["tool_events"] >= 1
    assert flags[0]["prompt_accepted"] is True
    assert ws.cancel_sessions == []
    assert ws.prompt_inflight is True
    assert ws.connects == 1


def test_silence_is_not_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Silence is never mail delivered. Stay on the websocket until the accept deadline."""
    mod = _load(INJECT_PY, "gcs_acp_inject_handoff_silence")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    (seat_dir / "acp.session").write_text("sess-pinned\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *_a, **_k: None)
    flags = _capture_prompt(mod, monkeypatch)
    ws = FakeAcpWs(prompt_chunks=[], new_session_id="sess-remint")
    _patch_connect(mod, ws, monkeypatch)

    started = time.monotonic()
    rc = asyncio.run(mod.inject("floor", "wake", timeout=0.4, pin_session=True))
    elapsed = time.monotonic() - started
    captured = capsys.readouterr()
    blob = captured.out + captured.err

    assert rc == 1, blob
    assert flags and flags[0]["prompt_accepted"] is False
    assert "ACP_INJECT_HANDOFF" not in blob
    assert "ACP_INJECT_OK" not in blob
    assert "ACP_INJECT_CANCEL" not in blob
    assert "ACP_INJECT_TIMEOUT" in blob
    assert "reason=no-accept" in blob
    assert elapsed >= 0.3, f"waited {elapsed:.2f}s; must not HANDOFF on 1s silence"
    assert elapsed < 1.5, f"waited {elapsed:.2f}s; test deadline is 0.4s"
    assert ws.connects == 1
    assert ws.closed is True
    assert ws.cancel_sessions == []


def test_queue_changed_alone_is_not_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """x.ai/queue/changed alone is submit, not a start. Do not HANDOFF."""
    mod = _load(INJECT_PY, "gcs_acp_inject_handoff_queue")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    (seat_dir / "acp.session").write_text("sess-pinned\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *_a, **_k: None)
    flags = _capture_prompt(mod, monkeypatch)
    ws = FakeAcpWs(prompt_chunks=[], prompt_updates=[_queue_changed()], new_session_id="sess-remint")
    _patch_connect(mod, ws, monkeypatch)

    started = time.monotonic()
    rc = asyncio.run(mod.inject("floor", "TASK_ASSIGN: work", timeout=0.4, pin_session=True))
    elapsed = time.monotonic() - started
    captured = capsys.readouterr()
    blob = captured.out + captured.err

    assert rc == 1, blob
    assert "ACP_INJECT_HANDOFF" not in blob
    assert "ACP_INJECT_OK" not in blob
    assert "ACP_INJECT_TIMEOUT" in blob
    assert "reason=no-accept" in blob
    assert flags and flags[0]["prompt_accepted"] is False
    assert ws.cancel_sessions == []
    assert elapsed >= 0.3, f"waited {elapsed:.2f}s; queue-only must not early-HANDOFF"
    assert ws.connects == 1


def test_leftover_tools_alone_are_not_this_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Leftover tool_call notifications with zero assistant chars are not this-prompt."""
    mod = _load(INJECT_PY, "gcs_acp_inject_handoff_leftover")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    (seat_dir / "acp.session").write_text("sess-pinned\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *_a, **_k: None)
    flags = _capture_prompt(mod, monkeypatch)
    ws = FakeAcpWs(
        prompt_chunks=[],
        prompt_updates=[_tool_call("tc-stale", "leftover"), _tool_call_update("tc-stale")],
        new_session_id="sess-remint",
    )
    _patch_connect(mod, ws, monkeypatch)

    started = time.monotonic()
    rc = asyncio.run(mod.inject("floor", "STATUS ping", timeout=0.4, pin_session=True))
    elapsed = time.monotonic() - started
    captured = capsys.readouterr()
    blob = captured.out + captured.err

    assert rc == 1, blob
    assert flags and flags[0]["prompt_accepted"] is False
    assert flags[0]["tool_events"] > 0
    assert flags[0]["chars"] == 0
    assert "ACP_INJECT_HANDOFF" not in blob
    assert "ACP_INJECT_OK" not in blob
    assert "reason=no-accept" in blob
    assert elapsed >= 0.3, f"waited {elapsed:.2f}s; leftover tools must not early-HANDOFF"
    assert ws.cancel_sessions == []
    assert ws.connects == 1


def test_result_only_is_not_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """RESULT hang-up with no other session/update is not HANDOFF."""
    mod = _load(INJECT_PY, "gcs_acp_inject_handoff_result_only")
    _prep_seat(mod, tmp_path, monkeypatch)
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *_a, **_k: None)
    flags = _capture_prompt(mod, monkeypatch)
    ws = FakeAcpWs(prompt_chunks=[f"{RESULT_LINE}\n"], new_session_id="sess-remint")
    _patch_connect(mod, ws, monkeypatch)

    rc = asyncio.run(mod.inject("floor", "STATUS ping", timeout=0.4, pin_session=True))
    captured = capsys.readouterr()
    blob = captured.out + captured.err

    assert rc == 1, blob
    assert flags and flags[0]["prompt_accepted"] is False
    assert "ACP_INJECT_HANDOFF" not in blob
    assert "ACP_INJECT_OK" not in blob
    assert "ACP_INJECT_TIMEOUT" in blob
    assert "ACP_INJECT_CANCEL" not in blob
    assert ws.cancel_sessions == []
    assert ws.connects == 1


def test_no_accept_remints_once_on_same_websocket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """After no-accept, remint once on the same websocket. Do not reconnect."""
    mod = _load(INJECT_PY, "gcs_acp_inject_handoff_remint")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    (seat_dir / "acp.session").write_text("sess-pinned\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *_a, **_k: None)
    ws = FakeAcpWs(prompt_chunks=[], new_session_id="sess-remint")
    _patch_connect(mod, ws, monkeypatch)

    rc = asyncio.run(mod.inject("floor", "wake", timeout=0.35, pin_session=True))
    captured = capsys.readouterr()
    blob = captured.out + captured.err

    assert rc == 1, blob
    assert "reason=no-accept" in blob
    assert "ACP_INJECT_HANDOFF" not in blob
    assert "ACP_INJECT_REMINT" in blob
    assert "old=sess-pinned" in blob
    assert "new=sess-remint" in blob
    assert (seat_dir / "acp.session").read_text(encoding="utf-8").strip() == "sess-remint"
    assert ws.connects == 1, "remint must stay on the websocket after start"
    assert sum(1 for m in ws.sent if m.get("method") == "session/new") == 1
    assert any(m.get("method") == "session/load" for m in ws.sent)
    assert any(m.get("method") == "session/prompt" for m in ws.sent)
    assert ws.cancel_sessions == []
    assert ws.closed is True


def test_handoff_success_does_not_remint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A true HANDOFF keeps the pinned session id."""
    mod = _load(INJECT_PY, "gcs_acp_inject_handoff_keep")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    (seat_dir / "acp.session").write_text("sess-pinned\n", encoding="utf-8")
    (seat_dir / "acp.inject.stale").write_text("leftover\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *_a, **_k: None)
    ws = FakeAcpWs(prompt_chunks=[f"{STATUS_LINE}\n", f"{RESULT_LINE}\n"])
    _patch_connect(mod, ws, monkeypatch)

    rc = asyncio.run(mod.inject("floor", "STATUS ping", timeout=2.0, pin_session=True))
    captured = capsys.readouterr()
    blob = captured.out + captured.err

    assert rc == 0, blob
    assert "ACP_INJECT_HANDOFF" in blob
    assert "ACP_INJECT_REMINT" not in blob
    assert (seat_dir / "acp.session").read_text(encoding="utf-8").strip() == "sess-pinned"
    assert not any(m.get("method") == "session/new" for m in ws.sent)
    assert not (seat_dir / "acp.inject.stale").is_file()
    assert ws.cancel_sessions == []
    assert ws.connects == 1
