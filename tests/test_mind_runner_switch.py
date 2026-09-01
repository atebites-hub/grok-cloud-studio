"""FAT: persist mind/runner and one-shot SWITCH on HTTP 402.

Executable binding for tests/features/mind_runner_switch.feature.

Default GCS_MIND_RUNNER=auto persists $GCS_A2A_STATE/<seat>/mind/runner
(grok|cursor). On quota / HTTP 402, flip and retry that same mail line
once (MIND_SWITCH). Forced grok|cursor does not flip. Never Bot
CloudAgent. Do not vendor Hermes. Do not clone LIV-85 mail.txt PRs.

BDD: demonstrate, don't theatre. No LGTM without evidence.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import test_mind as tm

REPO = tm.REPO
FEATURE = REPO / "tests" / "features" / "mind_runner_switch.feature"
ENV_EXAMPLE = REPO / ".env.example"
LAUNCHER = REPO / "scripts" / "launch-cloud-extra-high.sh"
MIND_PY = tm.MIND_PY
MIND_DOC = tm.MIND_DOC
AGENTS_DOC = tm.AGENTS_DOC
PRIVATE_GAME = "atebites-hub/" + "palemon"
LIV85_MAIL_MARKERS = (
    "mail.in-flight",
    "write_seat_mail",
    "TASK_STATE_SUBMITTED",
)
HERMES_MARKERS = (
    "NousResearch/hermes-agent",
    "hermes-agent/",
    "plugin.yaml",
)


def test_mind_runner_switch_feature_file_is_the_living_spec() -> None:
    text = FEATURE.read_text(encoding="utf-8")
    fold = " ".join(text.lower().split())
    assert FEATURE.is_file()
    assert "GCS_MIND_RUNNER=auto" in text
    assert "mind/runner" in text
    assert "MIND_SWITCH" in text
    assert "HTTP 402" in text
    assert "does not flip" in fold or "do not flip" in fold
    assert "same mail line" in fold
    assert "fast=false" in fold
    assert "grok-4.6" in text
    assert "xhigh" in text
    assert "bot cloudagent" in fold
    assert "hermes" in fold
    assert "liv-85" in fold
    assert "mail.txt" in fold
    assert PRIVATE_GAME not in text
    assert text.count("Scenario:") >= 5


def test_env_example_documents_auto_mind_runner() -> None:
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "GCS_MIND_RUNNER" in text
    assert "GCS_MIND_RUNNER=auto" in text
    assert "mind/runner" in text or "MIND_SWITCH" in text or "quota" in text.lower()
    assigned = [
        line
        for line in text.splitlines()
        if line.strip().startswith("CURSOR_API_KEY=")
    ]
    assert assigned == []
    assert PRIVATE_GAME not in text


def _bot_cloudagent_is_prohibition(text: str) -> bool:
    """True when Bot CloudAgent is absent or only as a never/do-not law."""
    fold = text.lower()
    if "bot cloudagent" not in fold:
        return True
    if "launch bot cloudagent" in fold:
        return False
    return "never" in fold or "do not" in fold or "don't" in fold


def test_docs_and_source_keep_switch_law() -> None:
    src = MIND_PY.read_text(encoding="utf-8")
    doc = MIND_DOC.read_text(encoding="utf-8")
    agents = AGENTS_DOC.read_text(encoding="utf-8")
    for blob in (src, doc, agents):
        assert "GCS_MIND_RUNNER" in blob
        assert "MIND_SWITCH" in blob
        assert "mind/runner" in blob
        assert _bot_cloudagent_is_prohibition(blob)
        assert PRIVATE_GAME not in blob
    assert "MIND_FALLBACK" not in src
    for marker in LIV85_MAIL_MARKERS:
        assert marker not in src
    assert "fast=false" in doc
    launcher = LAUNCHER.read_text(encoding="utf-8")
    assert "fast=false" in launcher
    assert "grok-4.6" in launcher
    assert "xhigh" in launcher


def test_tree_does_not_vendor_hermes() -> None:
    src = MIND_PY.read_text(encoding="utf-8")
    feature = FEATURE.read_text(encoding="utf-8")
    assert "vendor/hermes" not in src
    assert "NousResearch" not in src
    gitmodules = (REPO / ".gitmodules").read_text(encoding="utf-8")
    assert "hermes-agent" not in gitmodules
    hermes_dirs = list(REPO.glob("**/hermes-agent"))
    assert hermes_dirs == []
    for marker in HERMES_MARKERS:
        assert marker not in src
    assert "do not vendor" in feature.lower() or "does not vendor" in feature.lower()


def test_explicit_auto_persists_grok_runner_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    grok_log = tmp_path / "grok.argv.json"
    cursor_log = tmp_path / "cursor.argv.json"
    grok = tm._write_fake_grok(tmp_path, grok_log)
    cursor = tm._write_fake_cursor_agent(tmp_path, cursor_log)
    mind, state = tm._prep_mind(
        tmp_path, monkeypatch, unique="autoexplicit", grok=grok, cursor=cursor
    )
    monkeypatch.setenv("GCS_MIND_RUNNER", "auto")
    tm._append_inbox(state, "floor", "task-auto-path", "first grok mail")
    result = mind.process_once("floor")
    assert result["consumed"] == 1
    runner_path = state / "floor" / "mind" / "runner"
    assert runner_path == mind.mind_runner_file("floor")
    assert runner_path.read_text(encoding="utf-8").strip() == "grok"
    assert tm._argv_log(cursor_log) == []
    argv = tm._argv_log(grok_log)[0]["argv"]
    assert "--model" in argv
    assert tm._flag_value(argv, "--model") == tm.GROK_MIND_MODEL
    assert tm._flag_value(argv, "--reasoning-effort") == tm.GROK_MIND_REASONING_EFFORT

    tm._append_inbox(state, "floor", "task-auto-path-2", "second grok mail")
    again = mind.process_once("floor")
    assert again["consumed"] == 1
    assert tm._runner_name(state, "floor") == "grok"
    assert len(tm._argv_log(grok_log)) == 2
    assert tm._argv_log(cursor_log) == []
    grok_sid = tm._session_id(state, "floor")
    later = tm._argv_log(grok_log)[1]["argv"]
    assert "--resume" in later
    assert tm._flag_value(later, "--resume") == grok_sid


def test_garbage_env_and_runner_file_start_as_grok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    grok_log = tmp_path / "grok.argv.json"
    cursor_log = tmp_path / "cursor.argv.json"
    grok = tm._write_fake_grok(tmp_path, grok_log)
    cursor = tm._write_fake_cursor_agent(tmp_path, cursor_log)
    mind, state = tm._prep_mind(
        tmp_path, monkeypatch, unique="garbage", grok=grok, cursor=cursor
    )
    monkeypatch.setenv("GCS_MIND_RUNNER", "llama")
    assert mind.mind_runner_mode() == "auto"
    mind_dir = state / "floor" / "mind"
    mind_dir.mkdir(parents=True)
    (mind_dir / "runner").write_text("not-a-runner\n", encoding="utf-8")
    tm._append_inbox(state, "floor", "task-garbage", "use grok")
    result = mind.process_once("floor")
    assert result["consumed"] == 1
    assert tm._runner_name(state, "floor") == "grok"
    assert tm._argv_log(cursor_log) == []


def test_after_switch_later_mail_does_not_probe_grok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    grok_log = tmp_path / "grok.argv.json"
    cursor_log = tmp_path / "cursor.argv.json"
    grok = tm._write_fake_grok(
        tmp_path,
        grok_log,
        rc=1,
        stdout="",
        stderr="Error: HTTP 402 usage balance exhausted",
    )
    cursor = tm._write_fake_cursor_agent(tmp_path, cursor_log)
    monkeypatch.setenv("CURSOR_API_KEY", "test-cursor-api-key-not-leaked")
    mind, state = tm._prep_mind(
        tmp_path, monkeypatch, unique="noprobe", grok=grok, cursor=cursor
    )
    tm._append_inbox(state, "floor", "task-switch-1", "first mail after 402")
    first = mind.process_once("floor")
    assert first["consumed"] == 1
    assert tm._runner_name(state, "floor") == "cursor"
    grok_sid = tm._session_id(state, "floor")
    chat_id = tm._cursor_session_id(state, "floor")
    captured = capsys.readouterr()
    assert "MIND_SWITCH" in captured.out + captured.err
    assert len(tm._argv_log(grok_log)) == 1

    tm._append_inbox(state, "floor", "task-switch-2", "stay on cursor")
    second = mind.process_once("floor")
    assert second["consumed"] == 1
    assert tm._session_id(state, "floor") == grok_sid
    assert tm._cursor_session_id(state, "floor") == chat_id
    assert tm._runner_name(state, "floor") == "cursor"
    assert len(tm._argv_log(grok_log)) == 1
    cursor_rows = tm._argv_log(cursor_log)
    assert sum(1 for r in cursor_rows if r["argv"] == ["create-chat"]) == 1
    tm._assert_cursor_clap(cursor_rows[-1]["argv"], chat_id=chat_id, prompt="stay on cursor")
    captured2 = capsys.readouterr()
    assert "MIND_SWITCH" not in captured2.out + captured2.err


def test_forced_cursor_does_not_switch_or_rewrite_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    grok_log = tmp_path / "grok.argv.json"
    cursor_log = tmp_path / "cursor.argv.json"
    grok = tm._write_fake_grok(tmp_path, grok_log)
    cursor = tm._write_fake_cursor_agent(
        tmp_path,
        cursor_log,
        rc=1,
        stdout="",
        stderr="HTTP 402 usage balance exhausted",
    )
    monkeypatch.setenv("CURSOR_API_KEY", "test-cursor-api-key-not-leaked")
    mind, state = tm._prep_mind(
        tmp_path, monkeypatch, unique="forcedcur", grok=grok, cursor=cursor
    )
    mind_dir = state / "floor" / "mind"
    mind_dir.mkdir(parents=True)
    (mind_dir / "runner").write_text("grok\n", encoding="utf-8")
    monkeypatch.setenv("GCS_MIND_RUNNER", "cursor")
    tm._append_inbox(state, "floor", "task-forced-cur", "stay cursor")
    result = mind.process_once("floor")
    assert result["consumed"] == 0
    assert result.get("reason") == "runner-fail"
    assert tm._offset(state, "floor") == 0
    assert tm._argv_log(grok_log) == []
    assert tm._runner_name(state, "floor") == "grok"
    captured = capsys.readouterr()
    assert "MIND_SWITCH" not in captured.out + captured.err


def test_forced_grok_with_disk_cursor_does_not_rewrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    grok_log = tmp_path / "grok.argv.json"
    cursor_log = tmp_path / "cursor.argv.json"
    grok = tm._write_fake_grok(
        tmp_path,
        grok_log,
        rc=1,
        stdout="",
        stderr="HTTP 402 usage balance exhausted",
    )
    cursor = tm._write_fake_cursor_agent(tmp_path, cursor_log)
    monkeypatch.setenv("CURSOR_API_KEY", "test-cursor-api-key-not-leaked")
    mind, state = tm._prep_mind(
        tmp_path, monkeypatch, unique="forceddisk", grok=grok, cursor=cursor
    )
    mind_dir = state / "floor" / "mind"
    mind_dir.mkdir(parents=True)
    (mind_dir / "runner").write_text("cursor\n", encoding="utf-8")
    monkeypatch.setenv("GCS_MIND_RUNNER", "grok")
    tm._append_inbox(state, "floor", "task-forced-disk", "stay grok")
    result = mind.process_once("floor")
    assert result["consumed"] == 0
    assert tm._offset(state, "floor") == 0
    assert tm._argv_log(cursor_log) == []
    assert tm._runner_name(state, "floor") == "cursor"
    captured = capsys.readouterr()
    assert "MIND_SWITCH" not in captured.out + captured.err


def test_both_402_switches_once_no_ping_pong(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    grok_log = tmp_path / "grok.argv.json"
    cursor_log = tmp_path / "cursor.argv.json"
    grok = tm._write_fake_grok(
        tmp_path,
        grok_log,
        rc=1,
        stdout="HTTP 402",
        stderr="usage balance exhausted",
    )
    cursor = tm._write_fake_cursor_agent(
        tmp_path,
        cursor_log,
        rc=1,
        stdout="",
        stderr="Error: HTTP 402 usage balance exhausted",
    )
    monkeypatch.setenv("CURSOR_API_KEY", "test-cursor-api-key-not-leaked")
    mind, state = tm._prep_mind(
        tmp_path, monkeypatch, unique="both402", grok=grok, cursor=cursor
    )
    tm._append_inbox(state, "floor", "task-both-402", "same mail line")
    result = mind.process_once("floor")
    assert result["consumed"] == 0
    assert result.get("reason") == "runner-fail"
    assert tm._offset(state, "floor") == 0
    assert len(tm._argv_log(grok_log)) == 1
    cursor_rows = tm._argv_log(cursor_log)
    assert cursor_rows, "cursor runner must run once after MIND_SWITCH"
    assert sum(1 for r in cursor_rows if r["argv"] == ["create-chat"]) == 1
    captured = capsys.readouterr()
    blob = captured.out + captured.err
    assert blob.count("MIND_SWITCH") == 1
    assert "from=grok" in blob
    assert "to=cursor" in blob
    assert "reason=quota-exhausted" in blob
    assert tm._runner_name(state, "floor") == "cursor"
    grok_sid = tm._session_id(state, "floor")
    assert grok_sid not in cursor_rows[-1]["argv"]
    assert "--model" in cursor_rows[-1]["argv"]
    assert tm._flag_value(cursor_rows[-1]["argv"], "--model") == tm.CURSOR_MIND_MODEL


def test_402_in_stdout_only_still_switches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    grok_log = tmp_path / "grok.argv.json"
    cursor_log = tmp_path / "cursor.argv.json"
    grok = tm._write_fake_grok(
        tmp_path,
        grok_log,
        rc=1,
        stdout="quota: HTTP 402",
        stderr="",
    )
    cursor = tm._write_fake_cursor_agent(tmp_path, cursor_log)
    monkeypatch.setenv("CURSOR_API_KEY", "test-cursor-api-key-not-leaked")
    mind, state = tm._prep_mind(
        tmp_path, monkeypatch, unique="stdout402", grok=grok, cursor=cursor
    )
    tm._append_inbox(state, "floor", "task-stdout-402", "retry this mail")
    result = mind.process_once("floor")
    assert result["consumed"] == 1
    assert tm._runner_name(state, "floor") == "cursor"
    captured = capsys.readouterr()
    assert "MIND_SWITCH" in captured.out + captured.err
    grok_sid = tm._session_id(state, "floor")
    chat_id = tm._cursor_session_id(state, "floor")
    assert chat_id != grok_sid
    tm._assert_cursor_clap(
        tm._argv_log(cursor_log)[-1]["argv"],
        chat_id=chat_id,
        prompt="retry this mail",
    )
