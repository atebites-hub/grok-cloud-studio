"""ACP inject leftover / pin-session rules (studio host OS).

HANDOFF only after STATUS (reason=status) or session/prompt RPC completion
(reason=rpc-complete). Silence is not HANDOFF. Queue is not accept.
Keep-alive chatter and 40-80 char acknowledgements are not leave.
Stay on the websocket after the first tool until STATUS or RPC completes.
Dead sessions remint once after N consecutive no-accepts. RESULT is duplex,
not success. Leftover dispatch still cancels.
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

REPO = Path(__file__).resolve().parents[1]
ACP_INJECT = REPO / "scripts" / "directors" / "acp_inject.py"
DISPATCH = REPO / "scripts" / "a2a" / "dispatch.py"
FOOTER = REPO / "scripts" / "directors" / "common_footer.txt"
A2A_DOC = REPO / "docs" / "A2A.md"
AGENTS_DOC = REPO / "AGENTS.md"

RESULT_LINE = "RESULT bc-id=none pr=none a2a=task-1 notes=park-ok"
STATUS_LINE = "STATUS quoting token tick-1. Working."
KEEPALIVE_LINE = "Keep-alive received. Scanning A2A inboxes, fleet ledgers"
_FORBIDDEN_HANDOFF_REASONS = frozenset(
    {"queue", "tool", "harvest", "substantial-on-keepalive", "substantial"}
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
                    "harvested_early": bool(self._harvested_early),
                    "prompt_accepted": bool(getattr(self, "_prompt_accepted", False)),
                    "tool_events": int(self._tool_events or 0),
                    "chars": len(reply),
                    "reply": reply,
                }
            )
            return reply
        except BaseException:
            flags.append(
                {
                    "harvested_early": bool(self._harvested_early),
                    "prompt_accepted": bool(getattr(self, "_prompt_accepted", False)),
                    "tool_events": int(self._tool_events or 0),
                    "chars": len("".join(self._chunks)),
                    "reply": "".join(self._chunks),
                }
            )
            raise

    monkeypatch.setattr(mod.AcpClient, "session_prompt", wrap)
    return flags


class FakeAcpWs:
    """ACP WebSocket stub. Completes initialize/session/new; optional prompt RPC."""

    def __init__(
        self,
        *,
        prompt_chunks: list[str] | None = None,
        prompt_updates: list[dict[str, Any]] | None = None,
        complete_prompt: bool = False,
        new_session_id: str = "sess-harvest",
        delay_before_rpc: float = 0.0,
        delayed_chunks: list[str] | None = None,
        delay_before_delayed: float = 0.0,
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
        self._complete_prompt = complete_prompt
        self._delay_before_rpc = delay_before_rpc
        self._delayed_chunks = list(delayed_chunks or [])
        self._delay_before_delayed = delay_before_delayed
        self._delayed_task: asyncio.Task[None] | None = None
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
            if self._new_i < len(self._new_session_ids):
                sid = self._new_session_ids[self._new_i]
            else:
                sid = f"sess-harvest-{self._new_i + 1}"
            self._new_i += 1
            await self._incoming.put(
                {"jsonrpc": "2.0", "id": rid, "result": {"sessionId": sid}}
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
                        "error": {
                            "code": -32000,
                            "message": "shell.prompt.start_blocked",
                        },
                    }
                )
                return
            self.prompt_inflight = True
            self.prompt_rpc_ids.append(rid)
            for part in self._prompt_chunks:
                await self._incoming.put(_chunk(part))
            for upd in self._prompt_updates:
                await self._incoming.put(upd)
            if self._delayed_chunks:
                delay = self._delay_before_delayed

                async def _emit_delayed() -> None:
                    if delay > 0:
                        await asyncio.sleep(delay)
                    for part in self._delayed_chunks:
                        await self._incoming.put(_chunk(part))

                self._delayed_task = asyncio.create_task(_emit_delayed())
            if self._complete_prompt:
                if self._delay_before_rpc > 0:
                    await asyncio.sleep(self._delay_before_rpc)
                self.prompt_inflight = False
                await self._incoming.put({"jsonrpc": "2.0", "id": rid, "result": {}})
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
    monkeypatch.setattr(mod, "ROOT", REPO)
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


def _handoff_reasons(blob: str) -> list[str]:
    """Reasons from ACP_INJECT_HANDOFF lines. Forbidden values must never appear."""
    found: list[str] = []
    for line in blob.splitlines():
        if "ACP_INJECT_HANDOFF" not in line:
            continue
        reason = ""
        for part in line.split():
            if part.startswith("reason="):
                reason = part.split("=", 1)[1]
                break
        assert reason, f"HANDOFF missing reason=: {line}"
        assert reason in ("status", "rpc-complete"), reason
        assert reason not in _FORBIDDEN_HANDOFF_REASONS
        found.append(reason)
    return found


def test_seat_produced_work_pong_is_not_work() -> None:
    mod = _load(ACP_INJECT, "gcs_acp_inject_work_fn")
    assert mod.seat_produced_work("PONG") is False
    assert mod.seat_produced_work("ok") is False
    assert mod.seat_produced_work("") is False
    assert mod.seat_produced_work("", tool_events=3) is False
    assert mod.seat_produced_work("   \n", tool_events=1) is False
    assert mod.seat_produced_work(STATUS_LINE) is True
    assert mod.seat_produced_work("Reading docs\n", tool_events=1) is True
    assert mod.seat_produced_work(RESULT_LINE) is False
    assert mod.seat_produced_work(RESULT_LINE, tool_events=2) is False
    assert mod.seat_produced_work(f"{RESULT_LINE}\n") is False
    assert mod.seat_produced_work("x" * 40) is True
    assert mod.seat_produced_work("short") is False
    assert mod.extract_inject_result_line(RESULT_LINE) == RESULT_LINE
    assert mod.extract_inject_result_line(STATUS_LINE) is None
    assert mod.stream_is_hangup_only(RESULT_LINE) is True
    assert mod.stream_is_hangup_only(RESULT_LINE, tool_events=2) is True
    assert mod.stream_is_hangup_only("PONG") is True
    assert mod.stream_is_hangup_only("", tool_events=2) is False
    assert mod.stream_is_hangup_only("") is False
    assert mod.prompt_chunk_is_accept_signal("thinking about the ticket") is True
    assert mod.prompt_chunk_is_accept_signal(RESULT_LINE) is False
    assert mod.prompt_chunk_is_accept_signal("PONG") is False
    assert mod.pin_session_ready_to_leave(STATUS_LINE) is True
    assert mod.pin_session_ready_to_leave("Donald") is False
    assert mod.pin_session_ready_to_leave("x" * 40) is False
    assert mod.pin_session_ready_to_leave("") is False


def test_leftover_tools_empty_text_is_not_work() -> None:
    mod = _load(ACP_INJECT, "gcs_acp_inject_leftover_empty")
    assert not mod.seat_produced_work("", tool_events=3)
    assert not mod.prompt_chunk_is_accept_signal("")
    assert mod.stream_is_hangup_only(RESULT_LINE)
    assert not mod.pin_session_ready_to_leave("Donald")


def test_pin_session_ready_to_leave_keepalive_is_not_leave() -> None:
    """chars=56 keep-alive ack is not leave. STATUS is. leftover+chars=4 is not."""
    mod = _load(ACP_INJECT, "gcs_acp_inject_keepalive_leave")
    assert len(KEEPALIVE_LINE) == 56
    assert mod.pin_session_ready_to_leave(KEEPALIVE_LINE) is False
    assert mod.pin_session_ready_to_leave("x" * 40) is False
    assert mod.pin_session_ready_to_leave("x" * 80) is False
    assert mod.pin_session_ready_to_leave(STATUS_LINE) is True
    assert mod.pin_session_ready_to_leave("Dona") is False
    assert mod.pin_session_ready_to_leave("") is False
    assert mod.prompt_chunk_is_accept_signal("") is False
    assert mod.pin_session_handoff_reason(KEEPALIVE_LINE) is None
    assert mod.pin_session_handoff_reason(STATUS_LINE) == "status"
    assert (
        mod.pin_session_handoff_reason(KEEPALIVE_LINE, rpc_complete=True)
        == "rpc-complete"
    )
    assert mod.pin_session_handoff_reason(RESULT_LINE, rpc_complete=True) is None
    assert mod.pin_session_handoff_reason("", rpc_complete=True) is None
    assert mod.pin_session_handoff_reason("queue/changed", rpc_complete=False) is None


def test_pin_session_keepalive_ack_does_not_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Live hang-up: chars=56 keep-alive speech must not HANDOFF before STATUS/RPC."""
    mod = _load(ACP_INJECT, "gcs_acp_inject_keepalive_hangup")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    (seat_dir / "acp.session").write_text("sess-pinned\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: None)
    flags = _capture_prompt_harvest(mod, monkeypatch)
    ws = FakeAcpWs(prompt_chunks=[KEEPALIVE_LINE])
    _patch_connect(mod, ws, monkeypatch)

    started = time.monotonic()
    rc = asyncio.run(
        mod.inject("floor", "ACP_PING STATUS/CONTINUE", timeout=0.45, pin_session=True)
    )
    elapsed = time.monotonic() - started
    out = capsys.readouterr()
    blob = out.out + out.err
    assert rc == 1, blob
    assert flags and flags[0]["chars"] == 56
    assert flags[0]["harvested_early"] is False
    assert flags[0]["prompt_accepted"] is False
    assert _handoff_reasons(blob) == []
    assert "ACP_INJECT_OK" not in out.out
    assert "ACP_INJECT_TIMEOUT" in blob
    assert "reason=no-accept" in blob
    assert "ACP_INJECT_CANCEL" not in blob
    assert elapsed >= 0.35, f"waited {elapsed:.2f}s; keep-alive ack must not disconnect"
    assert ws.cancel_sessions == []


def test_pin_session_keepalive_then_status_handoff_reason_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Stay through keep-alive chatter; HANDOFF reason=status when STATUS arrives."""
    mod = _load(ACP_INJECT, "gcs_acp_inject_keepalive_then_status")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    (seat_dir / "acp.session").write_text("sess-pinned\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: None)
    flags = _capture_prompt_harvest(mod, monkeypatch)
    ws = FakeAcpWs(
        prompt_chunks=[KEEPALIVE_LINE],
        delayed_chunks=[f"\n{STATUS_LINE}\n"],
        delay_before_delayed=0.4,
    )
    _patch_connect(mod, ws, monkeypatch)

    started = time.monotonic()
    rc = asyncio.run(
        mod.inject("floor", "ACP_PING STATUS/CONTINUE", timeout=2.0, pin_session=True)
    )
    elapsed = time.monotonic() - started
    out = capsys.readouterr()
    blob = out.out + out.err
    assert rc == 0, blob
    assert elapsed >= 0.35, f"waited {elapsed:.2f}s; must not leave on keep-alive"
    assert "ACP_INJECT_OK" in out.out
    assert _handoff_reasons(blob) == ["status"]
    assert "reason=tool" not in blob
    assert "reason=harvest" not in blob
    assert "substantial-on-keepalive" not in blob
    assert "ACP_INJECT_CANCEL" not in blob
    assert flags and flags[0]["chars"] >= 56
    assert ws.cancel_sessions == []


def test_pin_session_keepalive_rpc_complete_handoff_reason_rpc_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Keep-alive ack is not leave; session/prompt RPC completion is reason=rpc-complete."""
    mod = _load(ACP_INJECT, "gcs_acp_inject_keepalive_rpc")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    (seat_dir / "acp.session").write_text("sess-pinned\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: None)
    flags = _capture_prompt_harvest(mod, monkeypatch)
    ws = FakeAcpWs(
        prompt_chunks=[KEEPALIVE_LINE],
        complete_prompt=True,
        delay_before_rpc=0.4,
    )
    _patch_connect(mod, ws, monkeypatch)

    started = time.monotonic()
    rc = asyncio.run(
        mod.inject("floor", "ACP_PING STATUS/CONTINUE", timeout=2.0, pin_session=True)
    )
    elapsed = time.monotonic() - started
    out = capsys.readouterr()
    blob = out.out + out.err
    assert rc == 0, blob
    assert elapsed >= 0.35
    assert "ACP_INJECT_OK" in out.out
    assert "chars=56" in out.out
    assert _handoff_reasons(blob) == ["rpc-complete"]
    assert flags and flags[0]["harvested_early"] is False
    assert "ACP_INJECT_CANCEL" not in blob
    assert ws.cancel_sessions == []


def test_pin_session_leftover_tools_plus_four_chars_is_not_leave(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Leftover tool_events + chars=4 is not ready_to_leave / HANDOFF."""
    mod = _load(ACP_INJECT, "gcs_acp_inject_leftover_four")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    (seat_dir / "acp.session").write_text("sess-pinned\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: None)
    flags = _capture_prompt_harvest(mod, monkeypatch)
    ws = FakeAcpWs(
        prompt_chunks=["Dona"],
        prompt_updates=[_tool_update("tc-stale", "leftover from prior turn")],
    )
    _patch_connect(mod, ws, monkeypatch)

    started = time.monotonic()
    rc = asyncio.run(
        mod.inject("floor", "ACP_PING STATUS/CONTINUE", timeout=0.45, pin_session=True)
    )
    elapsed = time.monotonic() - started
    out = capsys.readouterr()
    blob = out.out + out.err
    assert rc == 1, blob
    assert flags and flags[0]["chars"] == 4
    assert flags[0]["tool_events"] > 0
    assert flags[0]["harvested_early"] is False
    assert _handoff_reasons(blob) == []
    assert "ACP_INJECT_OK" not in out.out
    assert "ACP_INJECT_TIMEOUT" in blob
    assert elapsed >= 0.35
    assert ws.cancel_sessions == []


def test_inject_harvests_status_without_waiting_for_prompt_rpc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    mod = _load(ACP_INJECT, "gcs_acp_inject_harvest")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    duplex_calls: list[tuple[str, str, str]] = []
    flags = _capture_prompt_harvest(mod, monkeypatch)

    def fake_duplex(seat: str, prompt: str, reply: str) -> None:
        duplex_calls.append((seat, prompt, reply))

    monkeypatch.setattr(mod, "_duplex_after_inject", fake_duplex)
    ws = FakeAcpWs(prompt_chunks=[f"{STATUS_LINE}\n", f"{RESULT_LINE}\n"])
    _patch_connect(mod, ws, monkeypatch)

    timeout = 2.0
    started = time.monotonic()
    rc = asyncio.run(mod.inject("floor", "STATUS ping", timeout=timeout))
    elapsed = time.monotonic() - started
    out = capsys.readouterr()
    blob = out.out + out.err

    assert rc == 0, blob
    assert "ACP_INJECT_OK" in out.out
    assert "ACP_INJECT_TIMEOUT" not in blob
    assert flags and flags[0]["harvested_early"] is True
    assert duplex_calls
    assert "RESULT" in duplex_calls[0][2]
    assert elapsed < 1.0, f"waited {elapsed:.2f}s; must not block on session/prompt RPC"
    assert ws.prompt_rpc_ids
    assert ws.cancel_sessions == ["sess-harvest"]
    assert not (seat_dir / "acp.inject.stale").is_file()
    assert ws.auth_method_ids == ["cached_token"]


def test_inject_timeout_with_status_without_result_is_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    mod = _load(ACP_INJECT, "gcs_acp_inject_status_ok")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: None)
    ws = FakeAcpWs(
        prompt_chunks=["STATUS quoting token tick-floor-1. ticket move in_progress.\n"]
    )
    _patch_connect(mod, ws, monkeypatch)

    rc = asyncio.run(mod.inject("floor", "ACP_PING STATUS/CONTINUE", timeout=0.4))
    out = capsys.readouterr()
    blob = out.out + out.err

    assert rc == 0, blob
    assert "ACP_INJECT_OK" in out.out
    assert "ACP_INJECT_TIMEOUT" not in blob
    assert not (seat_dir / "acp.inject.stale").is_file()
    assert ws.cancel_sessions


def test_inject_timeout_without_work_stales(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    mod = _load(ACP_INJECT, "gcs_acp_inject_timeout_fail")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: None)
    ws = FakeAcpWs(prompt_chunks=["PONG\n"])
    _patch_connect(mod, ws, monkeypatch)

    rc = asyncio.run(mod.inject("floor", "STATUS ping", timeout=0.35))
    out = capsys.readouterr()
    blob = out.out + out.err

    assert rc == 1, blob
    assert "ACP_INJECT_TIMEOUT" in blob
    assert "ACP_INJECT_OK" not in out.out
    assert (seat_dir / "acp.inject.stale").is_file()
    assert ws.cancel_sessions == ["sess-harvest"]


def test_first_tool_plus_donald_stays_connected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Accept is not a reason to hang up. Stay until STATUS or RPC complete."""
    mod = _load(ACP_INJECT, "gcs_acp_inject_stay_tool")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    (seat_dir / "acp.session").write_text("sess-pinned\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: None)
    flags = _capture_prompt_harvest(mod, monkeypatch)
    ws = FakeAcpWs(
        prompt_chunks=["Donald"],
        prompt_updates=[_tool_update("tc-1", "read")],
        complete_prompt=True,
        delay_before_rpc=0.55,
    )
    _patch_connect(mod, ws, monkeypatch)

    started = time.monotonic()
    rc = asyncio.run(mod.inject("floor", "PROVE-MIND", timeout=2.0, pin_session=True))
    elapsed = time.monotonic() - started
    out = capsys.readouterr()
    blob = out.out + out.err
    assert rc == 0, blob
    assert elapsed >= 0.5
    assert _handoff_reasons(blob) == ["rpc-complete"]
    assert "ACP_INJECT_OK" in out.out
    assert "ACP_INJECT_CANCEL" not in blob
    assert flags and flags[0]["harvested_early"] is False
    assert flags[0]["tool_events"] >= 1
    assert ws.cancel_sessions == []
    assert (seat_dir / "acp.session").read_text(encoding="utf-8").strip() == "sess-pinned"


def test_pin_session_first_tool_does_not_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """First tool + short text is not HANDOFF. Stay on the websocket until timeout."""
    mod = _load(ACP_INJECT, "gcs_acp_inject_pin_first_tool")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    (seat_dir / "acp.session").write_text("sess-pinned\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: None)
    flags = _capture_prompt_harvest(mod, monkeypatch)
    ws = FakeAcpWs(
        prompt_chunks=["Donald"],
        prompt_updates=[_queue_changed(), _tool_update("tc-1", "read")],
    )
    _patch_connect(mod, ws, monkeypatch)

    started = time.monotonic()
    rc = asyncio.run(mod.inject("floor", "PROVE-MIND", timeout=0.45, pin_session=True))
    elapsed = time.monotonic() - started
    out = capsys.readouterr()
    blob = out.out + out.err
    assert rc == 1, blob
    assert flags and flags[0]["prompt_accepted"] is False
    assert flags[0]["harvested_early"] is False
    assert flags[0]["tool_events"] >= 1
    assert _handoff_reasons(blob) == []
    assert "ACP_INJECT_OK" not in out.out
    assert "ACP_INJECT_TIMEOUT" in blob
    assert "reason=no-accept" in blob
    assert "ACP_INJECT_CANCEL" not in blob
    assert "ACP_INJECT_SESSION_DEAD" not in blob
    assert ws.cancel_sessions == []
    assert elapsed >= 0.35, f"waited {elapsed:.2f}s; first tool must not disconnect"


def test_pin_session_silence_is_not_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    mod = _load(ACP_INJECT, "gcs_acp_inject_pin_silent")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    (seat_dir / "acp.session").write_text("sess-pinned\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: None)
    monkeypatch.setattr(mod, "DEAD_STREAK_N", 2)
    flags = _capture_prompt_harvest(mod, monkeypatch)
    ws = FakeAcpWs(prompt_chunks=[])
    _patch_connect(mod, ws, monkeypatch)

    started = time.monotonic()
    rc = asyncio.run(mod.inject("floor", "PROVE-MIND hang", timeout=0.4, pin_session=True))
    elapsed = time.monotonic() - started
    out = capsys.readouterr()
    blob = out.out + out.err
    assert rc == 1, blob
    assert flags and flags[0]["prompt_accepted"] is False
    assert "ACP_INJECT_HANDOFF" not in blob
    assert "ACP_INJECT_OK" not in out.out
    assert "ACP_INJECT_CANCEL" not in blob
    assert "ACP_INJECT_TIMEOUT" in blob
    assert "reason=no-accept" in blob
    assert "ACP_INJECT_SESSION_DEAD" not in blob
    assert ws.cancel_sessions == []
    assert not any(m.get("method") == "session/new" for m in ws.sent)
    assert elapsed >= 0.3
    assert elapsed < 1.5


def test_pin_session_silence_uses_accept_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No-start nacks at GCS_ACP_ACCEPT_DEADLINE, not the full inject timeout."""
    mod = _load(ACP_INJECT, "gcs_acp_inject_pin_nack_window")
    _prep_seat(mod, tmp_path, monkeypatch)
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: None)
    monkeypatch.setattr(mod, "DEAD_STREAK_N", 2)
    monkeypatch.setattr(mod, "PIN_NACK_SEC", 0.2)
    ws = FakeAcpWs(prompt_chunks=[])
    _patch_connect(mod, ws, monkeypatch)

    started = time.monotonic()
    rc = asyncio.run(mod.inject("floor", "PROVE-MIND hang", timeout=2.0, pin_session=True))
    elapsed = time.monotonic() - started
    out = capsys.readouterr()
    blob = out.out + out.err
    assert rc == 1, blob
    assert "ACP_INJECT_HANDOFF" not in blob
    assert "reason=no-accept" in blob
    assert "ACP_INJECT_SESSION_DEAD" not in blob
    assert elapsed >= 0.15
    assert elapsed < 0.9, f"waited {elapsed:.2f}s; silence must nack at accept deadline"


def test_pin_session_started_stays_past_accept_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """First tool + Donald is a start: stay until RPC, past the 30s-style nack window."""
    mod = _load(ACP_INJECT, "gcs_acp_inject_pin_stay_past_nack")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    (seat_dir / "acp.session").write_text("sess-pinned\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: None)
    monkeypatch.setattr(mod, "PIN_NACK_SEC", 0.15)
    flags = _capture_prompt_harvest(mod, monkeypatch)
    ws = FakeAcpWs(
        prompt_chunks=["Donald"],
        prompt_updates=[_tool_update("tc-1", "read")],
        complete_prompt=True,
        delay_before_rpc=0.4,
    )
    _patch_connect(mod, ws, monkeypatch)

    started = time.monotonic()
    rc = asyncio.run(mod.inject("floor", "PROVE-MIND", timeout=2.0, pin_session=True))
    elapsed = time.monotonic() - started
    out = capsys.readouterr()
    blob = out.out + out.err
    assert rc == 0, blob
    assert elapsed >= 0.35
    assert _handoff_reasons(blob) == ["rpc-complete"]
    assert "ACP_INJECT_OK" in out.out
    assert "ACP_INJECT_CANCEL" not in blob
    assert flags and flags[0]["tool_events"] >= 1
    assert ws.cancel_sessions == []


def test_pin_session_queue_changed_is_not_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    mod = _load(ACP_INJECT, "gcs_acp_inject_pin_queue")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    (seat_dir / "acp.session").write_text("sess-pinned\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: None)
    monkeypatch.setattr(mod, "DEAD_STREAK_N", 2)
    flags = _capture_prompt_harvest(mod, monkeypatch)
    ws = FakeAcpWs(prompt_chunks=[], prompt_updates=[_queue_changed()])
    _patch_connect(mod, ws, monkeypatch)

    started = time.monotonic()
    rc = asyncio.run(
        mod.inject("floor", "TASK_ASSIGN: work the ticket.", timeout=0.4, pin_session=True)
    )
    elapsed = time.monotonic() - started
    out = capsys.readouterr()
    blob = out.out + out.err
    assert rc == 1, blob
    assert _handoff_reasons(blob) == []
    assert "ACP_INJECT_OK" not in out.out
    assert "ACP_INJECT_TIMEOUT" in blob
    assert "reason=no-accept" in blob
    assert flags and flags[0]["prompt_accepted"] is False
    assert ws.cancel_sessions == []
    assert elapsed >= 0.3


def test_empty_stream_leftover_tool_events_does_not_harvest_early(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    mod = _load(ACP_INJECT, "gcs_acp_inject_leftover_tools")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    (seat_dir / "acp.session").write_text("sess-pinned\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: None)
    monkeypatch.setattr(mod, "DEAD_STREAK_N", 2)
    flags = _capture_prompt_harvest(mod, monkeypatch)
    ws = FakeAcpWs(
        prompt_chunks=[],
        prompt_updates=[
            _tool_update("tc-stale", "leftover from prior turn"),
            {
                "jsonrpc": "2.0",
                "method": "session/update",
                "params": {
                    "update": {
                        "sessionUpdate": "tool_call_update",
                        "toolCallId": "tc-stale",
                        "status": "completed",
                    }
                },
            },
        ],
    )
    _patch_connect(mod, ws, monkeypatch)

    started = time.monotonic()
    rc = asyncio.run(
        mod.inject("floor", "ACP_PING STATUS/CONTINUE", timeout=0.4, pin_session=True)
    )
    elapsed = time.monotonic() - started
    out = capsys.readouterr()
    blob = out.out + out.err

    assert rc == 1, blob
    assert flags and flags[0]["harvested_early"] is False
    assert flags[0]["prompt_accepted"] is False
    assert flags[0]["tool_events"] > 0
    assert flags[0]["chars"] == 0
    assert "ACP_INJECT_HANDOFF" not in blob
    assert "ACP_INJECT_OK" not in out.out
    assert "ACP_INJECT_TIMEOUT" in blob
    assert "reason=no-accept" in blob
    assert "ACP_INJECT_CANCEL" not in blob
    assert elapsed >= 0.3
    assert ws.cancel_sessions == []


def test_result_only_stream_is_not_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    mod = _load(ACP_INJECT, "gcs_acp_inject_result_only")
    _prep_seat(mod, tmp_path, monkeypatch)
    duplex_calls: list[Any] = []
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: duplex_calls.append(a))
    monkeypatch.setattr(mod, "DEAD_STREAK_N", 2)
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
    assert "reason=hangup" in blob or "reason=no-accept" in blob
    assert "ACP_INJECT_CANCEL" not in blob
    assert not duplex_calls
    assert ws.cancel_sessions == []


def test_remint_on_dead_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """N=1 no-accept on the same pin-session id allows one session/new."""
    mod = _load(ACP_INJECT, "gcs_acp_inject_pin_dead_once")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    (seat_dir / "acp.session").write_text("sess-pinned\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: None)
    monkeypatch.setattr(mod, "DEAD_STREAK_N", 1)
    ws = FakeAcpWs(prompt_chunks=[], new_session_id="sess-reborn")
    _patch_connect(mod, ws, monkeypatch)

    rc = asyncio.run(mod.inject("floor", "PROVE-MIND", timeout=0.25, pin_session=True))
    out = capsys.readouterr()
    blob = out.out + out.err
    assert rc == 1, blob
    assert "reason=no-accept" in blob
    assert "ACP_INJECT_SESSION_DEAD" in blob
    assert "old=sess-pinned" in blob
    assert "new=sess-reborn" in blob
    assert (seat_dir / "acp.session").read_text(encoding="utf-8").strip() == "sess-reborn"
    assert any(m.get("method") == "session/new" for m in ws.sent)
    assert ws.cancel_sessions == []


def test_pin_session_second_no_accept_remints_dead_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    mod = _load(ACP_INJECT, "gcs_acp_inject_pin_dead")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    (seat_dir / "acp.session").write_text("sess-pinned\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: None)
    monkeypatch.setattr(mod, "DEAD_STREAK_N", 2)
    ws = FakeAcpWs(prompt_chunks=[], new_session_id="sess-reborn")
    _patch_connect(mod, ws, monkeypatch)

    rc1 = asyncio.run(mod.inject("floor", "PROVE-MIND", timeout=0.25, pin_session=True))
    out1 = capsys.readouterr()
    blob1 = out1.out + out1.err
    assert rc1 == 1, blob1
    assert "ACP_INJECT_SESSION_DEAD" not in blob1
    assert (seat_dir / "acp.session").read_text(encoding="utf-8").strip() == "sess-pinned"
    ws.prompt_inflight = False

    rc2 = asyncio.run(mod.inject("floor", "PROVE-MIND", timeout=0.25, pin_session=True))
    out2 = capsys.readouterr()
    blob2 = out2.out + out2.err
    assert rc2 == 1, blob2
    assert "ACP_INJECT_SESSION_DEAD" in blob2
    assert (seat_dir / "acp.session").read_text(encoding="utf-8").strip() == "sess-reborn"
    assert any(m.get("method") == "session/new" for m in ws.sent)


def test_pin_session_success_clears_dead_streak(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    mod = _load(ACP_INJECT, "gcs_acp_inject_pin_streak_reset")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    (seat_dir / "acp.session").write_text("sess-pinned\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: None)
    monkeypatch.setattr(mod, "DEAD_STREAK_N", 2)

    ws_fail = FakeAcpWs(prompt_chunks=[])
    _patch_connect(mod, ws_fail, monkeypatch)
    rc1 = asyncio.run(mod.inject("floor", "miss", timeout=0.25, pin_session=True))
    assert rc1 == 1
    capsys.readouterr()

    ws_ok = FakeAcpWs(prompt_chunks=[f"{STATUS_LINE}\n"])
    _patch_connect(mod, ws_ok, monkeypatch)
    rc_ok = asyncio.run(mod.inject("floor", "STATUS ping", timeout=2.0, pin_session=True))
    out_ok = capsys.readouterr()
    assert rc_ok == 0, out_ok.out + out_ok.err

    ws_fail2 = FakeAcpWs(prompt_chunks=[], new_session_id="sess-should-not")
    _patch_connect(mod, ws_fail2, monkeypatch)
    rc2 = asyncio.run(mod.inject("floor", "miss again", timeout=0.25, pin_session=True))
    out2 = capsys.readouterr()
    blob2 = out2.out + out2.err
    assert rc2 == 1, blob2
    assert "ACP_INJECT_SESSION_DEAD" not in blob2
    assert (seat_dir / "acp.session").read_text(encoding="utf-8").strip() == "sess-pinned"


def test_pin_session_accepted_prompt_disconnect_does_not_cancel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    mod = _load(ACP_INJECT, "gcs_acp_inject_pin_accept")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    (seat_dir / "acp.session").write_text("sess-pinned\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: None)
    flags = _capture_prompt_harvest(mod, monkeypatch)
    ws = FakeAcpWs(prompt_chunks=[f"{STATUS_LINE}\n"])
    _patch_connect(mod, ws, monkeypatch)

    started = time.monotonic()
    rc = asyncio.run(mod.inject("floor", "PROVE-MIND", timeout=2.0, pin_session=True))
    elapsed = time.monotonic() - started
    out = capsys.readouterr()
    blob = out.out + out.err

    assert rc == 0, blob
    assert "ACP_INJECT_OK" in out.out
    assert _handoff_reasons(blob) == ["status"]
    assert "ACP_INJECT_CANCEL" not in blob
    assert flags and flags[0]["prompt_accepted"] is True
    assert elapsed < 1.0
    assert ws.cancel_sessions == []
    assert ws.closed is True
    assert (seat_dir / "acp.session").read_text(encoding="utf-8").strip() == "sess-pinned"


def test_inject_pin_session_success_does_not_remint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    mod = _load(ACP_INJECT, "gcs_acp_inject_pin")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    (seat_dir / "acp.session").write_text("sess-pinned\n", encoding="utf-8")
    (seat_dir / "acp.inject.stale").write_text("leftover\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: None)
    ws = FakeAcpWs(prompt_chunks=[f"{STATUS_LINE}\n", f"{RESULT_LINE}\n"])
    _patch_connect(mod, ws, monkeypatch)

    rc = asyncio.run(mod.inject("floor", "STATUS ping", timeout=2.0, pin_session=True))
    out = capsys.readouterr()
    blob = out.out + out.err

    assert rc == 0, blob
    assert "ACP_INJECT_OK" in out.out
    assert _handoff_reasons(blob) == ["status"]
    assert (seat_dir / "acp.session").read_text(encoding="utf-8").strip() == "sess-pinned"
    assert any(m.get("method") == "session/load" for m in ws.sent)
    assert not any(m.get("method") == "session/new" for m in ws.sent)
    assert ws.cancel_sessions == []


def test_pin_session_prompt_fail_does_not_cancel_or_remint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    mod = _load(ACP_INJECT, "gcs_acp_inject_pin_fail")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    (seat_dir / "acp.session").write_text("sess-pinned\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: None)
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


def test_leftover_dispatch_empty_tools_still_not_work_and_cancels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    mod = _load(ACP_INJECT, "gcs_acp_inject_leftover_dispatch")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: None)
    flags = _capture_prompt_harvest(mod, monkeypatch)
    ws = FakeAcpWs(prompt_chunks=[], prompt_updates=[_tool_update()])
    _patch_connect(mod, ws, monkeypatch)

    rc = asyncio.run(mod.inject("floor", "ACP_PING STATUS/CONTINUE", timeout=0.35))
    out = capsys.readouterr()
    blob = out.out + out.err
    assert rc == 1, blob
    assert flags and flags[0]["harvested_early"] is False
    assert flags[0]["tool_events"] > 0
    assert "ACP_INJECT_OK" not in out.out
    assert "ACP_INJECT_TIMEOUT" in blob
    assert ws.cancel_sessions == ["sess-harvest"]
    assert (seat_dir / "acp.inject.stale").is_file()


def test_leftover_tools_then_status_may_harvest_early(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    mod = _load(ACP_INJECT, "gcs_acp_inject_leftover_then_status")
    _prep_seat(mod, tmp_path, monkeypatch)
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: None)
    flags = _capture_prompt_harvest(mod, monkeypatch)
    ws = FakeAcpWs(
        prompt_chunks=[f"{STATUS_LINE}\n"],
        prompt_updates=[_tool_update("tc-stale", "leftover")],
    )
    _patch_connect(mod, ws, monkeypatch)

    rc = asyncio.run(
        mod.inject("floor", "ACP_PING STATUS/CONTINUE", timeout=2.0, pin_session=True)
    )
    out = capsys.readouterr()
    blob = out.out + out.err
    assert rc == 0, blob
    assert "ACP_INJECT_OK" in out.out
    assert flags and flags[0]["harvested_early"] is True
    assert _handoff_reasons(blob) == ["status"]
    assert ws.cancel_sessions == []


def test_compose_extra_does_not_train_result_only_hangup() -> None:
    dispatch = _load(DISPATCH, "gcs_a2a_dispatch_harvest")
    extra = dispatch._compose_extra("task-1", "ctx-1", "STATUS ping")
    low = extra.lower()
    assert "quoting token then result" not in low
    assert "print a result" not in low
    assert "do not idle" in low or "tools are allowed" in low or "remain" in low
    assert "duplex" in low
    assert "send.sh" in extra or "a2a_send" in extra


def test_footer_and_docs_do_not_train_result_only_hangup() -> None:
    footer = FOOTER.read_text(encoding="utf-8")
    footer_l = footer.lower()
    assert "stay silent after" not in footer_l
    assert "result-only" in footer_l
    assert "do not idle" in footer_l or "remain" in footer_l
    a2a = A2A_DOC.read_text(encoding="utf-8").lower()
    agents = AGENTS_DOC.read_text(encoding="utf-8").lower()
    blob = a2a + "\n" + agents
    assert "session/cancel" in blob or "do not session/cancel" in blob
    assert "cached_token" in blob or "auth.json" in blob
    assert "handoff" in blob
    assert "reason=status" in blob
    assert "rpc-complete" in blob
    assert "keep-alive" in blob or "keepalive" in blob
    assert "queue/changed" in blob
    assert "no-accept" in blob or "dead session" in blob
    assert "silence" in blob or "not a start" in blob
    assert "wake-daemon" in blob or "seat-wake-loop" in blob
