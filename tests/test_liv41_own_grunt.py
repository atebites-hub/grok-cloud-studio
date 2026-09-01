"""LIV-41: director turn without spawning/watching its own grunt is FAIL.

Does not remint GCS #75 (spawn-only / reason=no-spawn / under-floor) or
GCS #91 (watch-only / reason=no-watch). Combined leftover-ACP + mind law:
reason=no-spawn-watch. Unique --name. Refuse twin of RUNNING
gcs-liv59-anti-twin-floor2105. Empty CI is not merge.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[1]
OWN_GRUNT = REPO / "scripts" / "directors" / "director_turn_own_grunt.py"
ACP_INJECT = REPO / "scripts" / "directors" / "acp_inject.py"
MIND_PY = REPO / "scripts" / "directors" / "mind.py"
FOOTER = REPO / "scripts" / "directors" / "common_footer.txt"
CLOUD_DOC = REPO / "docs" / "CLOUD.md"
MIND_DOC = REPO / "docs" / "studio" / "MIND.md"
ARCH_DOC = REPO / "docs" / "ARCHITECTURE.md"
AGENTS_DOC = REPO / "AGENTS.md"
README = REPO / "README.md"
FEATURE = REPO / "tests" / "bdd" / "liv41_own_grunt.feature"
WORKFLOW = REPO / ".github" / "workflows" / "ship-gate.yml"
SHIP_GATE = REPO / "scripts" / "ci" / "ship-gate.sh"
PYTEST_INI = REPO / "pytest.ini"
INSTALL = REPO / "install.sh"
LAUNCH = "scripts/launch-cloud-extra-high.sh"
UNIQUE_NAME = "gcs-liv41-own-grunt-floor2105"
RUNNING_TWIN = "gcs-liv59-anti-twin-floor2105"

DIRECTOR_OWN_MAIL = (
    "A2A_TASK_ID=task-liv41\n"
    "A2A_CONTEXT=ctx-liv41\n"
    "Director-owns-launch wake (inbox → local ACP session/prompt into persistent "
    "grok agent serve — not cloud-agent create). "
    "You MAY use tools. You SHOULD call cloud_launch or "
    f"{LAUNCH} to spawn YOUR Cursor Cloud agent for this MESSAGE.\n"
    "\n"
    "MESSAGE:\n"
    "LAUNCH ONLY\n"
    f'{LAUNCH} --name floor-iac "Director owns Cursor Cloud launch."\n'
)

A2A_REPLY_MAIL = (
    "A2A_REPLY seat=floor task=task-reply-1 context=ctx-1 "
    "RESULT bc-id=none pr=none notes=done"
)
STATUS_PING = "ACP_PING STATUS/CONTINUE"

STATUS_LINE = "STATUS quoting token tick-liv41. Working."
KEEP_ALIVE = "Keep-alive received. Scanning A2A inboxes, fleet ledgers"


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _own() -> ModuleType:
    assert OWN_GRUNT.is_file(), "scripts/directors/director_turn_own_grunt.py"
    return _load(OWN_GRUNT, "gcs_liv41_own_grunt")


def _spawn_tool(command: str, *, title: str = "bash") -> dict[str, Any]:
    return {
        "sessionUpdate": "tool_call",
        "title": title,
        "kind": "execute",
        "rawInput": {"command": command},
    }


def _cloud_launch_tool(name: str, prompt: str = "LIV-41 own grunt. Open a PR.") -> dict[str, Any]:
    return {
        "sessionUpdate": "tool_call",
        "name": "cloud_launch",
        "title": "cloud_launch",
        "arguments": {"name": name, "prompt": prompt},
    }


def _ok_launch_cmd(name: str = UNIQUE_NAME) -> str:
    return f'{LAUNCH} --name {name} "LIV-41 own grunt. Open a PR."'


# --- judge: required / exempt -------------------------------------------------


def test_feature_file_binds_the_fail_example() -> None:
    text = FEATURE.read_text(encoding="utf-8")
    assert "no-spawn-watch" in text
    assert LAUNCH in text
    assert RUNNING_TWIN in text
    assert UNIQUE_NAME in text
    assert "Empty GitHub checks are not merge" in text or "Empty CI is not merge" in text


def test_director_owns_launch_mail_requires_own_grunt() -> None:
    mod = _own()
    assert mod.own_grunt_required(DIRECTOR_OWN_MAIL) is True
    assert mod.own_grunt_exempt(DIRECTOR_OWN_MAIL) is False


def test_a2a_reply_and_fleet_done_are_exempt() -> None:
    mod = _own()
    assert mod.own_grunt_exempt(A2A_REPLY_MAIL) is True
    assert mod.own_grunt_required(A2A_REPLY_MAIL) is False
    assert mod.own_grunt_required("FLEET_DONE / PR_READY: Extra High bc-1") is False
    assert mod.own_grunt_required("PR_READY pr=https://example.invalid/p/1") is False
    assert mod.own_grunt_required(STATUS_PING) is False


def test_status_only_on_director_owns_launch_is_fail() -> None:
    """BDD: a director turn without spawning/watching is FAIL."""
    mod = _own()
    verdict = mod.judge_director_own_grunt(mail=DIRECTOR_OWN_MAIL, assistant=STATUS_LINE)
    assert verdict["fail"] is True
    assert verdict["reason"] == "no-spawn-watch"
    assert verdict.get("detail") == "missing-spawn"


def test_send_sh_or_ticket_on_director_owns_launch_is_fail() -> None:
    mod = _own()
    send = json.dumps(_spawn_tool("scripts/a2a/send.sh ops ping"))
    ticket = json.dumps(_spawn_tool("ticket move PAL-1 done"))
    for blob in (send, ticket):
        verdict = mod.judge_director_own_grunt(mail=DIRECTOR_OWN_MAIL, assistant=blob)
        assert verdict["fail"] is True, blob
        assert verdict["reason"] == "no-spawn-watch"


def test_inspect_of_launcher_is_theatre_not_spawn() -> None:
    mod = _own()
    for cmd in (
        f"ls {LAUNCH}",
        f"cat {LAUNCH}",
        "rg launch-cloud-extra-high scripts/",
    ):
        verdict = mod.judge_director_own_grunt(
            mail=DIRECTOR_OWN_MAIL,
            assistant=json.dumps(_spawn_tool(cmd, title="Shell")),
        )
        assert verdict["fail"] is True, cmd
        assert verdict["reason"] == "no-spawn-watch"
        assert verdict.get("spawned") is False


def test_prose_cloud_launch_ok_without_argv_is_theatre() -> None:
    mod = _own()
    verdict = mod.judge_director_own_grunt(
        mail=DIRECTOR_OWN_MAIL,
        assistant="CLOUD_LAUNCH_OK id=bc-theatre\nCLOUD_WAITER_SPAWNED id=bc-theatre\n",
    )
    assert verdict["fail"] is True
    assert verdict.get("spawned") is False


def test_real_launcher_unique_name_is_spawn_and_watch() -> None:
    mod = _own()
    tool = _spawn_tool(_ok_launch_cmd())
    verdict = mod.judge_director_own_grunt(
        mail=DIRECTOR_OWN_MAIL,
        assistant=json.dumps(tool) + "\nCLOUD_LAUNCH_OK id=bc-own\nCLOUD_WAITER_SPAWNED id=bc-own\n",
        tool_updates=[tool],
    )
    assert verdict["fail"] is False, verdict
    assert verdict["reason"] == "own-grunt"
    assert verdict.get("spawned") is True
    assert verdict.get("watched") is True
    assert verdict.get("name") == UNIQUE_NAME


def test_launcher_invoke_without_skip_counts_as_watch() -> None:
    """The real launch script spawns spawn-waiter.sh unless GCS_SPAWN_WAITER=0."""
    mod = _own()
    tool = _spawn_tool(_ok_launch_cmd())
    verdict = mod.judge_director_own_grunt(
        mail=DIRECTOR_OWN_MAIL,
        assistant=json.dumps(tool),
        tool_updates=[tool],
    )
    assert verdict["fail"] is False, verdict
    assert verdict.get("watched") is True


def test_cloud_launch_plugin_unique_name_is_ok() -> None:
    mod = _own()
    tool = _cloud_launch_tool(UNIQUE_NAME)
    verdict = mod.judge_director_own_grunt(
        mail=DIRECTOR_OWN_MAIL,
        assistant=json.dumps(tool),
        tool_updates=[tool],
    )
    assert verdict["fail"] is False, verdict
    assert verdict.get("spawned") is True
    assert verdict.get("watched") is True


def test_refuse_twin_of_running_liv59_anti_twin() -> None:
    mod = _own()
    assert mod.is_refused_twin_name(RUNNING_TWIN) is True
    assert mod.is_refused_twin_name(f"{RUNNING_TWIN}-copy") is True
    assert mod.is_refused_twin_name(UNIQUE_NAME) is False
    tool = _spawn_tool(_ok_launch_cmd(RUNNING_TWIN))
    verdict = mod.judge_director_own_grunt(
        mail=DIRECTOR_OWN_MAIL,
        assistant=json.dumps(tool),
        tool_updates=[tool],
    )
    assert verdict["fail"] is True
    assert verdict["reason"] == "no-spawn-watch"
    assert verdict.get("detail") == "twin"
    assert verdict.get("spawned") is False


def test_bot_cloudagent_name_is_not_a_spawn() -> None:
    mod = _own()
    for name in ("donald", "orchestrator"):
        tool = _cloud_launch_tool(name)
        verdict = mod.judge_director_own_grunt(
            mail=DIRECTOR_OWN_MAIL,
            assistant=json.dumps(tool),
            tool_updates=[tool],
        )
        assert verdict["fail"] is True, name
        assert verdict.get("detail") == "bot"


def test_waiter_skipped_is_missing_watch() -> None:
    mod = _own()
    cmd = f'GCS_SPAWN_WAITER=0 {LAUNCH} --name {UNIQUE_NAME} "x"'
    tool = _spawn_tool(cmd)
    verdict = mod.judge_director_own_grunt(
        mail=DIRECTOR_OWN_MAIL,
        assistant=json.dumps(tool) + "\nCLOUD_LAUNCH_OK\nCLOUD_WAITER_SKIPPED id=bc-x\n",
        tool_updates=[tool],
    )
    assert verdict["fail"] is True
    assert verdict.get("spawned") is True
    assert verdict.get("watched") is False
    assert verdict.get("detail") == "missing-watch"


def test_blocking_watch_cloud_agent_is_not_watching() -> None:
    mod = _own()
    tools = [
        _spawn_tool(_ok_launch_cmd()),
        _spawn_tool("scripts/cloud/watch-cloud-agent.sh bc-own"),
    ]
    # Waiter skipped, blocking watch instead.
    assistant = (
        json.dumps(tools[0])
        + "\nCLOUD_LAUNCH_OK id=bc-own\nCLOUD_WAITER_SKIPPED id=bc-own\n"
        + json.dumps(tools[1])
    )
    verdict = mod.judge_director_own_grunt(
        mail=DIRECTOR_OWN_MAIL,
        assistant=assistant,
        tool_updates=tools,
    )
    assert verdict["fail"] is True
    assert verdict.get("detail") == "missing-watch"


def test_explicit_spawn_waiter_after_launch_is_watch() -> None:
    mod = _own()
    tools = [
        _spawn_tool(_ok_launch_cmd()),
        _spawn_tool("scripts/cloud/spawn-waiter.sh --id bc-own --name " + UNIQUE_NAME),
    ]
    verdict = mod.judge_director_own_grunt(
        mail=DIRECTOR_OWN_MAIL,
        assistant="\n".join(json.dumps(t) for t in tools),
        tool_updates=tools,
    )
    assert verdict["fail"] is False, verdict
    assert verdict.get("watched") is True


def test_a2a_reply_without_launch_is_not_fail() -> None:
    mod = _own()
    verdict = mod.judge_director_own_grunt(mail=A2A_REPLY_MAIL, assistant=STATUS_LINE)
    assert verdict["fail"] is False
    assert verdict["reason"] == "exempt"


def test_status_ping_without_launch_is_not_required() -> None:
    mod = _own()
    verdict = mod.judge_director_own_grunt(mail=STATUS_PING, assistant=STATUS_LINE)
    assert verdict["fail"] is False
    assert verdict["reason"] == "not-required"


def test_wrap_prompt_prepends_fail_closed_header() -> None:
    mod = _own()
    wrapped = mod.wrap_prompt_if_required(DIRECTOR_OWN_MAIL)
    assert wrapped.startswith("=== LIV-41 OWN-GRUNT")
    assert "no-spawn-watch" in wrapped
    assert UNIQUE_NAME in wrapped
    assert RUNNING_TWIN in wrapped
    assert "grok-4.6" in wrapped
    assert "xhigh" in wrapped
    assert "fast=false" in wrapped
    assert DIRECTOR_OWN_MAIL in wrapped
    assert mod.wrap_prompt_if_required(STATUS_PING) == STATUS_PING


def test_docs_and_footer_state_the_fail_law() -> None:
    footer = FOOTER.read_text(encoding="utf-8")
    cloud = CLOUD_DOC.read_text(encoding="utf-8")
    mind = MIND_DOC.read_text(encoding="utf-8")
    arch = ARCH_DOC.read_text(encoding="utf-8")
    for blob in (footer, cloud, mind, arch):
        assert "no-spawn-watch" in blob or "without spawning/watching" in blob.lower()
        assert LAUNCH in blob
        assert "gcs-liv59-anti-twin-floor2105" in blob or "unique --name" in blob.lower()
    assert "Empty" in (AGENTS_DOC.read_text(encoding="utf-8") + README.read_text(encoding="utf-8"))
    agents = AGENTS_DOC.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    assert "ship-gate" in agents.lower() or "pytest -q and secret_scan" in agents
    assert "ship-gate" in readme.lower() or "pytest -q and secret_scan" in readme


# --- leftover ACP inject ------------------------------------------------------


sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_acp_inject as acp_t  # noqa: E402


def test_acp_inject_director_owns_launch_status_only_is_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    mod = acp_t._load(ACP_INJECT, "gcs_acp_liv41_status_fail")
    acp_t._prep_seat(mod, tmp_path, monkeypatch)
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: None)
    ws = acp_t.FakeAcpWs(prompt_chunks=[f"{STATUS_LINE}\n"])
    acp_t._patch_connect(mod, ws, monkeypatch)
    rc = asyncio.run(
        mod.inject("floor", DIRECTOR_OWN_MAIL, timeout=2.0, pin_session=True)
    )
    out = capsys.readouterr()
    blob = out.out + out.err
    assert rc != 0, blob
    assert "ACP_INJECT_FAIL" in blob
    assert "reason=no-spawn-watch" in blob
    assert "ACP_INJECT_OK" not in out.out


def test_acp_inject_director_owns_launch_ticket_is_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    mod = acp_t._load(ACP_INJECT, "gcs_acp_liv41_ticket_fail")
    acp_t._prep_seat(mod, tmp_path, monkeypatch)
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: None)
    ws = acp_t.FakeAcpWs(
        prompt_chunks=[KEEP_ALIVE],
        prompt_updates=[
            acp_t._tool_update("tc-move", "bash", command="ticket move PAL-1 done"),
        ],
    )
    acp_t._patch_connect(mod, ws, monkeypatch)
    rc = asyncio.run(
        mod.inject("floor", DIRECTOR_OWN_MAIL, timeout=2.0, pin_session=True)
    )
    out = capsys.readouterr()
    blob = out.out + out.err
    assert rc != 0, blob
    assert "ACP_INJECT_FAIL" in blob
    assert "reason=no-spawn-watch" in blob


def test_acp_inject_director_owns_launch_real_launcher_is_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    mod = acp_t._load(ACP_INJECT, "gcs_acp_liv41_launch_ok")
    acp_t._prep_seat(mod, tmp_path, monkeypatch)
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: None)
    ws = acp_t.FakeAcpWs(
        prompt_chunks=[KEEP_ALIVE, "\nCLOUD_LAUNCH_OK id=bc-own\n"],
        prompt_updates=[
            acp_t._tool_update("tc-launch", "bash", command=_ok_launch_cmd()),
        ],
    )
    acp_t._patch_connect(mod, ws, monkeypatch)
    rc = asyncio.run(
        mod.inject("floor", DIRECTOR_OWN_MAIL, timeout=2.0, pin_session=True)
    )
    out = capsys.readouterr()
    blob = out.out + out.err
    assert rc == 0, blob
    assert "ACP_INJECT_OK" in out.out
    assert "ACP_INJECT_FAIL" not in blob
    acp_t._assert_handoff_reason(blob, "work")


def test_acp_inject_status_ping_ticket_still_handoff_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Keep-alive STATUS/CONTINUE + ticket move stays HANDOFF reason=work."""
    mod = acp_t._load(ACP_INJECT, "gcs_acp_liv41_status_ping_ok")
    acp_t._prep_seat(mod, tmp_path, monkeypatch)
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: None)
    ws = acp_t.FakeAcpWs(
        prompt_chunks=[KEEP_ALIVE],
        prompt_updates=[
            acp_t._tool_update("tc-move", "bash", command="ticket move PAL-1 done"),
        ],
    )
    acp_t._patch_connect(mod, ws, monkeypatch)
    rc = asyncio.run(mod.inject("floor", STATUS_PING, timeout=2.0, pin_session=True))
    out = capsys.readouterr()
    blob = out.out + out.err
    assert rc == 0, blob
    assert "ACP_INJECT_OK" in out.out
    acp_t._assert_handoff_reason(blob, "work")


def test_acp_inject_refuses_running_liv59_twin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    mod = acp_t._load(ACP_INJECT, "gcs_acp_liv41_twin_fail")
    acp_t._prep_seat(mod, tmp_path, monkeypatch)
    monkeypatch.setattr(mod, "_duplex_after_inject", lambda *a, **k: None)
    ws = acp_t.FakeAcpWs(
        prompt_chunks=[KEEP_ALIVE],
        prompt_updates=[
            acp_t._tool_update(
                "tc-twin",
                "bash",
                command=_ok_launch_cmd(RUNNING_TWIN),
            ),
        ],
    )
    acp_t._patch_connect(mod, ws, monkeypatch)
    rc = asyncio.run(
        mod.inject("floor", DIRECTOR_OWN_MAIL, timeout=2.0, pin_session=True)
    )
    out = capsys.readouterr()
    blob = out.out + out.err
    assert rc != 0, blob
    assert "ACP_INJECT_FAIL" in blob
    assert "reason=no-spawn-watch" in blob


# --- mind process_once --------------------------------------------------------


def _append_inbox(state: Path, seat: str, task_id: str, text: str) -> None:
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
    runner: Any,
) -> tuple[ModuleType, Path]:
    mind = _load(MIND_PY, f"gcs_mind_liv41_{unique}")
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


def test_process_once_director_owns_launch_without_spawn_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[str] = []

    def runner(prompt: str, *, seat: str = "") -> dict[str, Any]:
        del seat
        seen.append(prompt)
        return {"text": STATUS_LINE, "returncode": 0, "stderr": ""}

    mind, state = _prep_mind(tmp_path, monkeypatch, unique="nospawn", runner=runner)
    _append_inbox(state, "floor", "task-liv41-1", DIRECTOR_OWN_MAIL)
    result = mind.process_once("floor")
    assert result.get("consumed") == 0
    assert result.get("reason") == "no-spawn-watch"
    assert _offset(state, "floor") == 0
    err = capsys.readouterr().err
    assert "MIND_FAIL" in err
    assert "reason=no-spawn-watch" in err
    assert seen
    assert seen[0].startswith("=== LIV-41 OWN-GRUNT")


def test_process_once_director_owns_launch_with_launcher_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = _spawn_tool(_ok_launch_cmd())

    def runner(prompt: str, *, seat: str = "") -> dict[str, Any]:
        del prompt, seat
        return {"text": json.dumps(tool) + "\nCLOUD_LAUNCH_OK id=bc-own\n", "returncode": 0}

    mind, state = _prep_mind(tmp_path, monkeypatch, unique="spawnok", runner=runner)
    _append_inbox(state, "floor", "task-liv41-2", DIRECTOR_OWN_MAIL)
    result = mind.process_once("floor")
    assert result.get("consumed") == 1
    assert result.get("reason") == "ok"
    assert _offset(state, "floor") > 0


def test_process_once_ordinary_mail_still_advances(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def runner(prompt: str, *, seat: str = "") -> dict[str, Any]:
        del prompt, seat
        return {"text": "pong from floor", "returncode": 0}

    mind, state = _prep_mind(tmp_path, monkeypatch, unique="ordinary", runner=runner)
    _append_inbox(state, "floor", "task-ping", "ping from ops")
    result = mind.process_once("floor")
    assert result.get("consumed") == 1
    assert result.get("reason") == "ok"


# --- empty CI is not merge ----------------------------------------------------


def test_ship_gate_workflow_exists_and_is_not_empty() -> None:
    assert WORKFLOW.is_file(), "empty GitHub checks are not merge"
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "pytest -q and secret_scan" in text
    assert "scripts/ci/ship-gate.sh" in text
    assert "pull_request" in text
    assert "submodules: true" in text
    assert "fetch-depth: 0" in text
    assert "continue-on-error" not in text
    assert "GCS_BOT_BIND_OPTIONAL" in text


def test_ship_gate_script_requires_n_passed_and_secret_scan_clean() -> None:
    assert SHIP_GATE.is_file()
    text = SHIP_GATE.read_text(encoding="utf-8")
    assert ".venv/bin/pytest -q" in text
    assert "secret_scan.py" in text
    assert "secret_scan=clean" in text
    assert "[1-9][0-9]* passed" in text or "passed" in text
    mode = SHIP_GATE.stat().st_mode
    assert stat.S_ISREG(mode)
    install = INSTALL.read_text(encoding="utf-8")
    assert "scripts/ci" in install


def test_pytest_ini_does_not_double_quiet() -> None:
    """pytest 9 treats CLI -q plus addopts=-q as -qq and hides N passed."""
    text = PYTEST_INI.read_text(encoding="utf-8")
    active = [
        ln.strip()
        for ln in text.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    assert not any(ln.startswith("addopts") and "-q" in ln for ln in active)


def test_ship_gate_script_ok_on_fake_tree(tmp_path: Path) -> None:
    pytest_bin = tmp_path / ".venv" / "bin" / "pytest"
    pytest_bin.parent.mkdir(parents=True)
    pytest_bin.write_text(
        "#!/bin/sh\necho '23 passed in 1.00s'\nexit 0\n",
        encoding="utf-8",
    )
    pytest_bin.chmod(pytest_bin.stat().st_mode | stat.S_IEXEC)
    scan = tmp_path / "scripts" / "secret_scan.py"
    scan.parent.mkdir(parents=True)
    scan.write_text(
        "#!/usr/bin/env python3\nprint('secret_scan=clean')\n",
        encoding="utf-8",
    )
    dest = tmp_path / "scripts" / "ci" / "ship-gate.sh"
    dest.parent.mkdir(parents=True)
    dest.write_text(SHIP_GATE.read_text(encoding="utf-8"), encoding="utf-8")
    dest.chmod(dest.stat().st_mode | stat.S_IEXEC)
    proc = subprocess.run(
        ["bash", str(dest)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=10,
        env={**os.environ, "GCS_ROOT": str(tmp_path)},
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "ship-gate: OK" in blob
    assert "secret_scan=clean" in blob


def test_ship_gate_fails_when_pytest_hides_n_passed(tmp_path: Path) -> None:
    pytest_bin = tmp_path / ".venv" / "bin" / "pytest"
    pytest_bin.parent.mkdir(parents=True)
    pytest_bin.write_text("#!/bin/sh\necho quiet\nexit 0\n", encoding="utf-8")
    pytest_bin.chmod(pytest_bin.stat().st_mode | stat.S_IEXEC)
    scan = tmp_path / "scripts" / "secret_scan.py"
    scan.parent.mkdir(parents=True)
    scan.write_text("print('secret_scan=clean')\n", encoding="utf-8")
    dest = tmp_path / "scripts" / "ci" / "ship-gate.sh"
    dest.parent.mkdir(parents=True)
    dest.write_text(SHIP_GATE.read_text(encoding="utf-8"), encoding="utf-8")
    dest.chmod(dest.stat().st_mode | stat.S_IEXEC)
    proc = subprocess.run(
        ["bash", str(dest)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=10,
        env={**os.environ, "GCS_ROOT": str(tmp_path)},
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode != 0, blob
    assert "no passing tests" in blob.lower() or "passed" in blob.lower()
