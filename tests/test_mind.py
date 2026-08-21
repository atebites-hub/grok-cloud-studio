"""Stateful Grok Build mind: mailbox + pin + stay-up. Fake grok only.

No live grok CLI, no network, no secrets. Default runner is a fake `grok`
binary that records argv and prints a json blob.
"""
from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
import uuid
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[1]
MIND_PY = REPO / "scripts" / "directors" / "mind.py"
MIND_LOOP = REPO / "scripts" / "directors" / "seat-mind-loop.sh"
SEAT_COMMON = REPO / "scripts" / "directors" / "seat-daemon-common.sh"
BUS_SH = REPO / "scripts" / "a2a" / "start-studio-bus.sh"
DISPATCH_PY = REPO / "scripts" / "a2a" / "dispatch.py"
LIB_PY = REPO / "scripts" / "a2a" / "lib.py"
MIND_DOC = REPO / "docs" / "studio" / "MIND.md"
AGENTS_DOC = REPO / "AGENTS.md"
A2A_DOC = REPO / "docs" / "A2A.md"
ARCH_DOC = REPO / "docs" / "ARCHITECTURE.md"
PLUGIN_DIR = REPO / "plugins" / "studio-mind"


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


def _session_id(state: Path, seat: str) -> str:
    path = state / seat / "mind" / "session"
    assert path.is_file(), "pinned session UUID missing"
    return path.read_text(encoding="utf-8").strip()


def _argv_log(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


_BANNED_GROK_FLAGS = ("-p", "--single", "--trust", "--agent-profile", "--plugin-dir")
_LAW_SID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _law_argv(
    sid: str,
    mail: Path,
    *,
    minted: bool,
    grok: str = "grok",
) -> list[str]:
    pin = ["--resume", sid] if minted else ["--session-id", sid]
    return [
        grok,
        *pin,
        "--prompt-file",
        str(mail),
        "--verbatim",
        "--output-format",
        "json",
        "--always-approve",
        "--permission-mode",
        "bypassPermissions",
        "--max-turns",
        "40",
    ]


def _assert_no_banned_flags(argv: list[str]) -> None:
    for flag in _BANNED_GROK_FLAGS:
        assert flag not in argv, argv


def _write_fake_grok(
    tmp_path: Path,
    log: Path,
    *,
    rc: int = 0,
    stdout: str | None = None,
    stderr: str = "",
    session_in_use_on_session_id: bool = False,
) -> Path:
    blob = stdout if stdout is not None else json.dumps({"ok": True, "role": "assistant"})
    script = (
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        f"log = Path({str(log)!r})\n"
        "rows = json.loads(log.read_text()) if log.is_file() else []\n"
        "rows.append({\n"
        "    'argv': sys.argv[1:],\n"
        "    'cwd': os.getcwd(),\n"
        "    'GROK_HOME': os.environ.get('GROK_HOME', ''),\n"
        "    'GROK_MEMORY': os.environ.get('GROK_MEMORY', ''),\n"
        "})\n"
        "log.write_text(json.dumps(rows))\n"
        f"sys.stderr.write({stderr!r})\n"
        f"in_use = {bool(session_in_use_on_session_id)}\n"
        "if in_use and '--session-id' in sys.argv:\n"
        "    sys.stderr.write('error: session already in use\\n')\n"
        "    raise SystemExit(2)\n"
        f"sys.stdout.write({blob!r})\n"
        f"raise SystemExit({int(rc)})\n"
    )
    return _write_exec(tmp_path / "fake-bin" / "grok", script)


def _prep_mind(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    unique: str,
    runner=None,
    grok: Path | None = None,
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
    if grok is not None:
        monkeypatch.setenv("GROK_BIN", str(grok))
    if runner is not None:
        monkeypatch.setattr(mind, "DEFAULT_RUNNER", runner)
    return mind, state


def _flag_value(argv: list[str], flag: str) -> str:
    i = argv.index(flag)
    return argv[i + 1]


def test_mind_scripts_and_docs_exist() -> None:
    assert MIND_PY.is_file()
    assert MIND_LOOP.is_file()
    assert MIND_DOC.is_file()
    assert PLUGIN_DIR.is_dir()
    assert (PLUGIN_DIR / "plugin.json").is_file()
    assert (PLUGIN_DIR / "server.py").is_file()
    plugin = json.loads((PLUGIN_DIR / "plugin.json").read_text(encoding="utf-8"))
    assert plugin.get("name") == "studio-mind"
    src = MIND_PY.read_text(encoding="utf-8")
    loop = MIND_LOOP.read_text(encoding="utf-8")
    common = SEAT_COMMON.read_text(encoding="utf-8")
    doc = MIND_DOC.read_text(encoding="utf-8")
    for blob in (src, loop):
        assert "acp_inject" not in blob
        assert "session/prompt" not in blob
        assert "session/new" not in blob
        assert "pin-session" not in blob
        assert "pin_session" not in blob
        assert "HANDOFF" not in blob
        assert "GCS_WAKE_ACP_TIMEOUT" not in blob
        assert "no-accept" not in blob
        assert "/home/box" not in blob
        assert "palemon" not in blob.lower()
        assert "--fork-session" not in blob
        assert "--continue" not in blob
    assert "--resume" in src
    assert "--session-id" in src
    assert "--prompt-file" in src
    assert "install_studio_mind_plugin" in loop
    assert "plugin install" in common
    assert "--trust" in common
    assert "studio-mind" in common
    assert "def parse_tool_calls" not in src
    assert "Bot-equivalent" in doc or "bot-equivalent" in doc
    assert "leftover host os" in doc.lower() or "acp inject is leftover" in doc.lower()
    assert "GCS_MIND_SEATS" in doc
    assert "session/prompt" in doc
    assert "--prompt-file" in doc
    assert "plugin install" in doc
    assert "grok -p --resume" not in doc
    assert "mailbox" in doc.lower()
    assert "/home/box" not in doc
    assert "palemon" not in doc.lower()
    assert "already in use" in doc.lower()
    assert "240" in doc


def test_fake_grok_mints_then_resumes_same_uuid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "grok.argv.json"
    grok = _write_fake_grok(tmp_path, log)
    mind, state = _prep_mind(tmp_path, monkeypatch, unique="pin", grok=grok)
    _append_inbox(state, "floor", "task-mind-1", "ping from ops")
    first = mind.process_once("floor")
    assert first["consumed"] == 1
    assert _offset(state, "floor") > 0
    sid = _session_id(state, "floor")
    uuid.UUID(sid)
    rows = _argv_log(log)
    assert len(rows) == 1
    argv = rows[0]["argv"]
    _assert_no_banned_flags(argv)
    assert "--prompt-file" in argv
    mail = Path(_flag_value(argv, "--prompt-file"))
    assert mail.is_file()
    assert "ping from ops" in mail.read_text(encoding="utf-8")
    assert "--session-id" in argv
    assert _flag_value(argv, "--session-id") == sid
    assert "--resume" not in argv
    assert "--fork-session" not in argv
    assert "--continue" not in argv
    assert "--agent" not in argv
    assert argv == [
        "--session-id",
        sid,
        "--prompt-file",
        str(mail),
        "--verbatim",
        "--output-format",
        "json",
        "--always-approve",
        "--permission-mode",
        "bypassPermissions",
        "--max-turns",
        "40",
    ]
    assert rows[0]["GROK_MEMORY"] == "1"
    assert str(state / "floor" / "grok-home") in rows[0]["GROK_HOME"]
    assert rows[0]["cwd"] == str(REPO)
    transcript = _transcript_rows(state, "floor")
    assert any(r.get("role") == "user" and "ping from ops" in str(r.get("content", "")) for r in transcript)
    assert any(r.get("role") == "assistant" and "ok" in str(r.get("content", "")) for r in transcript)
    assert not any(r.get("role") == "tool" for r in transcript)

    _append_inbox(state, "floor", "task-mind-2", "second ping")
    second = mind.process_once("floor")
    assert second["consumed"] == 1
    assert _session_id(state, "floor") == sid
    rows2 = _argv_log(log)
    assert len(rows2) == 2
    argv2 = rows2[1]["argv"]
    _assert_no_banned_flags(argv2)
    assert "--resume" in argv2
    assert _flag_value(argv2, "--resume") == sid
    assert "--session-id" not in argv2
    assert "--agent" not in argv2
    assert argv2 == [
        "--resume",
        sid,
        "--prompt-file",
        str(Path(_flag_value(argv2, "--prompt-file"))),
        "--verbatim",
        "--output-format",
        "json",
        "--always-approve",
        "--permission-mode",
        "bypassPermissions",
        "--max-turns",
        "40",
    ]
    assert "--prompt-file" in argv2
    empty = mind.process_once("floor")
    assert empty["consumed"] == 0
    assert _session_id(state, "floor") == sid


def test_empty_json_harvest_does_not_remint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "grok.argv.json"
    grok = _write_fake_grok(tmp_path, log, stdout="{}")
    mind, state = _prep_mind(tmp_path, monkeypatch, unique="emptyjson", grok=grok)
    _append_inbox(
        state,
        "floor",
        "task-scan-1",
        "Keep-alive received. Scanning A2A inboxes, fleet ledgers",
    )
    result = mind.process_once("floor")
    assert result["consumed"] == 1
    sid = _session_id(state, "floor")
    _append_inbox(state, "floor", "task-scan-2", "another scan")
    mind.process_once("floor")
    assert _session_id(state, "floor") == sid
    argv2 = _argv_log(log)[1]["argv"]
    assert "--resume" in argv2
    assert _flag_value(argv2, "--resume") == sid
    rows = _transcript_rows(state, "floor")
    assert any(r.get("role") == "assistant" and r.get("content") == "{}" for r in rows)


def test_grok_nonzero_exit_does_not_advance_offset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    log = tmp_path / "grok.argv.json"
    key = "test-cursor-api-key-should-not-leak"
    grok = _write_fake_grok(
        tmp_path,
        log,
        rc=1,
        stdout="",
        stderr=f"CURSOR_API_KEY={key} boom",
    )
    mind, state = _prep_mind(tmp_path, monkeypatch, unique="failrc", grok=grok)
    _append_inbox(state, "floor", "task-fail-1", "do work")
    result = mind.process_once("floor")
    assert result["consumed"] == 0
    assert result.get("reason") == "runner-fail"
    assert _offset(state, "floor") == 0
    assert _transcript_rows(state, "floor") == []
    sid = _session_id(state, "floor")
    argv = _argv_log(log)[0]["argv"]
    _assert_no_banned_flags(argv)
    assert "--session-id" in argv
    assert "--resume" not in argv
    assert _flag_value(argv, "--session-id") == sid
    err = capsys.readouterr().err
    assert "MIND_FAIL" in err
    assert key not in err
    assert "CURSOR_API_KEY=[redacted]" in err
    assert "stderr=" in err


def test_process_once_does_not_execute_plugins_from_stdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tb_log = tmp_path / "taskboard.argv"
    binary = _write_exec(
        tmp_path / "host-bin" / "taskboard",
        "#!/bin/sh\n"
        f'echo "$@" >> "{tb_log}"\n'
        'echo TICKET_OK "$@"\n',
    )
    monkeypatch.setenv("TASKBOARD_BIN", str(binary))
    log = tmp_path / "grok.argv.json"
    grok = _write_fake_grok(
        tmp_path,
        log,
        stdout=json.dumps({"name": "ticket", "arguments": {"argv": ["list"]}}),
    )
    mind, state = _prep_mind(tmp_path, monkeypatch, unique="noploop", grok=grok)
    _append_inbox(state, "floor", "task-tools-1", "please list tickets")
    result = mind.process_once("floor")
    assert result["consumed"] == 1
    assert not tb_log.is_file()
    assert not any(r.get("role") == "tool" for r in _transcript_rows(state, "floor"))


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
    monkeypatch.setenv("TASKBOARD_BIN", str(binary))
    mind, _state = _prep_mind(tmp_path, monkeypatch, unique="ticket", runner=lambda *_a, **_k: {"text": "x"})
    monkeypatch.setenv("GCS_TASKBOARD_DB", str(db))
    out = mind.call_plugin("ticket", {"argv": ["list"]})
    assert "TICKET_OK" in out
    argv = log.read_text(encoding="utf-8") if log.is_file() else ""
    assert "--db" in argv, argv
    assert str(db) in argv, argv
    assert "ticket" in argv


def test_injected_runner_inbox_grows_transcript_and_offset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []

    def fake(prompt: str, **_kwargs: object) -> dict:
        seen.append(prompt)
        return {"text": f"ack:{prompt}"}

    mind, state = _prep_mind(tmp_path, monkeypatch, unique="inbox", runner=fake)
    _append_inbox(state, "floor", "task-mind-1", "ping from ops")
    first = mind.process_once("floor")
    assert first["consumed"] == 1
    assert _offset(state, "floor") > 0
    rows = _transcript_rows(state, "floor")
    assert any(r.get("role") == "user" and "ping from ops" in str(r.get("content", "")) for r in rows)
    assert any(r.get("role") == "assistant" and "ack:" in str(r.get("content", "")) for r in rows)
    assert seen and "ping from ops" in seen[0]
    assert "ticket" in mind.PLUGINS
    assert "a2a_send" in mind.PLUGINS
    assert "cloud_launch" in mind.PLUGINS


def test_missing_ticket_binary_returns_error_string_not_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TASKBOARD_BIN", raising=False)
    mind, _state = _prep_mind(
        tmp_path, monkeypatch, unique="missingbin", runner=lambda *_a, **_k: {"text": ""}
    )
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    blob = mind.call_plugin("ticket", {"argv": ["list"]}).lower()
    assert "missing" in blob or "plugin_err" in blob or "error" in blob


def test_runner_exception_does_not_advance_offset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(_prompt: str, **_kwargs: object) -> dict:
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
    def fake(_prompt: str, **_kwargs: object) -> dict:
        return {"text": "should not run"}

    mind, state = _prep_mind(tmp_path, monkeypatch, unique="skip", runner=fake)
    _append_inbox(state, "donald", "task-don-1", "hello")
    result = mind.process_once("donald")
    assert result["consumed"] == 0
    assert "skip" in str(result.get("reason", "")).lower()
    assert _offset(state, "donald") == 0
    assert _transcript_rows(state, "donald") == []


def test_grok_cli_argv_first_and_later_turns() -> None:
    mind = _load(MIND_PY, "gcs_mind_argv")
    mail = Path("/tmp/gcs-mind-mail.txt")
    sid = _LAW_SID
    first = mind.grok_cli_argv(
        session_id=sid,
        minted=False,
        mail_path=mail,
        grok="grok",
    )
    later = mind.grok_cli_argv(
        session_id=sid,
        minted=True,
        mail_path=mail,
        grok="grok",
    )
    assert first == _law_argv(sid, mail, minted=False)
    assert later == _law_argv(sid, mail, minted=True)
    _assert_no_banned_flags(first)
    _assert_no_banned_flags(later)
    assert first[1] == "--session-id"
    assert later[1] == "--resume"
    joined = " ".join(first + later)
    assert "--fork-session" not in joined
    assert "--continue" not in joined
    assert "session/prompt" not in joined
    assert "/home/box" not in joined
    assert "--agent" not in first
    assert "--agent" not in later


def test_grok_cli_argv_agent_only_for_yaml_frontmatter(tmp_path: Path) -> None:
    mind = _load(MIND_PY, "gcs_mind_agent_yaml")
    mail = tmp_path / "mail.txt"
    mail.write_text("hi\n", encoding="utf-8")
    sid = _LAW_SID
    yaml_agent = tmp_path / "agent.md"
    yaml_agent.write_text("---\nname: floor-mind\n---\nYou are floor.\n", encoding="utf-8")
    soul = tmp_path / "SOUL.md"
    soul.write_text("# floor\nNamed identity, not an agent file.\n", encoding="utf-8")
    missing = tmp_path / "nope.md"
    assert mind.yaml_agent_file(yaml_agent) == str(yaml_agent)
    assert mind.yaml_agent_file(soul) is None
    assert mind.yaml_agent_file(None) is None
    assert mind.yaml_agent_file(missing) is None
    with_yaml = mind.grok_cli_argv(
        session_id=sid,
        minted=True,
        mail_path=mail,
        agent=str(yaml_agent),
        grok="grok",
    )
    with_soul = mind.grok_cli_argv(
        session_id=sid,
        minted=True,
        mail_path=mail,
        agent=str(soul),
        grok="grok",
    )
    law = _law_argv(sid, mail, minted=True)
    assert with_yaml == law + ["--agent", str(yaml_agent)]
    assert with_soul == law
    _assert_no_banned_flags(with_yaml)
    _assert_no_banned_flags(with_soul)


def test_session_already_in_use_resumes_same_uuid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "grok.argv.json"
    grok = _write_fake_grok(tmp_path, log, session_in_use_on_session_id=True)
    mind, state = _prep_mind(tmp_path, monkeypatch, unique="inuse", grok=grok)
    _append_inbox(state, "floor", "task-inuse-1", "first mail")
    result = mind.process_once("floor")
    assert result["consumed"] == 1
    sid = _session_id(state, "floor")
    uuid.UUID(sid)
    rows = _argv_log(log)
    assert len(rows) == 2
    first, retry = rows[0]["argv"], rows[1]["argv"]
    _assert_no_banned_flags(first)
    _assert_no_banned_flags(retry)
    assert "--session-id" in first
    assert _flag_value(first, "--session-id") == sid
    assert "--resume" not in first
    assert "--resume" in retry
    assert _flag_value(retry, "--resume") == sid
    assert "--session-id" not in retry
    assert (state / "floor" / "mind" / "session.minted").is_file()
    assert _session_id(state, "floor") == sid
    _append_inbox(state, "floor", "task-inuse-2", "second mail")
    mind.process_once("floor")
    assert _session_id(state, "floor") == sid
    argv3 = _argv_log(log)[2]["argv"]
    assert "--resume" in argv3
    assert _flag_value(argv3, "--resume") == sid
    assert "--session-id" not in argv3


def test_mind_fail_logs_redacted_stderr_240(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    log = tmp_path / "grok.argv.json"
    key = "test-cursor-api-key-should-not-leak"
    noise = "N" * 400
    grok = _write_fake_grok(
        tmp_path, log, rc=2, stdout="", stderr=f"CURSOR_API_KEY={key} clap: {noise}"
    )
    mind, state = _prep_mind(tmp_path, monkeypatch, unique="fail240", grok=grok)
    _append_inbox(state, "floor", "task-fail-240", "do work")
    result = mind.process_once("floor")
    assert result["consumed"] == 0
    err = capsys.readouterr().err
    assert "MIND_FAIL" in err
    assert key not in err
    assert "CURSOR_API_KEY=[redacted]" in err
    assert mind.MIND_FAIL_STDERR_CHARS == 240
    snippet = err.split("stderr=", 1)[1].strip()
    assert len(snippet) <= 240
    assert "N" * 400 not in err


def test_seat_mind_loop_installs_studio_mind_plugin(tmp_path: Path) -> None:
    log = tmp_path / "plugin.argv"
    grok = _write_exec(
        tmp_path / "fake-bin" / "grok",
        "#!/bin/sh\n"
        f'printf "%s\\n" "$@" >> "{log}"\n'
        'printf "GROK_HOME=%s\\n" "$GROK_HOME" >> '
        f'"{log}.env"\n'
        "exit 0\n",
    )
    env = {
        "PATH": f"{grok.parent}:/usr/bin:/bin",
        "HOME": str(tmp_path / "home"),
        "GCS_ROOT": str(REPO),
        "GCS_A2A_STATE": str(tmp_path / "a2a-state"),
        "GROK_HOME": str(tmp_path / "grok-home"),
        "TASKBOARD_BIN": str(
            _write_exec(tmp_path / "host-bin" / "taskboard", "#!/bin/sh\nexit 0\n")
        ),
        "LC_ALL": "C",
        "TERM": "dumb",
    }
    script = r"""
set -euo pipefail
source scripts/directors/seat-daemon-common.sh
install_studio_mind_plugin floor
"""
    proc = subprocess.run(
        ["bash", "-c", script],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    argv = log.read_text(encoding="utf-8") if log.is_file() else ""
    assert "plugin" in argv, argv
    assert "install" in argv, argv
    assert "--trust" in argv, argv
    assert "studio-mind" in argv, argv
    assert "-p" not in argv.split(), argv
    assert "--plugin-dir" not in argv, argv
    assert "--agent-profile" not in argv, argv
    grok_home = (tmp_path / "plugin.argv.env").read_text(encoding="utf-8")
    assert str(tmp_path / "grok-home") in grok_home
    loop = MIND_LOOP.read_text(encoding="utf-8")
    assert "install_studio_mind_plugin" in loop
    assert "plugin install" in loop or "install_studio_mind_plugin" in loop


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


def test_studio_mind_plugin_lists_tools() -> None:
    server = PLUGIN_DIR / "server.py"
    msg = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}) + "\n"
    proc = subprocess.run(
        ["python3", str(server)],
        cwd=str(REPO),
        input=msg,
        capture_output=True,
        text=True,
        timeout=10,
        env={**os.environ, "GCS_ROOT": str(REPO), "GCS_MCP_NDJSON": "1"},
    )
    assert proc.returncode == 0, proc.stderr
    reply = json.loads(proc.stdout.splitlines()[0])
    names = {t["name"] for t in reply["result"]["tools"]}
    assert names == {"ticket", "a2a_send", "cloud_launch"}
