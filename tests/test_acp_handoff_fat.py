"""Factory acceptance: pin-session HANDOFF reasons.

GROW law (AGENTS.md / acp_inject.py): HANDOFF only after this-prompt STATUS
(`reason=status`) or a this-prompt work tool matched on invoked argv
(`reason=work`). Stay connected through keep-alive chatter, inspect tools,
payload blobs, silence, leftover tools, RESULT-only, and queue/changed.

These tests are the FAT. They fail if HANDOFF logs queue/tool/harvest/
substantial, if inspect/blob paths count as work, or if pin-session
session/cancel's a handed-off live turn.

Palemon Linear ids in work argv are Living Sky LIV-* (not Black Swan).
Does not vendor Hermes. Never Bot CloudAgent.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[1]
ACP_INJECT = REPO / "scripts" / "directors" / "acp_inject.py"
A2A_DOC = REPO / "docs" / "A2A.md"
AGENTS_DOC = REPO / "AGENTS.md"
HARNESS_PY = Path(__file__).resolve().parent / "test_acp_inject.py"

FORBIDDEN_HANDOFF_REASONS = frozenset(
    {"queue", "tool", "harvest", "substantial", "queue,tool,harvest"}
)
ALLOWED_HANDOFF_REASONS = frozenset({"status", "work"})

KEEP_ALIVE_LINE = "Keep-alive received. Scanning A2A inboxes, fleet ledgers"
KEEP_ALIVE_PARK_LINE = (
    "Keep-alive received. I'll check PARK, ownership, and current fleet/board "
    "state before deciding whether to launch or stay with existing work."
)
STATUS_LINE = "STATUS quoting token tick-1. Working."
RESULT_LINE = "RESULT bc-id=none pr=none a2a=task-1 notes=park-ok"
PINNED = "sess-pinned"


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_HARNESS: ModuleType | None = None


def _harness() -> ModuleType:
    global _HARNESS
    if _HARNESS is None:
        spec = importlib.util.spec_from_file_location(
            "gcs_acp_handoff_fat_harness", HARNESS_PY
        )
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _HARNESS = mod
    return _HARNESS


def _exec_tool(
    tool_call_id: str,
    title: str,
    *,
    command: str | None = None,
    argv: list[str] | None = None,
    extra: dict[str, Any] | None = None,
    kind: str = "execute",
    session_update: str = "tool_call",
) -> dict[str, Any]:
    """this-prompt tool_call with invoked argv fields only in rawInput."""
    raw: dict[str, Any] = {}
    if command is not None:
        raw["command"] = command
    if argv is not None:
        raw["argv"] = argv
    if extra:
        raw.update(extra)
    update: dict[str, Any] = {
        "sessionUpdate": session_update,
        "toolCallId": tool_call_id,
        "title": title,
    }
    if kind:
        update["kind"] = kind
    if raw:
        update["rawInput"] = raw
    return {
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {"update": update},
    }


def _inspect_list_dir() -> dict[str, Any]:
    return {
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


def _assert_no_forbidden_handoff(blob: str) -> None:
    low = blob.lower()
    for reason in FORBIDDEN_HANDOFF_REASONS:
        assert f"reason={reason}" not in low, blob
        assert reason not in "".join(
            ln for ln in blob.splitlines() if "ACP_INJECT_HANDOFF" in ln
        )


def _run_pin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *,
    load_name: str,
    chunks: list[str],
    updates: list[dict[str, Any]] | None = None,
    timeout: float = 0.45,
    later_chunks: list[str] | None = None,
    later_updates: list[dict[str, Any]] | None = None,
    later_delay: float = 0.0,
) -> tuple[int, str, list[dict[str, Any]], Any, Path, float]:
    h = _harness()
    mod = _load(ACP_INJECT, load_name)
    seat_dir = h._prep_seat(mod, tmp_path, monkeypatch)
    (seat_dir / "acp.session").write_text(PINNED + "\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: None)
    flags = h._capture_prompt_harvest(mod, monkeypatch)
    ws = h.FakeAcpWs(
        prompt_chunks=chunks,
        prompt_updates=list(updates or []),
        later_chunks=list(later_chunks or []),
        later_updates=list(later_updates or []),
        later_delay=later_delay,
        new_session_id="sess-new-must-not-use",
    )
    h._patch_connect(mod, ws, monkeypatch)
    started = time.monotonic()
    rc = asyncio.run(
        mod.inject("floor", "ACP_PING STATUS/CONTINUE", timeout=timeout, pin_session=True)
    )
    elapsed = time.monotonic() - started
    out = capsys.readouterr()
    blob = out.out + out.err
    return rc, blob, flags, ws, seat_dir, elapsed


def test_fat_handoff_reasons_constant_is_status_and_work_only() -> None:
    """Production pin: the only legal ACP_INJECT_HANDOFF reasons."""
    mod = _load(ACP_INJECT, "gcs_acp_handoff_fat_reasons_const")
    assert mod.HANDOFF_REASONS == ALLOWED_HANDOFF_REASONS
    assert FORBIDDEN_HANDOFF_REASONS.isdisjoint(mod.HANDOFF_REASONS)
    src = ACP_INJECT.read_text(encoding="utf-8")
    assert "HANDOFF_REASONS" in src
    assert "reason={reason}" in src
    assert "reason=status" in src
    assert "reason=work" in src
    low = src.lower()
    assert "never queue, tool, harvest, substantial" in low
    assert "substantial" in src


def test_fat_handoff_reason_classifier_status_vs_work() -> None:
    """STATUS wins over work_tools. Keep-alive / leftover / RESULT are None."""
    mod = _load(ACP_INJECT, "gcs_acp_handoff_fat_classifier")
    leftover = "abcd"
    assert mod.pin_session_handoff_reason(STATUS_LINE) == "status"
    assert mod.pin_session_handoff_reason(STATUS_LINE, tool_events=9) == "status"
    assert mod.pin_session_handoff_reason(STATUS_LINE, work_tools=1) == "status"
    assert (
        mod.pin_session_handoff_reason(KEEP_ALIVE_LINE, work_tools=1) == "work"
    )
    assert mod.pin_session_handoff_reason(KEEP_ALIVE_LINE) is None
    assert mod.pin_session_handoff_reason(KEEP_ALIVE_PARK_LINE, tool_events=2) is None
    assert mod.pin_session_handoff_reason(leftover, tool_events=3) is None
    assert mod.pin_session_handoff_reason(RESULT_LINE, work_tools=0) is None
    assert mod.pin_session_handoff_reason("", tool_events=4) is None
    assert mod.pin_session_handoff_reason("x" * 40, tool_events=2) is None
    for reason in (
        mod.pin_session_handoff_reason(STATUS_LINE),
        mod.pin_session_handoff_reason(KEEP_ALIVE_LINE, work_tools=1),
        mod.pin_session_handoff_reason(leftover, tool_events=3),
    ):
        if reason is None:
            continue
        assert reason in ALLOWED_HANDOFF_REASONS
        assert reason not in FORBIDDEN_HANDOFF_REASONS


@pytest.mark.parametrize(
    ("command", "expect_work"),
    [
        ("ticket move LIV-1 done", True),
        ("ticket create --title floor-follow-up", True),
        ("tb move LIV-1 in_progress", True),
        ("tb create follow-up", True),
        ("scripts/a2a/send.sh ops ping", True),
        ("scripts/launch-cloud-extra-high.sh --name floor-iac", True),
        ("ls scripts/launch-cloud-extra-high.sh", False),
        ("cat scripts/a2a/send.sh", False),
        ("rg launch-cloud-extra-high scripts/", False),
        ("ls", False),
    ],
)
def test_fat_work_tool_matches_invoked_argv_not_path_blob(
    command: str, expect_work: bool
) -> None:
    """Work is the invoked argv. Shell ls/cat/rg of a work-script path is not."""
    mod = _load(ACP_INJECT, "gcs_acp_handoff_fat_argv_match")
    update = {
        "sessionUpdate": "tool_call",
        "title": "Shell",
        "kind": "execute",
        "rawInput": {"command": command},
    }
    assert mod.is_this_prompt_work_tool(update) is expect_work


def test_fat_work_tool_argv_list_liv_ticket_is_work() -> None:
    """Living Sky ticket move as argv list is this-prompt work."""
    mod = _load(ACP_INJECT, "gcs_acp_handoff_fat_argv_list")
    argv_move = {
        "sessionUpdate": "tool_call",
        "title": "Shell",
        "kind": "execute",
        "rawInput": {"argv": ["ticket", "move", "LIV-1", "done"]},
    }
    blob_only = {
        "sessionUpdate": "tool_call",
        "title": "Shell",
        "kind": "execute",
        "rawInput": {
            "command": "ls scripts/",
            "description": "help: launch-cloud-extra-high.sh and send.sh",
            "cwd": "/workspace/.a2a-state/taskboard",
        },
    }
    leftover_update = {
        "sessionUpdate": "tool_call_update",
        "title": "scripts/a2a/send.sh ops ping",
        "status": "completed",
        "rawInput": {"command": "scripts/a2a/send.sh ops ping"},
    }
    a2a_title = {
        "sessionUpdate": "tool_call",
        "title": "a2a message send",
        "rawInput": {"seat": "ops", "text": "ping"},
    }
    assert mod.is_this_prompt_work_tool(argv_move) is True
    assert mod.is_this_prompt_work_tool(blob_only) is False
    assert mod.is_this_prompt_work_tool(leftover_update) is False
    assert mod.is_this_prompt_work_tool(a2a_title) is True


def test_fat_pin_session_status_handoff_reason_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """this-prompt STATUS after keep-alive chatter is leave reason=status."""
    h = _harness()
    rc, blob, flags, ws, seat_dir, elapsed = _run_pin(
        tmp_path,
        monkeypatch,
        capsys,
        load_name="gcs_acp_handoff_fat_status",
        chunks=[KEEP_ALIVE_LINE],
        updates=[h._queue_changed(), h._tool_update("tc-stale", "leftover")],
        timeout=2.0,
        later_chunks=[f"\n{STATUS_LINE}\n"],
        later_delay=0.35,
    )
    assert rc == 0, blob
    assert elapsed >= 0.3
    assert "ACP_INJECT_OK" in blob
    h._assert_handoff_reason(blob, "status")
    _assert_no_forbidden_handoff(blob)
    assert "reason=work" not in "".join(
        ln for ln in blob.splitlines() if "ACP_INJECT_HANDOFF" in ln
    )
    assert "ACP_INJECT_CANCEL" not in blob
    assert ws.cancel_sessions == []
    assert (seat_dir / "acp.session").read_text(encoding="utf-8").strip() == PINNED
    assert flags and flags[0]["work_tools"] == 0


@pytest.mark.parametrize(
    ("label", "command", "argv"),
    [
        ("ticket-move-liv", "ticket move LIV-1 done", None),
        ("tb-move-liv", "tb move LIV-1 in_progress", None),
        ("send-sh", "scripts/a2a/send.sh ops ticket-update", None),
        ("launch-cloud", "scripts/launch-cloud-extra-high.sh --name floor-iac", None),
        ("ticket-argv-list", None, ["ticket", "move", "LIV-1", "done"]),
    ],
)
def test_fat_pin_session_work_tool_handoff_reason_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    label: str,
    command: str | None,
    argv: list[str] | None,
) -> None:
    """this-prompt work on invoked argv is leave reason=work. Pin stays."""
    h = _harness()
    rc, blob, flags, ws, seat_dir, _elapsed = _run_pin(
        tmp_path,
        monkeypatch,
        capsys,
        load_name=f"gcs_acp_handoff_fat_work_{label}",
        chunks=[KEEP_ALIVE_LINE],
        updates=[
            h._queue_changed(),
            _exec_tool(f"tc-{label}", "Shell", command=command, argv=argv),
        ],
        timeout=2.0,
    )
    assert rc == 0, blob
    assert "ACP_INJECT_OK" in blob
    h._assert_handoff_reason(blob, "work")
    _assert_no_forbidden_handoff(blob)
    assert "reason=status" not in "".join(
        ln for ln in blob.splitlines() if "ACP_INJECT_HANDOFF" in ln
    )
    assert flags and flags[0]["work_tools"] >= 1
    assert "ACP_INJECT_CANCEL" not in blob
    assert ws.cancel_sessions == []
    assert (seat_dir / "acp.session").read_text(encoding="utf-8").strip() == PINNED


def test_fat_status_wins_over_this_prompt_work_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """When STATUS and a work tool both appear, HANDOFF reason is status."""
    h = _harness()
    rc, blob, flags, ws, seat_dir, _elapsed = _run_pin(
        tmp_path,
        monkeypatch,
        capsys,
        load_name="gcs_acp_handoff_fat_status_wins",
        chunks=[KEEP_ALIVE_LINE, f"\n{STATUS_LINE}\n"],
        updates=[
            _exec_tool("tc-move", "bash", command="ticket move LIV-1 done"),
        ],
        timeout=2.0,
    )
    assert rc == 0, blob
    h._assert_handoff_reason(blob, "status")
    _assert_no_forbidden_handoff(blob)
    assert flags and flags[0]["work_tools"] >= 1
    assert ws.cancel_sessions == []
    assert (seat_dir / "acp.session").read_text(encoding="utf-8").strip() == PINNED


@pytest.mark.parametrize(
    ("label", "chunks", "updates"),
    [
        ("keep-alive-56", [KEEP_ALIVE_LINE], None),
        ("keep-alive-park-140", [KEEP_ALIVE_PARK_LINE], None),
        ("silence", [], None),
        ("result-only", [f"{RESULT_LINE}\n"], None),
        ("leftover-chars4", ["abcd"], None),
    ],
)
def test_fat_stay_connected_text_is_not_handoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    label: str,
    chunks: list[str],
    updates: list[dict[str, Any]] | None,
) -> None:
    """Keep-alive chatter, silence, leftover short text, RESULT-only: no HANDOFF."""
    h = _harness()
    extra = list(updates or [])
    if label == "leftover-chars4":
        extra = [h._queue_changed(), h._tool_update("tc-stale", "leftover")]
    elif label in {"keep-alive-56", "keep-alive-park-140"}:
        extra = [h._queue_changed(), h._tool_update("tc-stale", "leftover")]
    rc, blob, flags, ws, seat_dir, elapsed = _run_pin(
        tmp_path,
        monkeypatch,
        capsys,
        load_name=f"gcs_acp_handoff_fat_stay_{label}",
        chunks=chunks,
        updates=extra,
        timeout=0.45,
    )
    assert rc == 1, blob
    assert "ACP_INJECT_HANDOFF" not in blob
    assert "ACP_INJECT_OK" not in blob
    assert "ACP_INJECT_TIMEOUT" in blob
    _assert_no_forbidden_handoff(blob)
    assert "ACP_INJECT_CANCEL" not in blob
    assert ws.cancel_sessions == []
    assert (seat_dir / "acp.session").read_text(encoding="utf-8").strip() == PINNED
    assert elapsed >= 0.3
    if flags:
        assert flags[0]["prompt_accepted"] is False
        assert flags[0]["harvested_early"] is False


@pytest.mark.parametrize(
    "label",
    ["listdir", "ls-launch", "blob-desc", "leftover-send-update", "queue-changed"],
)
def test_fat_stay_connected_inspect_and_blob_are_not_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    label: str,
) -> None:
    """list_dir taskboard, Shell ls of launch script, description blob: not work."""
    h = _harness()
    updates_by_label: dict[str, list[dict[str, Any]]] = {
        "listdir": [_inspect_list_dir()],
        "ls-launch": [
            _exec_tool(
                "tc-ls",
                "Shell",
                command="ls scripts/launch-cloud-extra-high.sh",
            )
        ],
        "blob-desc": [
            _exec_tool(
                "tc-blob",
                "Shell",
                command="ls scripts/",
                extra={
                    "description": "help: launch-cloud-extra-high.sh and send.sh",
                    "cwd": "/workspace/.a2a-state/taskboard",
                },
            )
        ],
        "leftover-send-update": [
            _exec_tool(
                "tc-stale-send",
                "scripts/a2a/send.sh ops ping",
                command="scripts/a2a/send.sh ops ping",
                session_update="tool_call_update",
                kind="",
            )
        ],
        "queue-changed": [h._queue_changed()],
    }
    rc, blob, flags, ws, seat_dir, elapsed = _run_pin(
        tmp_path,
        monkeypatch,
        capsys,
        load_name=f"gcs_acp_handoff_fat_inspect_{label}",
        chunks=[KEEP_ALIVE_LINE],
        updates=updates_by_label[label],
        timeout=0.45,
    )
    assert rc == 1, blob
    assert "ACP_INJECT_HANDOFF" not in blob, blob
    assert "reason=work" not in blob, blob
    assert "ACP_INJECT_TIMEOUT" in blob
    _assert_no_forbidden_handoff(blob)
    assert ws.cancel_sessions == []
    assert elapsed >= 0.3
    assert (seat_dir / "acp.session").read_text(encoding="utf-8").strip() == PINNED
    if flags:
        assert flags[0]["work_tools"] == 0, flags[0]


def test_fat_docs_and_law_pin_handoff_reasons() -> None:
    """Law text names both reasons and the stay-connected cases."""
    a2a = A2A_DOC.read_text(encoding="utf-8")
    agents = AGENTS_DOC.read_text(encoding="utf-8")
    src = ACP_INJECT.read_text(encoding="utf-8")
    blob = a2a + "\n" + agents + "\n" + src
    assert "reason=status" in blob
    assert "reason=work" in blob
    assert "keep-alive" in blob.lower() or "Keep-alive" in blob
    assert "queue/changed" in blob
    assert "session/cancel" in blob.lower() or "do not `session/cancel`" in blob
    assert "invoked argv" in blob or "invoked command/argv" in src
    assert "Hermes" not in src
    assert "Bot CloudAgent" not in src
    assert "vendor/hermes" not in src
    vendor = REPO / "vendor" / "hermes"
    assert not vendor.exists()
