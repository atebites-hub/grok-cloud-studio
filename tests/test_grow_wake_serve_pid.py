"""Remaining GROW wake slice: session/prompt only if daemon.pid owns ACP listen.

#103 FAT already proves inbox → session/prompt on a matching serve pid.
This file covers the leftover mismatch: a live unrelated daemon.pid plus a
TCP-open acp.url owned by someone else is NOT healthy. Wake remints serve
and session/prompts the new pid. Never grok --resume. Never Bot CloudAgent.
Never vendor Hermes. Fake ACP WebSocket only — no live grok CLI, no secrets.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

import test_grow_wake_fat as fat

REPO = Path(__file__).resolve().parents[1]
WAKE_PY = REPO / "scripts" / "a2a" / "wake-daemon.py"
WAKE_LOOP = REPO / "scripts" / "directors" / "seat-wake-loop.sh"
SEAT_COMMON = REPO / "scripts" / "directors" / "seat-daemon-common.sh"
A2A_DOC = REPO / "docs" / "A2A.md"
AGENTS_DOC = REPO / "AGENTS.md"
FEATURE = REPO / "tests" / "features" / "grow_wake_serve_pid_owns_listen.feature"
FAT_TOKEN = "FAT_WAKE_OWN_LISTEN_7c2e"
PINNED_SESSION = "sess-pinned-grow-owns"


def _kill(pid: int) -> None:
    if pid <= 0:
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    try:
        os.waitpid(pid, os.WNOHANG)
    except OSError:
        pass


def test_owns_listen_gherkin_forbids_resume_and_names_serve_pid() -> None:
    assert FEATURE.is_file()
    text = FEATURE.read_text(encoding="utf-8")
    fold = " ".join(text.lower().split())
    assert "daemon.pid" in fold
    assert "session/prompt" in text
    assert "grok --resume" in text
    assert "owns" in fold or "own the acp listen" in fold
    assert "hermes" in fold
    assert "bot cloudagent" in fold
    assert "#103" in text


def test_serve_pid_owns_acp_port_true_for_listener_false_for_unrelated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wake = fat._load(WAKE_PY, "gcs_wake_owns_unit")
    assert hasattr(wake, "serve_pid_owns_acp_port")
    leftover = subprocess.Popen(
        ["sleep", "60"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        with fat._fake_acp(tmp_path / "owns") as acp:
            assert wake.serve_pid_owns_acp_port(int(acp["pid"]), int(acp["port"])) is True
            assert wake.serve_pid_owns_acp_port(int(leftover.pid), int(acp["port"])) is False
            assert wake.serve_pid_owns_acp_port(0, int(acp["port"])) is False
            assert wake.serve_pid_owns_acp_port(int(acp["pid"]), 0) is False
    finally:
        leftover.kill()
        leftover.wait(timeout=3)


def test_serve_healthy_false_when_daemon_pid_does_not_own_listen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    grok_log = fat._install_fake_grok(tmp_path, monkeypatch)
    forbidden, stamp = fat._forbidden_start_daemon(tmp_path)
    leftover = subprocess.Popen(
        ["sleep", "60"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        with fat._fake_acp(tmp_path / "mismatch") as acp:
            wake, state = fat._prep_wake(
                tmp_path,
                monkeypatch,
                unique="owns_mismatch",
                start_daemon=forbidden,
                prompt_sh=fat._prompt_wrapper(tmp_path),
            )
            fat._write_healthy_seat(
                state,
                "floor",
                pid=int(leftover.pid),
                port=int(acp["port"]),
                session=PINNED_SESSION,
            )
            assert wake.serve_healthy("floor") is False
            assert not stamp.is_file()
            grok_rows = json.loads(grok_log.read_text(encoding="utf-8"))
            assert grok_rows == []
    finally:
        leftover.kill()
        leftover.wait(timeout=3)


def test_mismatch_remints_serve_and_session_prompts_new_pid_never_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    grok_log = fat._install_fake_grok(tmp_path, monkeypatch)
    start_log = tmp_path / "start-daemon-owns.log"
    start_sh = fat._start_daemon_script(tmp_path, log=start_log, session=PINNED_SESSION)
    prompt_sh = fat._prompt_wrapper(tmp_path)
    leftover = subprocess.Popen(
        ["sleep", "60"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        with fat._fake_acp(tmp_path / "leftover-listen") as leftover_acp:
            wake, state = fat._prep_wake(
                tmp_path,
                monkeypatch,
                unique="owns_remint",
                start_daemon=start_sh,
                prompt_sh=prompt_sh,
            )
            fat._write_healthy_seat(
                state,
                "ops",
                pid=int(leftover.pid),
                port=int(leftover_acp["port"]),
                session=PINNED_SESSION,
            )
            fat._append_inbox(
                state,
                "ops",
                "task-owns-1",
                f"TASK_ASSIGN: {FAT_TOKEN} after pid-owns-listen remint. Open a PR.",
            )
            assert wake.serve_healthy("ops") is False
            result = wake.process_once("ops")
            assert result["consumed"] == 1, result
            assert start_log.is_file()
            assert "ops" in start_log.read_text(encoding="utf-8")
            sd = state / "ops"
            new_pid = int((sd / "daemon.pid").read_text(encoding="utf-8").strip())
            assert result["serve_pid"] == new_pid
            assert new_pid > 0
            assert new_pid != int(leftover.pid)
            assert new_pid != int(leftover_acp["pid"])
            leftover_journal = fat._journal(leftover_acp["journal"])
            assert "session/prompt" not in leftover_journal.get("methods", [])
            journal = fat._journal(sd / "fake-acp.json")
            assert "session/prompt" in journal["methods"], journal
            assert any(FAT_TOKEN in p for p in journal["prompts"]), journal["prompts"]
            assert journal["pid"] == new_pid
            grok_rows = json.loads(grok_log.read_text(encoding="utf-8"))
            for row in grok_rows:
                assert "--resume" not in row.get("argv", []), row
            assert result["acp_session"] == PINNED_SESSION
            child = subprocess.run(
                ["kill", "-0", str(new_pid)],
                capture_output=True,
                timeout=5,
                check=False,
            )
            if child.returncode == 0:
                _kill(new_pid)
    finally:
        leftover.kill()
        leftover.wait(timeout=3)


def test_owns_listen_cli_and_bash_daemon_healthy_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    common = SEAT_COMMON.read_text(encoding="utf-8")
    assert "wake-daemon.py" in common
    assert "--owns-listen" in common
    loop = WAKE_LOOP.read_text(encoding="utf-8")
    assert "ensure_seat_serve" in loop
    assert "wake-daemon.py" in loop
    leftover = subprocess.Popen(
        ["sleep", "60"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        with fat._fake_acp(tmp_path / "cli") as acp:
            env = {
                **os.environ,
                "GCS_ROOT": str(REPO),
                "GCS_A2A_STATE": str(tmp_path / "a2a-state"),
                "LC_ALL": "C",
            }
            ok = subprocess.run(
                [
                    sys.executable,
                    str(WAKE_PY),
                    "--owns-listen",
                    str(acp["pid"]),
                    str(acp["port"]),
                ],
                cwd=str(REPO),
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert ok.returncode == 0, ok.stdout + ok.stderr
            assert "WAKE_OWNS_LISTEN" in ok.stdout
            bad = subprocess.run(
                [
                    sys.executable,
                    str(WAKE_PY),
                    "--owns-listen",
                    str(leftover.pid),
                    str(acp["port"]),
                ],
                cwd=str(REPO),
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert bad.returncode == 1, bad.stdout + bad.stderr
    finally:
        leftover.kill()
        leftover.wait(timeout=3)


def test_owns_listen_docs_and_source_never_resume_hermes_or_bot() -> None:
    wake_src = WAKE_PY.read_text(encoding="utf-8")
    common = SEAT_COMMON.read_text(encoding="utf-8")
    assert "serve_pid_owns_acp_port" in wake_src
    assert "serve_healthy" in wake_src
    assert '"--resume"' not in wake_src
    assert "'--resume'" not in wake_src
    assert "--owns-listen" in common
    a2a = A2A_DOC.read_text(encoding="utf-8")
    agents = AGENTS_DOC.read_text(encoding="utf-8")
    blob = a2a + "\n" + agents
    fold = blob.lower()
    assert "session/prompt" in blob
    assert "never `grok --resume`" in blob or "never grok --resume" in fold
    assert "listen" in fold and "daemon.pid" in fold
    assert "Do not launch Bot CloudAgent" in a2a
    hermes = REPO / "vendor" / "hermes-agent"
    assert not hermes.exists()
    assert not (REPO / "vendor" / "hermes").exists()
