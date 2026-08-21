"""Stateful Grok Build mind harness: mail is a turn, plugins, no ACP inject.

Fake model runner only — no live grok CLI, no network, no secrets.
"""
from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[1]
MIND_PY = REPO / "scripts" / "directors" / "mind.py"
MIND_LOOP = REPO / "scripts" / "directors" / "seat-mind-loop.sh"
BUS_SH = REPO / "scripts" / "a2a" / "start-studio-bus.sh"
DISPATCH_PY = REPO / "scripts" / "a2a" / "dispatch.py"
LIB_PY = REPO / "scripts" / "a2a" / "lib.py"
MIND_DOC = REPO / "docs" / "studio" / "MIND.md"
AGENTS_DOC = REPO / "AGENTS.md"
A2A_DOC = REPO / "docs" / "A2A.md"
ARCH_DOC = REPO / "docs" / "ARCHITECTURE.md"


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _write_exec(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def _append_inbox(state: Path, seat: str, task_id: str, text: str) -> Path:
    seat_dir = state / seat
    seat_dir.mkdir(parents=True, exist_ok=True)
    inbox = seat_dir / "inbox.jsonl"
    rec = {
        "taskId": task_id,
        "contextId": "ctx-1",
        "parts": [{"kind": "text", "text": text}],
        "metadata": {"from": "ops"},
    }
    with inbox.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    return inbox


def _transcript_rows(state: Path, seat: str) -> list[dict]:
    path = state / seat / "mind" / "transcript.jsonl"
    if not path.is_file():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _offset(state: Path, seat: str) -> int:
    path = state / seat / "mind" / "offset"
    if not path.is_file():
        return 0
    return int(path.read_text(encoding="utf-8").strip() or "0")


def _prep_mind(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    unique: str,
    runner,
) -> tuple[ModuleType, Path]:
    mind = _load(MIND_PY, f"gcs_mind_{unique}")
    state = tmp_path / "a2a-state"
    state.mkdir(parents=True, exist_ok=True)
    db = state / "taskboard" / "taskboard.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_text("", encoding="utf-8")
    monkeypatch.setattr(mind, "STATE_DIR", state)
    monkeypatch.setattr(mind, "ROOT", REPO)
    monkeypatch.setenv("GCS_A2A_STATE", str(state))
    monkeypatch.setenv("GCS_ROOT", str(REPO))
    monkeypatch.setenv("GCS_TASKBOARD_DB", str(db))
    monkeypatch.setattr(mind, "DEFAULT_RUNNER", runner)
    return mind, state


def test_mind_scripts_and_docs_exist() -> None:
    assert MIND_PY.is_file()
    assert MIND_LOOP.is_file()
    assert MIND_DOC.is_file()
    src = MIND_PY.read_text(encoding="utf-8")
    loop = MIND_LOOP.read_text(encoding="utf-8")
    doc = MIND_DOC.read_text(encoding="utf-8")
    for blob in (src, loop):
        assert "acp_inject" not in blob
        assert "session/prompt" not in blob
        assert "session/new" not in blob
        assert "pin-session" not in blob
        assert "pin_session" not in blob
        assert "HANDOFF" not in blob
        assert "--resume" not in blob
        assert "GCS_WAKE_ACP_TIMEOUT" not in blob
        assert "no-accept" not in blob
        assert "/home/box" not in blob
        assert "palemon" not in blob.lower()
    assert "Bot-equivalent" in doc or "bot-equivalent" in doc
    assert "leftover host os" in doc.lower() or "acp inject is leftover" in doc.lower()
    assert "GCS_MIND_SEATS" in doc
    assert "session/prompt" in doc
    assert "/home/box" not in doc
    assert "palemon" not in doc.lower()


def test_fake_runner_inbox_grows_transcript_and_offset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[list[dict]] = []

    def fake(messages: list[dict], plugins: dict, **_kwargs: object) -> dict:
        seen.append(list(messages))
        last = messages[-1].get("content") if messages else ""
        return {"text": f"ack:{last}"}

    mind, state = _prep_mind(tmp_path, monkeypatch, unique="inbox", runner=fake)
    _append_inbox(state, "floor", "task-mind-1", "ping from ops")
    first = mind.process_once("floor")
    assert first["consumed"] == 1
    assert _offset(state, "floor") > 0
    rows = _transcript_rows(state, "floor")
    assert any(r.get("role") == "user" and "ping from ops" in str(r.get("content", "")) for r in rows)
    assert any(r.get("role") == "assistant" and "ack:" in str(r.get("content", "")) for r in rows)
    assert seen and seen[0]
    assert "ticket" in mind.PLUGINS
    assert "a2a_send" in mind.PLUGINS
    assert "cloud_launch" in mind.PLUGINS

    _append_inbox(state, "floor", "task-mind-2", "second ping")
    second = mind.process_once("floor")
    assert second["consumed"] == 1
    assert _offset(state, "floor") > first.get("offset", 0) or _offset(state, "floor") > 0
    rows2 = _transcript_rows(state, "floor")
    assert len(rows2) > len(rows)
    empty = mind.process_once("floor")
    assert empty["consumed"] == 0


def test_ticket_plugin_passes_db_to_state_dir_taskboard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "taskboard.argv"
    binary = _write_exec(
        tmp_path / "host-bin" / "taskboard",
        "#!/bin/sh\n"
        f'echo "$@" >> "{log}"\n'
        'echo TICKET_OK "$@"\n',
    )
    db = tmp_path / "a2a-state" / "taskboard" / "taskboard.db"

    def fake(_messages: list[dict], _plugins: dict, **_kwargs: object) -> dict:
        return {
            "text": "listing tickets",
            "tool_calls": [{"name": "ticket", "arguments": {"argv": ["list"]}}],
        }

    monkeypatch.setenv("TASKBOARD_BIN", str(binary))
    mind, state = _prep_mind(tmp_path, monkeypatch, unique="ticket", runner=fake)
    monkeypatch.setenv("GCS_TASKBOARD_DB", str(db))
    _append_inbox(state, "floor", "task-ticket-1", "move work")
    result = mind.process_once("floor")
    assert result["consumed"] == 1
    argv = log.read_text(encoding="utf-8") if log.is_file() else ""
    assert "--db" in argv, argv
    assert str(db) in argv, argv
    assert "ticket list" in argv or argv.strip().endswith("ticket list") or "ticket" in argv
    tool_rows = [r for r in _transcript_rows(state, "floor") if r.get("role") == "tool"]
    assert tool_rows
    assert "TICKET_OK" in str(tool_rows[-1].get("content", ""))


def test_empty_model_text_completes_turn_when_runner_returns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake(_messages: list[dict], _plugins: dict, **_kwargs: object) -> dict:
        return {"text": ""}

    mind, state = _prep_mind(tmp_path, monkeypatch, unique="empty", runner=fake)
    _append_inbox(
        state,
        "floor",
        "task-scan-1",
        "Keep-alive received. Scanning A2A inboxes, fleet ledgers",
    )
    result = mind.process_once("floor")
    assert result["consumed"] == 1
    assert _offset(state, "floor") > 0
    rows = _transcript_rows(state, "floor")
    assert any(r.get("role") == "user" for r in rows)
    assert any(r.get("role") == "assistant" for r in rows)


def test_missing_ticket_binary_returns_error_string_not_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake(_messages: list[dict], _plugins: dict, **_kwargs: object) -> dict:
        return {
            "text": "",
            "tool_calls": [{"name": "ticket", "arguments": {"argv": ["list"]}}],
        }

    monkeypatch.delenv("TASKBOARD_BIN", raising=False)
    mind, state = _prep_mind(tmp_path, monkeypatch, unique="missingbin", runner=fake)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    _append_inbox(state, "floor", "task-miss-1", "list tickets")
    result = mind.process_once("floor")
    assert result["consumed"] == 1
    tool_rows = [r for r in _transcript_rows(state, "floor") if r.get("role") == "tool"]
    assert tool_rows
    blob = str(tool_rows[-1].get("content", "")).lower()
    assert "missing" in blob or "plugin_err" in blob or "error" in blob


def test_runner_exception_does_not_advance_offset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(_messages: list[dict], _plugins: dict, **_kwargs: object) -> dict:
        raise RuntimeError("runner exploded")

    mind, state = _prep_mind(tmp_path, monkeypatch, unique="boom", runner=boom)
    _append_inbox(state, "floor", "task-boom-1", "do work")
    result = mind.process_once("floor")
    assert result["consumed"] == 0
    assert _offset(state, "floor") == 0
    assert result.get("reason") == "runner-fail"


def test_skip_seats_are_not_mind_seats(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GCS_MIND_SEATS", "floor,ops,donald,orchestrator")
    monkeypatch.delenv("GCS_SKIP_SEATS", raising=False)
    proc = subprocess.run(
        ["python3", str(LIB_PY), "mind-seats"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, proc.stderr
    seats = {s.strip() for s in proc.stdout.splitlines() if s.strip()}
    assert "donald" not in seats
    assert "orchestrator" not in seats
    assert "floor" in seats
    assert "ops" in seats


def test_mind_seats_default_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    env = {k: v for k, v in os.environ.items() if k != "GCS_MIND_SEATS"}
    proc = subprocess.run(
        ["python3", str(LIB_PY), "mind-seats"],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == ""


def test_process_once_refuses_skip_seat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake(_messages: list[dict], _plugins: dict, **_kwargs: object) -> dict:
        return {"text": "should not run"}

    mind, state = _prep_mind(tmp_path, monkeypatch, unique="skip", runner=fake)
    _append_inbox(state, "donald", "task-don-1", "hello")
    result = mind.process_once("donald")
    assert result["consumed"] == 0
    assert "skip" in str(result.get("reason", "")).lower()
    assert _offset(state, "donald") == 0
    assert _transcript_rows(state, "donald") == []


def test_grok_cli_runner_flags_no_live_grok() -> None:
    mind = _load(MIND_PY, "gcs_mind_argv")
    argv = mind.grok_cli_argv("hello seat", cwd=REPO)
    joined = " ".join(argv)
    assert "--permission-mode" in argv
    assert "bypassPermissions" in argv
    assert "--always-approve" in argv
    assert "--trust" in argv
    assert "--cwd" in argv
    assert str(REPO) in argv
    assert "-p" in argv
    assert "--resume" not in argv
    assert "session/prompt" not in joined
    assert "/home/box" not in joined


def test_a2a_send_and_cloud_launch_plugins_missing_binaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mind = _load(MIND_PY, "gcs_mind_plugmiss")
    monkeypatch.setattr(mind, "ROOT", tmp_path)
    monkeypatch.setattr(mind, "STATE_DIR", tmp_path / "a2a-state")
    send_out = mind.call_plugin("a2a_send", {"seat": "ops", "text": "hi"})
    launch_out = mind.call_plugin("cloud_launch", {"prompt": "do a thing"})
    assert "missing" in send_out.lower() or "plugin_err" in send_out.lower()
    assert "missing" in launch_out.lower() or "plugin_err" in launch_out.lower()


def test_a2a_send_plugin_invokes_send_sh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "send.argv"
    _write_exec(
        tmp_path / "scripts" / "a2a" / "send.sh",
        "#!/bin/sh\n"
        f'echo "$@" >> "{log}"\n'
        'echo A2A_SEND_OK seat="$1"\n',
    )
    mind = _load(MIND_PY, "gcs_mind_send")
    monkeypatch.setattr(mind, "ROOT", tmp_path)
    monkeypatch.setattr(mind, "STATE_DIR", tmp_path / "a2a-state")
    out = mind.call_plugin("a2a_send", {"seat": "ops", "text": "hello from floor"})
    assert "A2A_SEND_OK" in out
    argv = log.read_text(encoding="utf-8")
    assert "ops" in argv
    assert "hello from floor" in argv


def test_cloud_launch_plugin_redacts_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = "test-cursor-api-key-should-not-leak"
    _write_exec(
        tmp_path / "scripts" / "launch-cloud-extra-high.sh",
        "#!/bin/sh\n"
        f'echo CURSOR_API_KEY={key}\n'
        'echo CLOUD_LAUNCH_OK id=bc-fake\n',
    )
    mind = _load(MIND_PY, "gcs_mind_launch")
    monkeypatch.setattr(mind, "ROOT", tmp_path)
    monkeypatch.setattr(mind, "STATE_DIR", tmp_path / "a2a-state")
    out = mind.call_plugin("cloud_launch", {"prompt": "implement X", "name": "floor-x"})
    assert key not in out
    assert "CLOUD_LAUNCH_OK" in out or "bc-fake" in out or "CURSOR_API_KEY=" in out


def test_bus_starts_mind_loop_without_killing_serve() -> None:
    bus = BUS_SH.read_text(encoding="utf-8")
    loop = MIND_LOOP.read_text(encoding="utf-8")
    assert "GCS_MIND_SEATS" in bus
    assert "seat-mind-loop.sh" in bus
    assert "mind/pid" in bus or "mind/pid" in loop
    assert "stop-seat-daemon" not in bus.split("start_mind")[1].split("stop_mind")[0] if "start_mind" in bus else True
    assert "ensure_seat_serve" not in loop
    assert "wake-daemon.py" not in loop
    assert "acp_inject" not in loop
    assert "GCS_MIND_PLUS_ACP_WAKE" in bus or "instead of" in bus.lower() or "in addition" in bus.lower()
    agents = AGENTS_DOC.read_text(encoding="utf-8")
    a2a = A2A_DOC.read_text(encoding="utf-8")
    arch = ARCH_DOC.read_text(encoding="utf-8")
    blob = agents + "\n" + a2a + "\n" + arch
    assert "GCS_MIND_SEATS" in blob
    assert "mind.py" in blob or "seat-mind-loop" in blob
    assert "Agent Kanban" in bus or "Agent Kanban was removed" in a2a


def test_dispatch_skips_live_mind_pid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dispatch = _load(DISPATCH_PY, "gcs_dispatch_mind_skip")
    state = tmp_path / "a2a-state"
    inject_stamp = tmp_path / "inject.extra"
    fake_inject = _write_exec(
        tmp_path / "fake_acp_inject.py",
        "#!/usr/bin/env python3\nimport sys\nfrom pathlib import Path\n"
        f"Path({str(inject_stamp)!r}).write_text(sys.argv[-1], encoding='utf-8')\n",
    )
    monkeypatch.setattr(dispatch, "STATE_DIR", state)
    monkeypatch.setattr(dispatch, "ACP_INJECT", fake_inject)
    monkeypatch.setattr(dispatch, "GROW_SEATS", frozenset())
    monkeypatch.setattr(dispatch, "_daemon_healthy", lambda seat: True)
    monkeypatch.setattr(dispatch, "_ensure_daemon", lambda seat: True)
    monkeypatch.setattr(dispatch, "_CHILDREN", {})
    qa = state / "qa-a"
    (qa / "mind").mkdir(parents=True)
    (qa / "mind" / "pid").write_text(str(os.getpid()) + "\n", encoding="utf-8")
    _append_inbox(state, "qa-a", "task-mind-skip", "LAUNCH ONLY do not inject")
    started = dispatch._process_seat("qa-a", dry_run=False)
    assert started == 0
    assert not inject_stamp.is_file()
    assert not (qa / "dispatch.offset").is_file()
    src = DISPATCH_PY.read_text(encoding="utf-8")
    assert "mind-owns-inbox" in src or "mind/pid" in src


def test_plugin_schemas_are_json_objects() -> None:
    mind = _load(MIND_PY, "gcs_mind_schema")
    for name in ("ticket", "a2a_send", "cloud_launch"):
        plugin = mind.PLUGINS[name]
        schema = plugin["schema"] if isinstance(plugin, dict) else plugin.schema
        assert isinstance(schema, dict)
        assert schema.get("type") == "object"
        fn = plugin["call"] if isinstance(plugin, dict) else plugin.call
        assert callable(fn)
