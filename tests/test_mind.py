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
import time
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


def _runner_name(state: Path, seat: str) -> str:
    path = state / seat / "mind" / "runner"
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


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
GROK_MIND_MODEL = "grok-4.6"
GROK_MIND_REASONING_EFFORT = "xhigh"  # CLI extra-high alias


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
        "--model",
        GROK_MIND_MODEL,
        "--reasoning-effort",
        GROK_MIND_REASONING_EFFORT,
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


CURSOR_MIND_MODEL = "cursor-grok-4.6-xhigh"
_CURSOR_CHAT_ID = "11111111-2222-3333-4444-555555555555"


def _cursor_session_id(state: Path, seat: str) -> str:
    path = state / seat / "mind" / "cursor-session"
    assert path.is_file(), "pinned cursor chat id missing"
    return path.read_text(encoding="utf-8").strip()


def _cursor_law_argv(binary: str, chat_id: str, prompt: str) -> list[str]:
    return [
        binary,
        "--resume",
        chat_id,
        "-p",
        "--force",
        "--output-format",
        "json",
        "--trust",
        "--approve-mcps",
        "--model",
        CURSOR_MIND_MODEL,
        prompt,
    ]


def _assert_cursor_clap(argv: list[str], *, chat_id: str, prompt: str) -> None:
    assert "--resume" in argv
    assert _flag_value(argv, "--resume") == chat_id
    assert argv.count("--resume") == 1
    assert "-p" in argv or "--print" in argv
    assert "--force" in argv or "--yolo" in argv
    assert "--output-format" in argv
    assert _flag_value(argv, "--output-format") == "json"
    assert "--trust" in argv
    assert "--approve-mcps" in argv
    assert "--model" in argv
    assert _flag_value(argv, "--model") == CURSOR_MIND_MODEL
    assert argv[-1] == prompt or prompt in argv[-1]
    assert "--prompt-file" not in argv
    assert "--session-id" not in argv
    assert "--continue" not in argv
    assert "--fork-session" not in argv
    assert "--plugin-dir" not in argv
    assert "--agent-profile" not in argv
    assert not any(a == "-1" or a.startswith("--resume=") for a in argv)
    joined = " ".join(argv)
    assert "--resume=-1" not in joined
    assert CURSOR_MIND_MODEL in argv
    assert "composer-2" not in argv
    assert "grok-4.6" not in argv or CURSOR_MIND_MODEL in argv


def _write_fake_cursor_agent(
    tmp_path: Path,
    log: Path,
    *,
    chat_id: str = _CURSOR_CHAT_ID,
    rc: int = 0,
    stdout: str | None = None,
    stderr: str = "",
    create_chat_rc: int = 0,
    name: str = "agent",
) -> Path:
    blob = stdout if stdout is not None else json.dumps({"ok": True, "runner": "cursor"})
    script = (
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        f"log = Path({str(log)!r})\n"
        f"chat_id = {chat_id!r}\n"
        "rows = json.loads(log.read_text()) if log.is_file() else []\n"
        "rows.append({\n"
        "    'argv': sys.argv[1:],\n"
        "    'cwd': os.getcwd(),\n"
        "    'GROK_HOME': os.environ.get('GROK_HOME'),\n"
        "    'GROK_MEMORY': os.environ.get('GROK_MEMORY'),\n"
        "    'has_cursor_api_key': bool(os.environ.get('CURSOR_API_KEY')),\n"
        "})\n"
        "log.write_text(json.dumps(rows))\n"
        "if 'create-chat' in sys.argv[1:]:\n"
        "    sys.stdout.write(chat_id + '\\n')\n"
        f"    sys.stderr.write({stderr!r})\n"
        f"    raise SystemExit({int(create_chat_rc)})\n"
        f"sys.stderr.write({stderr!r})\n"
        f"sys.stdout.write({blob!r})\n"
        f"raise SystemExit({int(rc)})\n"
    )
    return _write_exec(tmp_path / "fake-bin" / name, script)


def _prep_mind(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    unique: str,
    runner=None,
    grok: Path | None = None,
    cursor: Path | None = None,
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
    monkeypatch.delenv("GCS_MIND_RUNNER", raising=False)
    monkeypatch.delenv("GCS_CURSOR_BIN", raising=False)
    if grok is not None:
        monkeypatch.setenv("GROK_BIN", str(grok))
    if cursor is not None:
        monkeypatch.setenv("GCS_CURSOR_BIN", str(cursor))
    if runner is not None:
        monkeypatch.setattr(mind, "DEFAULT_RUNNER", runner)
    orig_home = mind.grok_home_dir

    def _grok_home_with_linear(seat: str) -> Path:
        d = orig_home(seat)
        cfg = d / "config.toml"
        if not cfg.is_file():
            cfg.write_text(
                "[mcp_servers.linear]\n"
                f'url = "{mind.LINEAR_MCP_URL}"\n'
                'headers = { Authorization = "Bearer ${LINEAR_API_KEY}" }\n',
                encoding="utf-8",
            )
        return d

    monkeypatch.setattr(mind, "grok_home_dir", _grok_home_with_linear)
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
    assert "cursor-session" in src
    assert "cursor-session" in doc
    assert "create-chat" in src
    assert "create-chat" in doc
    assert CURSOR_MIND_MODEL in src
    assert CURSOR_MIND_MODEL in doc
    assert "--model" in src
    assert GROK_MIND_MODEL in src
    assert "--reasoning-effort" in src or "--effort" in src
    assert GROK_MIND_REASONING_EFFORT in src or "extra-high" in src
    assert GROK_MIND_MODEL in doc
    assert "--reasoning-effort" in doc or "--effort" in doc
    assert GROK_MIND_REASONING_EFFORT in doc or "extra-high" in doc
    assert "usage balance exhausted" in doc.lower()
    assert "GCS_MIND_RUNNER" in src
    assert "GCS_MIND_RUNNER" in doc
    assert "GCS_MIND_RUNNER=auto" in doc or 'default "auto"' in src or 'or "auto"' in src
    assert "MIND_SWITCH" in src
    assert "MIND_SWITCH" in doc
    assert "MIND_FALLBACK" not in src
    assert "mind/runner" in src or ' / "runner"' in src
    assert "mind/runner" in doc
    assert "--verbatim" in doc
    assert "--always-approve" in doc
    assert "bypassPermissions" in doc
    assert "--max-turns" in doc
    assert "do not transfer" in doc.lower() or "does not transfer" in doc.lower() or "do not transfer" in src.lower()
    assert "two catalogs" in doc.lower()
    assert "higgsfield" in doc.lower()
    assert "deliver_wake" in doc
    assert "fast=false" in doc
    assert "cursor cloud" in doc.lower()
    receipt_blob = (doc + "\n" + ARCH_DOC.read_text(encoding="utf-8")).lower()
    assert "receipt" in receipt_blob
    assert "not mind-turn" in receipt_blob or "not mind turn" in receipt_blob
    assert "TASK_STATE_COMPLETED" in ARCH_DOC.read_text(encoding="utf-8")
    assert "format_mail_turn" not in src
    assert "hermes-agent" not in src.lower()
    assert "chrome-devtools" in doc
    assert "chrome-devtools-mcp" in doc
    assert "127.0.0.1:5173" in doc
    assert "qa-a" in doc
    assert "not cursor cli" in doc.lower() or "not cursor" in doc.lower()
    assert "cloudagent" in doc.lower() or "bot cloudagent" in doc.lower() or "grok bot" in doc.lower()
    cursor_mcp = json.loads((REPO / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
    assert "chrome-devtools" not in (cursor_mcp.get("mcpServers") or {})


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
        "--model",
        GROK_MIND_MODEL,
        "--reasoning-effort",
        GROK_MIND_REASONING_EFFORT,
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
        "--model",
        GROK_MIND_MODEL,
        "--reasoning-effort",
        GROK_MIND_REASONING_EFFORT,
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
    assert "cloud_watch" not in mind.PLUGINS


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
    assert "--model" in first and _flag_value(first, "--model") == GROK_MIND_MODEL
    assert "--model" in later and _flag_value(later, "--model") == GROK_MIND_MODEL
    effort_flag = "--reasoning-effort" if "--reasoning-effort" in first else "--effort"
    assert _flag_value(first, effort_flag) in {GROK_MIND_REASONING_EFFORT, "extra-high", "max"}
    assert _flag_value(later, effort_flag) in {GROK_MIND_REASONING_EFFORT, "extra-high", "max"}
    cursor = mind.cursor_cli_argv(
        chat_id=_CURSOR_CHAT_ID, prompt="keep cursor pin", binary="agent"
    )
    assert _flag_value(cursor, "--model") == CURSOR_MIND_MODEL
    assert "--reasoning-effort" not in cursor
    assert mind.GROK_MIND_MODEL == GROK_MIND_MODEL
    assert mind.GROK_MIND_REASONING_EFFORT == GROK_MIND_REASONING_EFFORT
    assert mind.CURSOR_MIND_MODEL == CURSOR_MIND_MODEL


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


def test_studio_mind_plugin_already_installed_is_ok(tmp_path: Path) -> None:
    """grok 'Error: repo studio-mind-... already installed' is MIND_PLUGIN_OK.

    Seat start reinstalls studio-mind every loop. A non-zero grok exit with
    that message is idempotent success, not reason=install-fail.
    """
    log = tmp_path / "plugin.argv"
    stamp = tmp_path / "plugin.installed"
    grok = _write_exec(
        tmp_path / "fake-bin" / "grok",
        "#!/bin/sh\n"
        f'printf "%s\\n" "$@" >> "{log}"\n'
        f'if [ -f "{stamp}" ]; then\n'
        '  echo "Error: repo studio-mind-deadbeef already installed" >&2\n'
        "  exit 1\n"
        "fi\n"
        f'touch "{stamp}"\n'
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
    assert blob.count("MIND_PLUGIN_OK") >= 2, blob
    assert "reason=install-fail" not in blob, blob
    assert "MIND_PLUGIN_SKIP" not in blob, blob
    argv = log.read_text(encoding="utf-8")
    assert argv.count("plugin") >= 2
    assert "--trust" in argv
    assert "studio-mind" in argv


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


def _spawn_sleep() -> subprocess.Popen:
    return subprocess.Popen(
        ["sleep", "180"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _write_pid(path: Path, proc: subprocess.Popen) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{proc.pid}\n", encoding="utf-8")


def _reap_proc(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.kill()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        pass


def _reap_pid(pid: int) -> None:
    if pid <= 0:
        return
    try:
        os.kill(pid, 9)
    except OSError:
        return
    for _ in range(20):
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.05)


def _bus_env(state: Path, extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {
            "GCS_MIND_SEATS",
            "GCS_START_SEAT_DAEMONS",
            "GCS_ACP_STOP_WITH_BUS",
            "GCS_BOT_BRIDGE",
        }
    }
    env.update(
        {
            "GCS_ROOT": str(REPO),
            "GCS_A2A_STATE": str(state),
            "GCS_START_SEAT_DAEMONS": "0",
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "LC_ALL": "C",
        }
    )
    if extra:
        env.update(extra)
    return env


def _run_bus_start(state: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(BUS_SH), "start"],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=25,
    )


def _plant_leftover_bus(
    state: Path, *, mind_seats: tuple[str, ...]
) -> dict[str, subprocess.Popen]:
    """Stand-ins for leftover studio-bus pids. Dispatch is the one that may bounce."""
    state.mkdir(parents=True, exist_ok=True)
    procs = {
        "hub": _spawn_sleep(),
        "dispatch": _spawn_sleep(),
        "bot-bridge": _spawn_sleep(),
        "shepherd": _spawn_sleep(),
        "ticker": _spawn_sleep(),
    }
    _write_pid(state / "hub.pid", procs["hub"])
    _write_pid(state / "dispatch.pid", procs["dispatch"])
    _write_pid(state / "bot-bridge.pid", procs["bot-bridge"])
    _write_pid(state / "fleet-shepherd.pid", procs["shepherd"])
    _write_pid(state / "host-ticker.pid", procs["ticker"])
    for seat in mind_seats:
        mind = _spawn_sleep()
        serve = _spawn_sleep()
        procs[f"mind:{seat}"] = mind
        procs[f"serve:{seat}"] = serve
        _write_pid(state / seat / "mind" / "pid", mind)
        _write_pid(state / seat / "daemon.pid", serve)
    return procs


def _reap_planted(procs: dict[str, subprocess.Popen], state: Path) -> None:
    try:
        raw = (state / "dispatch.pid").read_text(encoding="utf-8").strip()
        leftover = procs["dispatch"].pid
        if raw and int(raw.split()[0]) != leftover:
            _reap_pid(int(raw.split()[0]))
    except (OSError, ValueError, KeyError):
        pass
    for proc in procs.values():
        _reap_proc(proc)


def _prep_dispatch_skip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> tuple[ModuleType, Path, Path]:
    monkeypatch.delenv("GCS_MIND_SEATS", raising=False)
    dispatch = _load(DISPATCH_PY, name)
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
    return dispatch, state, inject_stamp


def test_dispatch_skips_live_mind_pid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    dispatch, state, inject_stamp = _prep_dispatch_skip(
        tmp_path, monkeypatch, "gcs_dispatch_mind_skip_pid"
    )
    qa = state / "qa-a"
    (qa / "mind").mkdir(parents=True)
    (qa / "mind" / "pid").write_text(str(os.getpid()) + "\n", encoding="utf-8")
    _append_inbox(state, "qa-a", "task-mind-skip", "LAUNCH ONLY do not inject")
    started = dispatch._process_seat("qa-a", dry_run=False)
    assert started == 0
    assert not inject_stamp.is_file()
    assert not (qa / "dispatch.offset").is_file()
    out = capsys.readouterr().out
    assert "DISPATCH_SKIP seat=qa-a reason=mind-owns-inbox" in out
    src = DISPATCH_PY.read_text(encoding="utf-8")
    assert "mind-owns-inbox" in src
    assert "mind/pid" in src
    assert "MIND_SEATS = _mind_seats_fn" not in src


def test_dispatch_skips_mind_owns_inbox_from_current_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Long-lived dispatch must re-read GCS_MIND_SEATS; do not freeze at import."""
    dispatch, state, inject_stamp = _prep_dispatch_skip(
        tmp_path, monkeypatch, "gcs_dispatch_mind_skip_env"
    )
    _append_inbox(state, "qa-a", "task-mind-env", "LAUNCH ONLY do not inject")
    first = dispatch._process_seat("qa-a", dry_run=True)
    assert first == 0
    first_out = capsys.readouterr().out
    assert "DISPATCH_SKIP seat=qa-a reason=mind-owns-inbox" not in first_out
    assert "DISPATCH_DRY_RUN" in first_out

    monkeypatch.setenv("GCS_MIND_SEATS", "qa-a")
    started = dispatch._process_seat("qa-a", dry_run=False)
    assert started == 0
    assert not inject_stamp.is_file()
    assert not (state / "qa-a" / "dispatch.offset").is_file()
    out = capsys.readouterr().out
    assert "DISPATCH_SKIP seat=qa-a reason=mind-owns-inbox" in out
    assert "DISPATCH_LAUNCH" not in out


def test_bus_recycles_dispatch_when_mind_seats_change_without_killing_minds(
    tmp_path: Path,
) -> None:
    """PAL-15: leftover dispatch from before GCS_MIND_SEATS=qa-a must bounce alone."""
    state = tmp_path / "a2a-state"
    procs = _plant_leftover_bus(state, mind_seats=("qa-a",))
    leftover_disp = procs["dispatch"].pid
    (state / "studio.env").write_text("GCS_MIND_SEATS=qa-a\n", encoding="utf-8")
    try:
        proc = _run_bus_start(state, _bus_env(state))
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, out
        assert "STUDIO_BUS_DISPATCH_RECYCLE" in out
        assert "reason=mind-seats-changed" in out
        assert "STUDIO_BUS_DISPATCH_START" in out
        assert "STUDIO_BUS_DISPATCH_ALREADY" not in out
        assert "STUDIO_BUS_HUB_ALREADY" in out
        assert "STUDIO_BUS_SHEPHERD_ALREADY" in out
        # PAL-25 remaining: leftover bot-bridge.pid is not a default start.
        assert "STUDIO_BUS_BOT_BRIDGE_ALREADY" not in out
        assert "STUDIO_BUS_BOT_BRIDGE_START" not in out
        assert "STUDIO_BUS_BOT_BRIDGE_SKIP" in out
        assert "STUDIO_BUS_BOT_BRIDGE_STOP" in out
        assert "STUDIO_BUS_MIND_ALREADY seat=qa-a" in out
        assert "STUDIO_BUS_HUB_STOP" not in out
        assert "STUDIO_BUS_SHEPHERD_STOP" not in out
        assert "STUDIO_BUS_MIND_STOP" not in out
        assert "STUDIO_BUS_TICKER_STOP" not in out
        assert "stop-seat-daemon" not in out
        assert procs["hub"].poll() is None
        assert procs["bot-bridge"].poll() is not None
        assert procs["shepherd"].poll() is None
        assert procs["ticker"].poll() is None
        assert procs["mind:qa-a"].poll() is None
        assert procs["serve:qa-a"].poll() is None
        assert procs["dispatch"].poll() is not None
        new_pid = int((state / "dispatch.pid").read_text(encoding="utf-8").strip().split()[0])
        assert new_pid != leftover_disp
        os.kill(new_pid, 0)
        persisted = (state / "dispatch.mind-seats").read_text(encoding="utf-8")
        seats = {part.strip() for part in persisted.replace(",", "\n").split() if part.strip()}
        assert seats == {"qa-a"}
    finally:
        _reap_planted(procs, state)


def test_bus_keeps_dispatch_when_mind_seats_match(tmp_path: Path) -> None:
    state = tmp_path / "a2a-state"
    procs = _plant_leftover_bus(state, mind_seats=("floor", "qa-a"))
    leftover_disp = procs["dispatch"].pid
    (state / "dispatch.mind-seats").write_text("qa-a,floor\n", encoding="utf-8")
    env = _bus_env(state, {"GCS_MIND_SEATS": "floor,qa-a"})
    try:
        proc = _run_bus_start(state, env)
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, out
        assert "STUDIO_BUS_DISPATCH_ALREADY" in out
        assert f"pid={leftover_disp}" in out
        assert "STUDIO_BUS_DISPATCH_RECYCLE" not in out
        assert "STUDIO_BUS_DISPATCH_START" not in out
        assert "STUDIO_BUS_DISPATCH_STOP" not in out
        assert procs["dispatch"].poll() is None
        assert procs["hub"].poll() is None
        assert procs["mind:floor"].poll() is None
        assert procs["mind:qa-a"].poll() is None
        assert procs["serve:qa-a"].poll() is None
        assert int((state / "dispatch.pid").read_text(encoding="utf-8").strip().split()[0]) == leftover_disp
    finally:
        _reap_planted(procs, state)


def _reap_pidfile(state: Path, name: str) -> None:
    path = state / f"{name}.pid"
    try:
        raw = path.read_text(encoding="utf-8").strip().split()[0]
        _reap_pid(int(raw))
    except (OSError, ValueError, IndexError):
        pass


def test_bus_skips_bot_bridge_by_default(tmp_path: Path) -> None:
    """Jay: Bot seats standby. recover / start must not wake them unless opted in."""
    state = tmp_path / "a2a-state"
    procs = _plant_leftover_bus(state, mind_seats=())
    _reap_proc(procs["bot-bridge"])
    (state / "bot-bridge.pid").unlink(missing_ok=True)
    try:
        proc = _run_bus_start(state, _bus_env(state))
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, out
        assert "STUDIO_BUS_BOT_BRIDGE_START" not in out
        assert "STUDIO_BUS_BOT_BRIDGE_SKIP" in out
        assert "GCS_BOT_BRIDGE=1" in out or "standby" in out.lower()
        pid_path = state / "bot-bridge.pid"
        if pid_path.is_file():
            raw = pid_path.read_text(encoding="utf-8").strip().split()[0]
            pid = int(raw)
            try:
                os.kill(pid, 0)
                alive = True
            except OSError:
                alive = False
            assert not alive, "default start must not leave a live bot-bridge"
        bus = BUS_SH.read_text(encoding="utf-8")
        assert "GCS_BOT_BRIDGE" in bus
        recover = (REPO / "recover.sh").read_text(encoding="utf-8")
        # PAL-25: usage may name the opt-in knob; recover must not force it on.
        for line in recover.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert "export GCS_BOT_BRIDGE=1" not in stripped
            assert not stripped.startswith("GCS_BOT_BRIDGE=1")
            assert "GCS_BOT_BRIDGE=${GCS_BOT_BRIDGE:-1}" not in stripped
    finally:
        _reap_pidfile(state, "bot-bridge")
        _reap_planted(procs, state)


def test_bus_starts_bot_bridge_when_gcs_bot_bridge_is_1(tmp_path: Path) -> None:
    state = tmp_path / "a2a-state"
    procs = _plant_leftover_bus(state, mind_seats=())
    _reap_proc(procs["bot-bridge"])
    (state / "bot-bridge.pid").unlink(missing_ok=True)
    env = _bus_env(
        state,
        {"GCS_BOT_BRIDGE": "1", "GCS_BOT_BRIDGE_POLL_SEC": "60"},
    )
    started_pid = 0
    try:
        proc = _run_bus_start(state, env)
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, out
        assert "STUDIO_BUS_BOT_BRIDGE_START" in out
        assert "STUDIO_BUS_BOT_BRIDGE_SKIP" not in out
        raw = (state / "bot-bridge.pid").read_text(encoding="utf-8").strip().split()[0]
        started_pid = int(raw)
        os.kill(started_pid, 0)
    finally:
        if started_pid:
            _reap_pid(started_pid)
        _reap_pidfile(state, "bot-bridge")
        _reap_planted(procs, state)


def test_bus_keeps_dispatch_when_mind_seats_file_missing_and_current_empty(
    tmp_path: Path,
) -> None:
    state = tmp_path / "a2a-state"
    procs = _plant_leftover_bus(state, mind_seats=())
    leftover_disp = procs["dispatch"].pid
    try:
        proc = _run_bus_start(state, _bus_env(state))
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, out
        assert "STUDIO_BUS_DISPATCH_ALREADY" in out
        assert "STUDIO_BUS_DISPATCH_RECYCLE" not in out
        assert procs["dispatch"].poll() is None
        assert int((state / "dispatch.pid").read_text(encoding="utf-8").strip().split()[0]) == leftover_disp
    finally:
        _reap_planted(procs, state)


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


def test_cursor_cli_argv_pins_model_and_never_continues() -> None:
    mind = _load(MIND_PY, "gcs_mind_cursor_argv")
    prompt = "mail line from ops"
    argv = mind.cursor_cli_argv(
        chat_id=_CURSOR_CHAT_ID,
        prompt=prompt,
        binary="agent",
    )
    assert argv == _cursor_law_argv("agent", _CURSOR_CHAT_ID, prompt)
    _assert_cursor_clap(argv, chat_id=_CURSOR_CHAT_ID, prompt=prompt)
    create = mind.cursor_create_chat_argv(binary="agent")
    assert create == ["agent", "create-chat"]
    assert "--resume" not in create
    assert "--session-id" not in create
    assert "--continue" not in create
    src = MIND_PY.read_text(encoding="utf-8")
    assert "--continue" not in src
    assert "cursor-session" in src
    assert "mind/session" in src or "cursor-session" in src
    assert mind.CURSOR_MIND_MODEL == CURSOR_MIND_MODEL


def test_cursor_cli_binary_prefers_cursor_grok_wrapper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bindir = tmp_path / "path-bin"
    _write_exec(bindir / "agent", "#!/bin/sh\nexit 1\n")
    wrapper = _write_exec(bindir / "cursor-grok", "#!/bin/sh\nexit 0\n")
    monkeypatch.delenv("GCS_CURSOR_BIN", raising=False)
    monkeypatch.setenv("PATH", f"{bindir}:/usr/bin:/bin")
    mind = _load(MIND_PY, "gcs_mind_which_cursor")
    chosen = Path(mind.cursor_cli_binary())
    assert chosen.resolve() == wrapper.resolve()
    monkeypatch.setenv("GCS_CURSOR_BIN", "/tmp/explicit-cursor-bin")
    assert mind.cursor_cli_binary() == "/tmp/explicit-cursor-bin"


def test_cursor_create_chat_then_resume_separate_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    grok_log = tmp_path / "grok.argv.json"
    cursor_log = tmp_path / "cursor.argv.json"
    grok = _write_fake_grok(tmp_path, grok_log)
    cursor = _write_fake_cursor_agent(tmp_path, cursor_log)
    monkeypatch.setenv("CURSOR_API_KEY", "test-cursor-api-key-not-leaked")
    monkeypatch.setenv("GROK_HOME", str(tmp_path / "ambient-grok-home"))
    mind, state = _prep_mind(
        tmp_path, monkeypatch, unique="cursorpin", grok=grok, cursor=cursor
    )
    monkeypatch.setenv("GCS_MIND_RUNNER", "cursor")
    _append_inbox(state, "floor", "task-cur-1", "cursor first mail")
    first = mind.process_once("floor")
    assert first["consumed"] == 1
    assert _offset(state, "floor") > 0
    grok_sid = _session_id(state, "floor") if (state / "floor" / "mind" / "session").is_file() else ""
    chat_id = _cursor_session_id(state, "floor")
    assert chat_id == _CURSOR_CHAT_ID
    assert chat_id != grok_sid
    assert not (state / "floor" / "mind" / "session.minted").is_file()
    rows = _argv_log(cursor_log)
    assert [r["argv"] for r in rows][0] == ["create-chat"]
    turn = rows[1]["argv"]
    _assert_cursor_clap(turn, chat_id=chat_id, prompt="cursor first mail")
    assert rows[1]["cwd"] == str(REPO)
    assert rows[1]["GROK_HOME"] is None
    assert rows[1]["has_cursor_api_key"] is True
    assert _argv_log(grok_log) == []
    mail = state / "floor" / "mind" / "mail.txt"
    assert mail.is_file()
    assert "cursor first mail" in mail.read_text(encoding="utf-8")

    _append_inbox(state, "floor", "task-cur-2", "cursor second mail")
    second = mind.process_once("floor")
    assert second["consumed"] == 1
    assert _cursor_session_id(state, "floor") == chat_id
    rows2 = _argv_log(cursor_log)
    assert len(rows2) == 3
    assert rows2[2]["argv"][0:2] != ["create-chat"]
    _assert_cursor_clap(rows2[2]["argv"], chat_id=chat_id, prompt="cursor second mail")
    assert "create-chat" not in rows2[2]["argv"]


def test_grok_402_switches_to_cursor_without_reminting_grok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    grok_log = tmp_path / "grok.argv.json"
    cursor_log = tmp_path / "cursor.argv.json"
    grok = _write_fake_grok(
        tmp_path,
        grok_log,
        rc=1,
        stdout="",
        stderr="Error: HTTP 402 usage balance exhausted",
    )
    cursor = _write_fake_cursor_agent(tmp_path, cursor_log)
    monkeypatch.setenv("CURSOR_API_KEY", "test-cursor-api-key-not-leaked")
    mind, state = _prep_mind(
        tmp_path, monkeypatch, unique="402ok", grok=grok, cursor=cursor
    )
    _append_inbox(state, "floor", "task-402-1", "still do the mail")
    result = mind.process_once("floor")
    assert result["consumed"] == 1
    assert result.get("reason") == "ok"
    assert _offset(state, "floor") > 0
    grok_sid = _session_id(state, "floor")
    uuid.UUID(grok_sid)
    chat_id = _cursor_session_id(state, "floor")
    assert chat_id == _CURSOR_CHAT_ID
    assert chat_id != grok_sid
    assert not (state / "floor" / "mind" / "session.minted").is_file()
    grok_argv = _argv_log(grok_log)[0]["argv"]
    assert "--session-id" in grok_argv
    assert _flag_value(grok_argv, "--session-id") == grok_sid
    cursor_rows = _argv_log(cursor_log)
    assert cursor_rows[0]["argv"] == ["create-chat"]
    _assert_cursor_clap(
        cursor_rows[1]["argv"], chat_id=chat_id, prompt="still do the mail"
    )
    assert grok_sid not in cursor_rows[1]["argv"]
    captured = capsys.readouterr()
    switch_blob = captured.out + captured.err
    assert "MIND_SWITCH" in switch_blob
    assert "MIND_FALLBACK" not in switch_blob
    assert "seat=floor" in switch_blob
    assert "from=grok" in switch_blob
    assert "to=cursor" in switch_blob
    assert "reason=" in switch_blob
    assert _runner_name(state, "floor") == "cursor"
    rows = _transcript_rows(state, "floor")
    assert any(r.get("role") == "assistant" for r in rows)

    _append_inbox(state, "floor", "task-402-2", "second 402 mail")
    again = mind.process_once("floor")
    assert again["consumed"] == 1
    assert _session_id(state, "floor") == grok_sid
    assert _cursor_session_id(state, "floor") == chat_id
    assert _runner_name(state, "floor") == "cursor"
    grok_rows = _argv_log(grok_log)
    assert len(grok_rows) == 1
    cursor_rows2 = _argv_log(cursor_log)
    assert sum(1 for r in cursor_rows2 if r["argv"] == ["create-chat"]) == 1
    _assert_cursor_clap(
        cursor_rows2[-1]["argv"], chat_id=chat_id, prompt="second 402 mail"
    )
    captured2 = capsys.readouterr()
    again_blob = captured2.out + captured2.err
    assert "MIND_SWITCH" not in again_blob


def test_offset_not_advanced_on_402_when_cursor_also_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    grok_log = tmp_path / "grok.argv.json"
    cursor_log = tmp_path / "cursor.argv.json"
    grok = _write_fake_grok(
        tmp_path,
        grok_log,
        rc=2,
        stdout="",
        stderr="HTTP 402: usage balance exhausted",
    )
    cursor = _write_fake_cursor_agent(
        tmp_path, cursor_log, rc=1, stdout="", stderr="cursor boom"
    )
    monkeypatch.setenv("CURSOR_API_KEY", "test-cursor-api-key-not-leaked")
    mind, state = _prep_mind(
        tmp_path, monkeypatch, unique="402fail", grok=grok, cursor=cursor
    )
    _append_inbox(state, "floor", "task-402-fail", "do work")
    result = mind.process_once("floor")
    assert result["consumed"] == 0
    assert result.get("reason") == "runner-fail"
    assert _offset(state, "floor") == 0
    assert _transcript_rows(state, "floor") == []
    grok_sid = _session_id(state, "floor")
    assert not (state / "floor" / "mind" / "session.minted").is_file()
    chat_id = _cursor_session_id(state, "floor")
    assert chat_id == _CURSOR_CHAT_ID
    assert chat_id != grok_sid
    err = capsys.readouterr().err
    assert "MIND_FAIL" in err
    assert "test-cursor-api-key-not-leaked" not in err
    assert _runner_name(state, "floor") == "cursor"


def test_non_402_grok_failure_does_not_call_cursor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    grok_log = tmp_path / "grok.argv.json"
    cursor_log = tmp_path / "cursor.argv.json"
    grok = _write_fake_grok(tmp_path, grok_log, rc=1, stderr="clap: unknown flag")
    cursor = _write_fake_cursor_agent(tmp_path, cursor_log)
    monkeypatch.setenv("CURSOR_API_KEY", "test-cursor-api-key-not-leaked")
    mind, state = _prep_mind(
        tmp_path, monkeypatch, unique="nofallback", grok=grok, cursor=cursor
    )
    _append_inbox(state, "floor", "task-no-fb", "do work")
    result = mind.process_once("floor")
    assert result["consumed"] == 0
    assert result.get("reason") == "runner-fail"
    assert _offset(state, "floor") == 0
    assert _argv_log(cursor_log) == []
    assert not (state / "floor" / "mind" / "cursor-session").is_file()


def test_forced_grok_runner_does_not_switch_on_402(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    grok_log = tmp_path / "grok.argv.json"
    cursor_log = tmp_path / "cursor.argv.json"
    grok = _write_fake_grok(
        tmp_path,
        grok_log,
        rc=1,
        stdout="",
        stderr="HTTP 402 usage balance exhausted",
    )
    cursor = _write_fake_cursor_agent(tmp_path, cursor_log)
    monkeypatch.setenv("CURSOR_API_KEY", "test-cursor-api-key-not-leaked")
    mind, state = _prep_mind(
        tmp_path, monkeypatch, unique="forcedgrok", grok=grok, cursor=cursor
    )
    monkeypatch.setenv("GCS_MIND_RUNNER", "grok")
    _append_inbox(state, "floor", "task-forced-grok", "do work")
    result = mind.process_once("floor")
    assert result["consumed"] == 0
    assert result.get("reason") == "runner-fail"
    assert _offset(state, "floor") == 0
    assert _argv_log(cursor_log) == []
    assert _runner_name(state, "floor") != "cursor"
    captured = capsys.readouterr()
    blob = captured.out + captured.err
    assert "MIND_SWITCH" not in blob


def test_cursor_quota_switches_to_grok_and_retries_same_mail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    grok_log = tmp_path / "grok.argv.json"
    cursor_log = tmp_path / "cursor.argv.json"
    grok = _write_fake_grok(tmp_path, grok_log)
    cursor = _write_fake_cursor_agent(
        tmp_path,
        cursor_log,
        rc=1,
        stdout="",
        stderr="Error: HTTP 402 usage balance exhausted",
    )
    monkeypatch.setenv("CURSOR_API_KEY", "test-cursor-api-key-not-leaked")
    mind, state = _prep_mind(
        tmp_path, monkeypatch, unique="cur402", grok=grok, cursor=cursor
    )
    mind_dir = state / "floor" / "mind"
    mind_dir.mkdir(parents=True)
    (mind_dir / "runner").write_text("cursor\n", encoding="utf-8")
    _append_inbox(state, "floor", "task-cur-402", "switch back to grok")
    result = mind.process_once("floor")
    assert result["consumed"] == 1
    assert result.get("reason") == "ok"
    assert _offset(state, "floor") > 0
    assert _runner_name(state, "floor") == "grok"
    assert _argv_log(cursor_log), "cursor runner must run first"
    grok_rows = _argv_log(grok_log)
    assert len(grok_rows) == 1
    captured = capsys.readouterr()
    blob = captured.out + captured.err
    assert "MIND_SWITCH" in blob
    assert "from=cursor" in blob
    assert "to=grok" in blob

    cursor_n = len(_argv_log(cursor_log))
    _append_inbox(state, "floor", "task-cur-402b", "stay on grok")
    again = mind.process_once("floor")
    assert again["consumed"] == 1
    grok_rows2 = _argv_log(grok_log)
    assert len(grok_rows2) == 2
    captured2 = capsys.readouterr()
    again_blob = captured2.out + captured2.err
    assert "MIND_SWITCH" not in again_blob
    assert len(_argv_log(cursor_log)) == cursor_n


def test_auto_success_persists_grok_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    grok_log = tmp_path / "grok.argv.json"
    cursor_log = tmp_path / "cursor.argv.json"
    grok = _write_fake_grok(tmp_path, grok_log)
    cursor = _write_fake_cursor_agent(tmp_path, cursor_log)
    mind, state = _prep_mind(
        tmp_path, monkeypatch, unique="persistgrok", grok=grok, cursor=cursor
    )
    _append_inbox(state, "floor", "task-auto-1", "first grok mail")
    result = mind.process_once("floor")
    assert result["consumed"] == 1
    assert _runner_name(state, "floor") == "grok"
    assert _argv_log(cursor_log) == []


def test_cursor_runner_sources_agent_env_without_printing_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    grok_log = tmp_path / "grok.argv.json"
    cursor_log = tmp_path / "cursor.argv.json"
    grok = _write_fake_grok(tmp_path, grok_log)
    cursor = _write_fake_cursor_agent(tmp_path, cursor_log)
    env_file = tmp_path / "cursor-agent.env"
    key = "test-cursor-api-key-from-envfile"
    env_file.write_text(f"export CURSOR_API_KEY={key}\n", encoding="utf-8")
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    monkeypatch.setenv("CURSOR_AGENT_ENV", str(env_file))
    mind, state = _prep_mind(
        tmp_path, monkeypatch, unique="agentenv", grok=grok, cursor=cursor
    )
    monkeypatch.setenv("GCS_MIND_RUNNER", "cursor")
    _append_inbox(state, "floor", "task-env-1", "from env file")
    result = mind.process_once("floor")
    assert result["consumed"] == 1
    rows = _argv_log(cursor_log)
    assert rows[1]["has_cursor_api_key"] is True
    captured = capsys.readouterr()
    assert key not in captured.out
    assert key not in captured.err
    transcript = (state / "floor" / "mind" / "transcript.jsonl").read_text(encoding="utf-8")
    assert key not in transcript


def test_none_runner_is_not_mail_consumed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A runner that did not run (None) must not advance offset after hub receipt."""

    def silent(_prompt: str, **_kwargs: object):
        return None

    mind, state = _prep_mind(tmp_path, monkeypatch, unique="nonerunner", runner=silent)
    _append_inbox(state, "floor", "task-none-1", "must not fake success")
    result = mind.process_once("floor")
    assert result["consumed"] == 0
    assert result.get("reason") == "runner-fail"
    assert _offset(state, "floor") == 0
    assert _transcript_rows(state, "floor") == []

