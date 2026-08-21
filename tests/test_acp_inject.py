"""ACP inject leftover / pin-session rules (studio host OS).

GROW stay-connected law: HANDOFF only after this-prompt STATUS or a
this-prompt work tool on invoked argv. Keep-alive chatter (any length)
is not HANDOFF. Queue is not accept. Stay on the websocket after the
first accept signal until STATUS / work tool or the full inject timeout.
Dead sessions remint once after 3 consecutive no-start nacks (not 1).
Accept deadline default 120s (not 30). RESULT is duplex, not success.
Leftover dispatch still cancels. Tests are the spec: they fail if
defaults revert to 30s / streak=1.
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
ENV_EXAMPLE = REPO / ".env.example"
WAKE_PY = REPO / "scripts" / "a2a" / "wake-daemon.py"

RESULT_LINE = "RESULT bc-id=none pr=none a2a=task-1 notes=park-ok"
STATUS_LINE = "STATUS quoting token tick-1. Working."
KEEP_ALIVE_LINE = "Keep-alive received. Scanning A2A inboxes, fleet ledgers"
KEEP_ALIVE_PARK_LINE = (
    "Keep-alive received. I'll check PARK, ownership, and current fleet/board "
    "state before deciding whether to launch or stay with existing work."
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


def _tool_update(
    tool_call_id: str = "tc-stale",
    title: str = "leftover",
    *,
    command: str | None = None,
    session_update: str = "tool_call",
) -> dict[str, Any]:
    update: dict[str, Any] = {
        "sessionUpdate": session_update,
        "toolCallId": tool_call_id,
        "title": title,
    }
    if command is not None:
        update["kind"] = "execute"
        update["rawInput"] = {"command": command}
    return {
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {"update": update},
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
                    "work_tools": int(getattr(self, "_work_tools", 0) or 0),
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
                    "work_tools": int(getattr(self, "_work_tools", 0) or 0),
                    "chars": len("".join(self._chunks)),
                    "reply": "".join(self._chunks),
                }
            )
            raise

    monkeypatch.setattr(mod.AcpClient, "session_prompt", wrap)
    return flags


def _handoff_lines(blob: str) -> list[str]:
    return [ln for ln in blob.splitlines() if "ACP_INJECT_HANDOFF" in ln]


def _assert_handoff_reason(blob: str, expected: str) -> None:
    """HANDOFF reason is status|work — never queue, tool, harvest, substantial."""
    assert expected in ("status", "work"), expected
    lines = _handoff_lines(blob)
    assert lines, blob
    for ln in lines:
        assert f"reason={expected}" in ln, ln
        assert "reason=queue" not in ln, ln
        assert "reason=tool" not in ln, ln
        assert "reason=harvest" not in ln, ln
        assert "reason=substantial" not in ln, ln
        assert "queue,tool,harvest" not in ln, ln


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
        later_chunks: list[str] | None = None,
        later_updates: list[dict[str, Any]] | None = None,
        later_delay: float = 0.0,
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
        self._later_chunks = list(later_chunks or [])
        self._later_updates = list(later_updates or [])
        self._later_delay = later_delay
        self._later_task: asyncio.Task[None] | None = None
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
            if self._later_chunks or self._later_updates:
                self._later_task = asyncio.create_task(self._emit_later())
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

    async def _emit_later(self) -> None:
        if self._later_delay > 0:
            await asyncio.sleep(self._later_delay)
        for part in self._later_chunks:
            await self._incoming.put(_chunk(part))
        for upd in self._later_updates:
            await self._incoming.put(upd)

    async def recv(self) -> str:
        item = await self._incoming.get()
        if item is None:
            raise ConnectionError("WS closed")
        if isinstance(item, str):
            return item
        return json.dumps(item)

    async def close(self) -> None:
        self.closed = True
        task = self._later_task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


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


def test_grow_law_defaults_in_source_not_overlay() -> None:
    """Spec: defaults live in acp_inject.py. Revert to 30s/streak=1 and fail."""
    src = ACP_INJECT.read_text(encoding="utf-8")
    wake_src = WAKE_PY.read_text(encoding="utf-8")
    env = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert 'os.environ.get("GCS_ACP_ACCEPT_DEADLINE", "120")' in src
    assert 'os.environ.get("GCS_ACP_DEAD_STREAK", "3")' in src
    assert 'os.environ.get("GCS_ACP_ACCEPT_DEADLINE", "30")' not in src
    assert 'os.environ.get("GCS_ACP_DEAD_STREAK", "1")' not in src
    assert 'os.environ.get("GCS_WAKE_ACP_TIMEOUT", "600")' in wake_src
    assert 'os.environ.get("GCS_WAKE_ACP_TIMEOUT", "180")' not in wake_src
    assert "GCS_ACP_ACCEPT_DEADLINE=120" in env
    assert "GCS_ACP_DEAD_STREAK=3" in env
    assert "GCS_ACP_ACCEPT_DEADLINE=30" not in env
    assert "GCS_ACP_DEAD_STREAK=1" not in env
    assert "GCS_WAKE_ACP_TIMEOUT=600" in env
    assert "GROW stay-connected contract" in src
    assert "studio.env overlay" in src


def test_leftover_tools_empty_text_is_not_work() -> None:
    mod = _load(ACP_INJECT, "gcs_acp_inject_leftover_empty")
    assert not mod.seat_produced_work("", tool_events=3)
    assert not mod.prompt_chunk_is_accept_signal("")
    assert mod.stream_is_hangup_only(RESULT_LINE)
    assert not mod.pin_session_ready_to_leave("Donald")


def test_pin_session_ready_to_leave_ignores_leftover_harvest() -> None:
    """pin_session + tools + chars=4 is not leave. STATUS / work-tool are."""
    mod = _load(ACP_INJECT, "gcs_acp_inject_pin_leave_fn")
    leftover = "abcd"
    assert len(leftover) == 4
    assert len(KEEP_ALIVE_LINE) == 56
    assert not mod.pin_session_ready_to_leave(leftover, tool_events=3)
    assert not mod.pin_session_ready_to_leave("Donald", tool_events=1)
    assert not mod.pin_session_ready_to_leave("")
    assert not mod.pin_session_ready_to_leave("x" * 40, tool_events=2)
    assert not mod.pin_session_ready_to_leave(KEEP_ALIVE_LINE)
    assert not mod.pin_session_ready_to_leave(KEEP_ALIVE_LINE, tool_events=4)
    assert not mod.pin_session_ready_to_leave(RESULT_LINE, work_tools=0)
    assert mod.pin_session_ready_to_leave(STATUS_LINE, tool_events=9) is True
    assert mod.pin_session_ready_to_leave(KEEP_ALIVE_LINE, work_tools=1) is True
    assert mod.pin_session_handoff_reason(STATUS_LINE, tool_events=4) == "status"
    assert mod.pin_session_handoff_reason(KEEP_ALIVE_LINE, work_tools=1) == "work"
    assert mod.pin_session_handoff_reason(STATUS_LINE, work_tools=1) == "status"
    assert mod.pin_session_handoff_reason("x" * 40, tool_events=1) is None
    assert mod.pin_session_handoff_reason(KEEP_ALIVE_LINE) is None
    assert mod.pin_session_handoff_reason(leftover, tool_events=3) is None
    assert mod.pin_session_handoff_reason("", tool_events=2) is None
    for reason in (
        mod.pin_session_handoff_reason(STATUS_LINE),
        mod.pin_session_handoff_reason(KEEP_ALIVE_LINE, work_tools=1),
        mod.pin_session_handoff_reason(leftover, tool_events=3),
    ):
        if reason is None:
            continue
        assert reason in ("status", "work")
        assert reason not in {"queue", "tool", "harvest", "substantial", "queue,tool,harvest"}


def test_keep_alive_scanning_sentence_is_not_ready_to_leave() -> None:
    """LIVE 2026-08-21T03:31Z floor-ops keep-alive sentence must not HANDOFF."""
    mod = _load(ACP_INJECT, "gcs_acp_inject_keepalive_leave")
    sentence = "Keep-alive received. Scanning A2A inboxes, fleet ledgers"
    assert sentence == KEEP_ALIVE_LINE
    assert len(sentence) == 56
    assert mod.pin_session_ready_to_leave(sentence) is False
    assert mod.pin_session_ready_to_leave(sentence, tool_events=2) is False
    assert mod.pin_session_handoff_reason(sentence) is None


def test_keep_alive_park_sentence_is_not_ready_to_leave() -> None:
    """LIVE 2026-08-21T05:23:44Z 140-char keep-alive must not HANDOFF."""
    mod = _load(ACP_INJECT, "gcs_acp_inject_keepalive_park")
    sentence = KEEP_ALIVE_PARK_LINE
    assert len(sentence) == 140
    assert mod.pin_session_ready_to_leave(sentence) is False
    assert mod.pin_session_ready_to_leave(sentence, tool_events=2) is False
    assert mod.pin_session_handoff_reason(sentence) is None
    assert mod.pin_session_handoff_reason(sentence, work_tools=0) is None


def test_this_prompt_work_tool_is_not_leftover() -> None:
    mod = _load(ACP_INJECT, "gcs_acp_inject_work_tool_fn")
    send = {
        "sessionUpdate": "tool_call",
        "title": "bash",
        "rawInput": {"command": "scripts/a2a/send.sh ops ping"},
    }
    board = {
        "sessionUpdate": "tool_call",
        "title": "bash",
        "kind": "execute",
        "rawInput": {"command": "ticket move PAL-1 done"},
    }
    launch = {
        "sessionUpdate": "tool_call",
        "kind": "execute",
        "rawInput": {"command": "scripts/launch-cloud-extra-high.sh --name floor-iac"},
    }
    leftover_update = {
        "sessionUpdate": "tool_call_update",
        "title": "scripts/a2a/send.sh ops ping",
        "status": "completed",
    }
    generic = {"sessionUpdate": "tool_call", "title": "read", "rawInput": {"path": "docs/A2A.md"}}
    assert mod.is_this_prompt_work_tool(send) is True
    assert mod.is_this_prompt_work_tool(board) is True
    assert mod.is_this_prompt_work_tool(launch) is True
    assert mod.is_this_prompt_work_tool(leftover_update) is False
    assert mod.is_this_prompt_work_tool(generic) is False
    assert mod.is_this_prompt_work_tool({"sessionUpdate": "agent_thought_chunk"}) is False


def test_list_dir_on_taskboard_path_is_not_this_prompt_work() -> None:
    """LIVE: list_dir / read / grep of a path containing taskboard is not work."""
    mod = _load(ACP_INJECT, "gcs_acp_inject_listdir_taskboard")
    list_dir = {
        "sessionUpdate": "tool_call",
        "title": "list_dir",
        "kind": "read",
        "rawInput": {"path": "/workspace/.a2a-state/taskboard"},
    }
    read_board = {
        "sessionUpdate": "tool_call",
        "title": "read",
        "kind": "read",
        "rawInput": {"path": "/workspace/.a2a-state/taskboard/PAL-1.md"},
    }
    grep_board = {
        "sessionUpdate": "tool_call",
        "title": "grep",
        "kind": "search",
        "rawInput": {"path": "/opt/tcarac/taskboard", "pattern": "PAL-1"},
    }
    cwd_ls = {
        "sessionUpdate": "tool_call",
        "title": "bash",
        "kind": "execute",
        "rawInput": {"command": "ls", "cwd": "/home/floor/taskboard"},
    }
    read_send = {
        "sessionUpdate": "tool_call",
        "title": "read",
        "rawInput": {"path": "scripts/a2a/send.sh"},
    }
    assert mod.is_this_prompt_work_tool(list_dir) is False
    assert mod.is_this_prompt_work_tool(read_board) is False
    assert mod.is_this_prompt_work_tool(grep_board) is False
    assert mod.is_this_prompt_work_tool(cwd_ls) is False
    assert mod.is_this_prompt_work_tool(read_send) is False


def test_shell_inspect_of_work_script_path_is_not_this_prompt_work() -> None:
    """LIVE: Shell ls/cat/rg of launch-cloud-extra-high.sh or send.sh is not work.

    Matching the flattened tool_call blob treats a path/help string as a
    mutation. Work must be the invoked argv, not cwd/description/path.
    """
    mod = _load(ACP_INJECT, "gcs_acp_inject_shell_inspect_argv")
    ls_launch = {
        "sessionUpdate": "tool_call",
        "title": "Shell",
        "kind": "execute",
        "rawInput": {"command": "ls scripts/launch-cloud-extra-high.sh"},
    }
    cat_send = {
        "sessionUpdate": "tool_call",
        "title": "Shell",
        "kind": "execute",
        "rawInput": {"command": "cat scripts/a2a/send.sh"},
    }
    rg_launch = {
        "sessionUpdate": "tool_call",
        "title": "bash",
        "kind": "execute",
        "rawInput": {"command": "rg launch-cloud-extra-high scripts/"},
    }
    help_blob = {
        "sessionUpdate": "tool_call",
        "title": "Shell",
        "kind": "execute",
        "rawInput": {
            "command": "ls scripts/",
            "description": "help: launch-cloud-extra-high.sh and send.sh",
            "working_directory": "/workspace",
        },
    }
    argv_ls = {
        "sessionUpdate": "tool_call",
        "title": "Shell",
        "rawInput": {"argv": ["ls", "scripts/launch-cloud-extra-high.sh"]},
    }
    assert mod.is_this_prompt_work_tool(ls_launch) is False
    assert mod.is_this_prompt_work_tool(cat_send) is False
    assert mod.is_this_prompt_work_tool(rg_launch) is False
    assert mod.is_this_prompt_work_tool(help_blob) is False
    assert mod.is_this_prompt_work_tool(argv_ls) is False


def test_ticket_move_cli_is_this_prompt_work() -> None:
    """ticket move / ticket create / tb move|create / send / launch are work."""
    mod = _load(ACP_INJECT, "gcs_acp_inject_ticket_move_work")
    move = {
        "sessionUpdate": "tool_call",
        "title": "bash",
        "kind": "execute",
        "rawInput": {"command": "ticket move PAL-1 done"},
    }
    create = {
        "sessionUpdate": "tool_call",
        "title": "bash",
        "kind": "execute",
        "rawInput": {"command": "ticket create --title floor-follow-up"},
    }
    tb_move = {
        "sessionUpdate": "tool_call",
        "title": "bash",
        "kind": "execute",
        "rawInput": {"command": "tb move PAL-1 in_progress"},
    }
    tb_create = {
        "sessionUpdate": "tool_call",
        "title": "bash",
        "rawInput": {"command": "tb create follow-up"},
    }
    a2a_msg = {
        "sessionUpdate": "tool_call",
        "title": "bash",
        "rawInput": {
            "command": "curl -X POST http://127.0.0.1:8732/a2a/ops/message:send -d '{}'"
        },
    }
    a2a_prose = {
        "sessionUpdate": "tool_call",
        "title": "a2a message send",
        "rawInput": {"seat": "ops", "text": "ping"},
    }
    assert mod.is_this_prompt_work_tool(move) is True
    assert mod.is_this_prompt_work_tool(create) is True
    assert mod.is_this_prompt_work_tool(tb_move) is True
    assert mod.is_this_prompt_work_tool(tb_create) is True
    assert mod.is_this_prompt_work_tool(a2a_msg) is True
    assert mod.is_this_prompt_work_tool(a2a_prose) is True


def test_return_prompt_stream_leftover_harvest_is_not_handoff() -> None:
    """accepted=True + leftover harvest (tools + chars=4) must not HANDOFF."""

    async def _run() -> None:
        mod = _load(ACP_INJECT, "gcs_acp_inject_return_stream")
        client = mod.AcpClient("ws://127.0.0.1:1", str(REPO))
        client._pin_wait = True
        client._tool_events = 2
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        client._pending[7] = fut
        reply = client._return_prompt_stream(7, fut, "abcd", accepted=True)
        assert reply == "abcd"
        assert client._prompt_accepted is False
        assert client._harvested_early is False
        assert 7 in client._pending
        assert not fut.done()

        fut_status = loop.create_future()
        client._pending[8] = fut_status
        client._return_prompt_stream(8, fut_status, STATUS_LINE, accepted=True)
        assert client._prompt_accepted is True
        assert 8 not in client._pending

        client._prompt_accepted = False
        client._harvested_early = False
        fut_long = loop.create_future()
        client._pending[9] = fut_long
        client._return_prompt_stream(9, fut_long, "y" * 40, accepted=True)
        assert client._prompt_accepted is False
        assert 9 in client._pending

        client._work_tools = 1
        fut_work = loop.create_future()
        client._pending[10] = fut_work
        client._return_prompt_stream(10, fut_work, KEEP_ALIVE_LINE, accepted=True)
        assert client._prompt_accepted is True
        assert 10 not in client._pending

    asyncio.run(_run())


def test_pin_session_leftover_harvest_chars4_does_not_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Live hang-up: queue + leftover tools + chars=4 is a start, not a leave."""
    mod = _load(ACP_INJECT, "gcs_acp_inject_pin_harvest4")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    (seat_dir / "acp.session").write_text("sess-pinned\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: None)
    flags = _capture_prompt_harvest(mod, monkeypatch)
    ws = FakeAcpWs(
        prompt_chunks=["abcd"],
        prompt_updates=[_queue_changed(), _tool_update("tc-stale", "leftover")],
    )
    _patch_connect(mod, ws, monkeypatch)

    started = time.monotonic()
    rc = asyncio.run(mod.inject("floor", "PROVE-MIND", timeout=0.45, pin_session=True))
    elapsed = time.monotonic() - started
    out = capsys.readouterr()
    blob = out.out + out.err
    assert rc == 1, blob
    assert flags and flags[0]["chars"] == 4
    assert flags[0]["tool_events"] > 0
    assert flags[0]["prompt_accepted"] is False
    assert flags[0]["harvested_early"] is False
    assert "ACP_INJECT_HANDOFF" not in blob
    assert "queue,tool,harvest" not in blob
    assert "reason=queue" not in blob
    assert "ACP_INJECT_OK" not in out.out
    assert "ACP_INJECT_TIMEOUT" in blob
    assert "reason=no-accept" in blob
    assert "ACP_INJECT_CANCEL" not in blob
    assert ws.cancel_sessions == []
    assert elapsed >= 0.35, f"waited {elapsed:.2f}s; leftover harvest must not disconnect"


def test_pin_session_stays_through_leftover_harvest_until_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Stay on the websocket after leftover harvest until STATUS, then reason=status."""
    mod = _load(ACP_INJECT, "gcs_acp_inject_pin_harvest_then_status")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    (seat_dir / "acp.session").write_text("sess-pinned\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: None)
    flags = _capture_prompt_harvest(mod, monkeypatch)
    ws = FakeAcpWs(
        prompt_chunks=["abcd"],
        prompt_updates=[_queue_changed(), _tool_update("tc-stale", "leftover")],
        later_chunks=[f"\n{STATUS_LINE}\n"],
        later_delay=0.4,
    )
    _patch_connect(mod, ws, monkeypatch)

    started = time.monotonic()
    rc = asyncio.run(mod.inject("floor", "PROVE-MIND", timeout=2.0, pin_session=True))
    elapsed = time.monotonic() - started
    out = capsys.readouterr()
    blob = out.out + out.err
    assert rc == 0, blob
    assert elapsed >= 0.35, f"waited {elapsed:.2f}s; must not leave on leftover harvest"
    assert "ACP_INJECT_OK" in out.out
    _assert_handoff_reason(blob, "status")
    assert "ACP_INJECT_CANCEL" not in blob
    assert flags and flags[0]["tool_events"] > 0
    assert ws.cancel_sessions == []


def test_pin_session_keep_alive_chatter_does_not_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """LIVE hang-up: 56-char keep-alive scanning sentence is not a leave."""
    mod = _load(ACP_INJECT, "gcs_acp_inject_pin_keepalive")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    (seat_dir / "acp.session").write_text("sess-pinned\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: None)
    flags = _capture_prompt_harvest(mod, monkeypatch)
    ws = FakeAcpWs(
        prompt_chunks=[KEEP_ALIVE_LINE],
        prompt_updates=[_queue_changed(), _tool_update("tc-stale", "leftover")],
    )
    _patch_connect(mod, ws, monkeypatch)

    started = time.monotonic()
    rc = asyncio.run(mod.inject("floor", "ACP_PING STATUS/CONTINUE", timeout=0.45, pin_session=True))
    elapsed = time.monotonic() - started
    out = capsys.readouterr()
    blob = out.out + out.err
    assert rc == 1, blob
    assert flags and flags[0]["chars"] == 56
    assert flags[0]["prompt_accepted"] is False
    assert flags[0]["harvested_early"] is False
    assert flags[0]["work_tools"] == 0
    assert "ACP_INJECT_HANDOFF" not in blob
    assert "reason=substantial" not in blob
    assert "ACP_INJECT_OK" not in out.out
    assert "ACP_INJECT_TIMEOUT" in blob
    assert "reason=no-accept" in blob
    assert ws.cancel_sessions == []
    assert elapsed >= 0.35, f"waited {elapsed:.2f}s; keep-alive chatter must not disconnect"


def test_pin_session_list_dir_taskboard_does_not_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """LIVE hang-up: keep-alive + list_dir on .a2a-state/taskboard is not reason=work."""
    mod = _load(ACP_INJECT, "gcs_acp_inject_pin_listdir_board")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    (seat_dir / "acp.session").write_text("sess-pinned\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: None)
    flags = _capture_prompt_harvest(mod, monkeypatch)
    list_dir = {
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {
            "update": {
                "sessionUpdate": "tool_call",
                "toolCallId": "tc-listdir",
                "title": "list_dir",
                "kind": "read",
                "rawInput": {"path": "/workspace/.a2a-state/taskboard"},
            }
        },
    }
    ws = FakeAcpWs(
        prompt_chunks=[KEEP_ALIVE_LINE],
        prompt_updates=[_queue_changed(), list_dir],
    )
    _patch_connect(mod, ws, monkeypatch)

    started = time.monotonic()
    rc = asyncio.run(mod.inject("floor", "ACP_PING STATUS/CONTINUE", timeout=0.45, pin_session=True))
    elapsed = time.monotonic() - started
    out = capsys.readouterr()
    blob = out.out + out.err
    assert rc == 1, blob
    assert flags and flags[0]["work_tools"] == 0
    assert "ACP_INJECT_HANDOFF" not in blob
    assert "reason=work" not in blob
    assert "ACP_INJECT_OK" not in out.out
    assert "ACP_INJECT_TIMEOUT" in blob
    assert "reason=no-accept" in blob
    assert ws.cancel_sessions == []
    assert elapsed >= 0.35, f"waited {elapsed:.2f}s; list_dir taskboard must not disconnect"


def test_pin_session_shell_ls_launch_script_does_not_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """LIVE hang-up: keep-alive + Shell ls launch-cloud-extra-high.sh is not reason=work."""
    mod = _load(ACP_INJECT, "gcs_acp_inject_pin_shell_ls_launch")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    (seat_dir / "acp.session").write_text("sess-pinned\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: None)
    flags = _capture_prompt_harvest(mod, monkeypatch)
    ws = FakeAcpWs(
        prompt_chunks=[KEEP_ALIVE_PARK_LINE],
        prompt_updates=[
            _queue_changed(),
            _tool_update(
                "tc-ls-launch",
                "Shell",
                command="ls scripts/launch-cloud-extra-high.sh",
            ),
        ],
    )
    _patch_connect(mod, ws, monkeypatch)

    started = time.monotonic()
    rc = asyncio.run(mod.inject("floor", "ACP_PING STATUS/CONTINUE", timeout=0.45, pin_session=True))
    elapsed = time.monotonic() - started
    out = capsys.readouterr()
    blob = out.out + out.err
    assert rc == 1, blob
    assert flags and flags[0]["chars"] == 140
    assert flags[0]["work_tools"] == 0
    assert "ACP_INJECT_HANDOFF" not in blob
    assert "reason=work" not in blob
    assert "ACP_INJECT_OK" not in out.out
    assert "ACP_INJECT_TIMEOUT" in blob
    assert "reason=no-accept" in blob
    assert ws.cancel_sessions == []
    assert elapsed >= 0.35, f"waited {elapsed:.2f}s; Shell ls of launch script must not disconnect"


def test_pin_session_ticket_move_pal1_handoff_reason_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """ticket move PAL-1 done is still this-prompt work (argv matcher from #14)."""
    mod = _load(ACP_INJECT, "gcs_acp_inject_pin_ticket_move_pal1")
    _prep_seat(mod, tmp_path, monkeypatch)
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: None)
    flags = _capture_prompt_harvest(mod, monkeypatch)
    ws = FakeAcpWs(
        prompt_chunks=[KEEP_ALIVE_LINE],
        prompt_updates=[
            _queue_changed(),
            _tool_update(
                "tc-move",
                "bash",
                command="ticket move PAL-1 done",
            ),
        ],
    )
    _patch_connect(mod, ws, monkeypatch)

    rc = asyncio.run(mod.inject("floor", "ACP_PING STATUS/CONTINUE", timeout=2.0, pin_session=True))
    out = capsys.readouterr()
    blob = out.out + out.err
    assert rc == 0, blob
    assert "ACP_INJECT_OK" in out.out
    _assert_handoff_reason(blob, "work")
    assert flags and flags[0]["work_tools"] >= 1
    assert "ACP_INJECT_CANCEL" not in blob


def test_pin_session_work_tool_handoff_reason_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """this-prompt send.sh / taskboard / launch is leave reason=work."""
    mod = _load(ACP_INJECT, "gcs_acp_inject_pin_work_tool")
    _prep_seat(mod, tmp_path, monkeypatch)
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: None)
    flags = _capture_prompt_harvest(mod, monkeypatch)
    ws = FakeAcpWs(
        prompt_chunks=[KEEP_ALIVE_LINE],
        prompt_updates=[
            _queue_changed(),
            _tool_update(
                "tc-send",
                "bash",
                command="scripts/a2a/send.sh ops ticket-update",
            ),
        ],
        later_delay=0.0,
    )
    _patch_connect(mod, ws, monkeypatch)

    rc = asyncio.run(mod.inject("floor", "ACP_PING STATUS/CONTINUE", timeout=2.0, pin_session=True))
    out = capsys.readouterr()
    blob = out.out + out.err
    assert rc == 0, blob
    assert "ACP_INJECT_OK" in out.out
    _assert_handoff_reason(blob, "work")
    assert flags and flags[0]["work_tools"] >= 1
    assert "ACP_INJECT_CANCEL" not in blob


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
    """Accept is not a reason to hang up. Stay until STATUS."""
    mod = _load(ACP_INJECT, "gcs_acp_inject_stay_tool")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    (seat_dir / "acp.session").write_text("sess-pinned\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: None)
    flags = _capture_prompt_harvest(mod, monkeypatch)
    ws = FakeAcpWs(
        prompt_chunks=["Donald"],
        prompt_updates=[_tool_update("tc-1", "read")],
        later_chunks=[f"\n{STATUS_LINE}\n"],
        later_delay=0.55,
    )
    _patch_connect(mod, ws, monkeypatch)

    started = time.monotonic()
    rc = asyncio.run(mod.inject("floor", "PROVE-MIND", timeout=2.0, pin_session=True))
    elapsed = time.monotonic() - started
    out = capsys.readouterr()
    blob = out.out + out.err
    assert rc == 0, blob
    assert elapsed >= 0.5
    _assert_handoff_reason(blob, "status")
    assert "ACP_INJECT_OK" in out.out
    assert "ACP_INJECT_CANCEL" not in blob
    assert flags and flags[0]["harvested_early"] is True
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
    assert "ACP_INJECT_HANDOFF" not in blob
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


def test_pin_nack_and_dead_streak_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """LIVE 2026-08-21T05:46Z: 30s nack + streak=1 reminted before grok serve streamed."""
    monkeypatch.delenv("GCS_ACP_ACCEPT_DEADLINE", raising=False)
    monkeypatch.delenv("GCS_ACP_DEAD_STREAK", raising=False)
    mod = _load(ACP_INJECT, "gcs_acp_inject_nack_defaults")
    assert mod.PIN_NACK_SEC == 120.0
    assert mod.DEAD_STREAK_N == 3
    assert mod.PIN_NACK_SEC > 30.0
    env = (REPO / ".env.example").read_text(encoding="utf-8")
    assert "GCS_ACP_ACCEPT_DEADLINE=120" in env
    assert "GCS_ACP_DEAD_STREAK=3" in env
    a2a = A2A_DOC.read_text(encoding="utf-8")
    assert "default 120s" in a2a
    assert "GCS_ACP_DEAD_STREAK`, default 3)" in a2a or "default 3)" in a2a


def test_thirty_sec_silence_is_not_leave_or_session_dead_on_streak_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """LIVE 2026-08-21T05:46:28Z: 31s silence was TIMEOUT + SESSION_DEAD (streak=1).

    Time-scaled 100x: nack window 1.2s (120s), first STATUS at 0.35s (35s).
    Old 0.30s nack reminted before grok agent serve streamed. 30s of silence
    is not leave and is not SESSION_DEAD even when DEAD_STREAK_N=1.
    """
    mod = _load(ACP_INJECT, "gcs_acp_inject_pin_30s_silence")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    (seat_dir / "acp.session").write_text("sess-pinned\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: None)
    monkeypatch.setattr(mod, "PIN_NACK_SEC", 1.2)
    monkeypatch.setattr(mod, "DEAD_STREAK_N", 1)
    flags = _capture_prompt_harvest(mod, monkeypatch)
    ws = FakeAcpWs(
        prompt_chunks=[],
        later_chunks=[f"\n{STATUS_LINE}\n"],
        later_delay=0.35,
        new_session_id="sess-should-not",
    )
    _patch_connect(mod, ws, monkeypatch)

    started = time.monotonic()
    rc = asyncio.run(mod.inject("floor", "PROVE-MIND", timeout=1.8, pin_session=True))
    elapsed = time.monotonic() - started
    out = capsys.readouterr()
    blob = out.out + out.err
    assert rc == 0, blob
    assert elapsed >= 0.3, f"waited {elapsed:.2f}s; 30s-analog silence must not nack"
    assert elapsed < 1.2, f"waited {elapsed:.2f}s; STATUS at 0.35s should hand off"
    _assert_handoff_reason(blob, "status")
    assert "ACP_INJECT_OK" in out.out
    assert "ACP_INJECT_HANDOFF" in blob
    assert "ACP_INJECT_SESSION_DEAD" not in blob
    assert "ACP_INJECT_CANCEL" not in blob
    assert flags and flags[0]["prompt_accepted"] is True
    assert not any(m.get("method") == "session/new" for m in ws.sent)
    assert ws.cancel_sessions == []
    assert (seat_dir / "acp.session").read_text(encoding="utf-8").strip() == "sess-pinned"


def test_third_consecutive_no_start_nack_session_dead(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """One session/new only after 3 consecutive no-start nacks on the same id."""
    mod = _load(ACP_INJECT, "gcs_acp_inject_pin_dead_third")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    (seat_dir / "acp.session").write_text("sess-pinned\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: None)
    monkeypatch.setattr(mod, "DEAD_STREAK_N", 3)
    monkeypatch.setattr(mod, "PIN_NACK_SEC", 0.12)
    ws = FakeAcpWs(prompt_chunks=[], new_session_id="sess-reborn")
    _patch_connect(mod, ws, monkeypatch)
    streak_path = seat_dir / "acp.no_accept_streak"

    for i in range(2):
        rc = asyncio.run(mod.inject("floor", "PROVE-MIND", timeout=0.25, pin_session=True))
        out = capsys.readouterr()
        blob = out.out + out.err
        assert rc == 1, blob
        assert "reason=no-accept" in blob
        assert "ACP_INJECT_SESSION_DEAD" not in blob
        assert (seat_dir / "acp.session").read_text(encoding="utf-8").strip() == "sess-pinned"
        assert not any(m.get("method") == "session/new" for m in ws.sent)
        assert f"count={i + 1}" in streak_path.read_text(encoding="utf-8")
        ws.prompt_inflight = False

    rc3 = asyncio.run(mod.inject("floor", "PROVE-MIND", timeout=0.25, pin_session=True))
    out3 = capsys.readouterr()
    blob3 = out3.out + out3.err
    assert rc3 == 1, blob3
    assert "ACP_INJECT_SESSION_DEAD" in blob3
    assert "old=sess-pinned" in blob3
    assert "new=sess-reborn" in blob3
    assert (seat_dir / "acp.session").read_text(encoding="utf-8").strip() == "sess-reborn"
    assert any(m.get("method") == "session/new" for m in ws.sent)
    assert ws.cancel_sessions == []
    assert not streak_path.is_file()


def test_started_turn_timeout_does_not_remint_on_streak_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Keep-alive (accept signal) stays until inject timeout. Do not remint."""
    mod = _load(ACP_INJECT, "gcs_acp_inject_pin_started_no_remint")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    (seat_dir / "acp.session").write_text("sess-pinned\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: None)
    monkeypatch.setattr(mod, "DEAD_STREAK_N", 1)
    monkeypatch.setattr(mod, "PIN_NACK_SEC", 0.12)
    flags = _capture_prompt_harvest(mod, monkeypatch)
    ws = FakeAcpWs(
        prompt_chunks=[KEEP_ALIVE_LINE],
        new_session_id="sess-should-not",
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
    assert elapsed >= 0.35, f"waited {elapsed:.2f}s; started turn must use full timeout"
    assert "ACP_INJECT_TIMEOUT" in blob
    assert "reason=no-accept" in blob
    assert "ACP_INJECT_HANDOFF" not in blob
    assert "reason=work" not in blob
    assert "ACP_INJECT_SESSION_DEAD" not in blob
    assert flags and flags[0]["work_tools"] == 0
    assert flags[0]["chars"] == 56
    assert not any(m.get("method") == "session/new" for m in ws.sent)
    assert ws.cancel_sessions == []
    assert (seat_dir / "acp.session").read_text(encoding="utf-8").strip() == "sess-pinned"
    assert not (seat_dir / "acp.no_accept_streak").is_file()


def test_pin_session_started_stays_past_accept_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """First tool + Donald is a start: stay until STATUS, past the nack window."""
    mod = _load(ACP_INJECT, "gcs_acp_inject_pin_stay_past_nack")
    seat_dir = _prep_seat(mod, tmp_path, monkeypatch)
    (seat_dir / "acp.session").write_text("sess-pinned\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: None)
    monkeypatch.setattr(mod, "PIN_NACK_SEC", 0.15)
    flags = _capture_prompt_harvest(mod, monkeypatch)
    ws = FakeAcpWs(
        prompt_chunks=["Donald"],
        prompt_updates=[_tool_update("tc-1", "read")],
        later_chunks=[f"\n{STATUS_LINE}\n"],
        later_delay=0.4,
    )
    _patch_connect(mod, ws, monkeypatch)

    started = time.monotonic()
    rc = asyncio.run(mod.inject("floor", "PROVE-MIND", timeout=2.0, pin_session=True))
    elapsed = time.monotonic() - started
    out = capsys.readouterr()
    blob = out.out + out.err
    assert rc == 0, blob
    assert elapsed >= 0.35
    _assert_handoff_reason(blob, "status")
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
    assert "ACP_INJECT_HANDOFF" not in blob
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
    """When DEAD_STREAK_N=1, one no-start nack on the same id allows session/new."""
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
    _assert_handoff_reason(blob, "status")
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
    _assert_handoff_reason(blob, "status")
    assert flags and flags[0]["harvested_early"] is True
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
    assert "reason=work" in blob
    assert "queue/changed" in blob
    assert "no-accept" in blob or "dead session" in blob
    assert "silence" in blob or "not a start" in blob
    assert "wake-daemon" in blob or "seat-wake-loop" in blob
    assert "default 120" in a2a or "default 120s" in a2a
    assert "default 3" in a2a
    assert "default 30s" not in a2a
    assert "gcs_acp_dead_streak`, default 1)" not in a2a
    assert "studio.env" in a2a or "acp_inject.py" in a2a
