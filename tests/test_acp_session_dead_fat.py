"""FAT: leftover ACP dead pin-session. 3 no-start nacks → one session/new.

Distinct from leftover ACP wake inbox→session/prompt (#103 MERGED).
Distinct from LIV-85 hub COMPLETE / mail.txt clones.
Never grok --resume. Never Bot CloudAgent. Never vendor Hermes.
Fake ACP WebSocket serve only — no live grok CLI, no secrets.
"""
from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[1]
WAKE_PY = REPO / "scripts" / "a2a" / "wake-daemon.py"
SEAT_PROMPT = REPO / "scripts" / "directors" / "seat-prompt-acp.sh"
ACP_INJECT = REPO / "scripts" / "directors" / "acp_inject.py"
FAKE_ACP = REPO / "tests" / "fake_acp_serve.py"
FEATURE = REPO / "tests" / "features" / "leftover_acp_session_dead_nack.feature"
WAKE_FEATURE = REPO / "tests" / "features" / "grow_wake_inbox_session_prompt.feature"
ENV_EXAMPLE = REPO / ".env.example"

PINNED_SESSION = "sess-pinned-dead-nack"
REBORN_SESSION = "sess-reborn-dead-nack"
FAT_TOKEN = "FAT_DEAD_NACK_TOKEN_a1c3"
RESUME_RE = re.compile(r"\bgrok\b[^\n]*--resume")


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
        "contextId": "ctx-dead-nack-1",
        "parts": [{"kind": "text", "text": text}],
        "metadata": {"from": "ops"},
    }
    with inbox.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    return inbox


def _journal(path: Path) -> dict[str, Any]:
    assert path.is_file(), f"missing ACP journal {path}"
    return json.loads(path.read_text(encoding="utf-8"))


@contextlib.contextmanager
def _fake_acp(
    tmp_path: Path,
    *,
    session: str = PINNED_SESSION,
    prompt_mode: str = "silent",
    reborn_session: str = REBORN_SESSION,
) -> Iterator[dict[str, Any]]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    journal = tmp_path / "fake-acp.json"
    ready = tmp_path / "fake-acp.ready"
    cmd = [
        sys.executable,
        str(FAKE_ACP),
        "--journal",
        str(journal),
        "--ready",
        str(ready),
        "--session",
        session,
        "--prompt-mode",
        prompt_mode,
    ]
    if reborn_session:
        cmd.extend(["--reborn-session", reborn_session])
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.time() + 5.0
        while time.time() < deadline:
            if proc.poll() is not None:
                err = proc.stderr.read() if proc.stderr else ""
                out = proc.stdout.read() if proc.stdout else ""
                raise RuntimeError(f"fake ACP serve exited {proc.returncode}: {out}{err}")
            if ready.is_file() and "port=" in ready.read_text(encoding="utf-8"):
                break
            time.sleep(0.05)
        else:
            proc.terminate()
            raise TimeoutError("fake ACP serve did not become ready")
        blob = ready.read_text(encoding="utf-8")
        port = int(re.search(r"port=(\d+)", blob).group(1))
        yield {
            "proc": proc,
            "port": port,
            "pid": proc.pid,
            "journal": journal,
            "session": session,
        }
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)


def _prompt_wrapper(tmp_path: Path) -> Path:
    return _write_exec(
        tmp_path / "seat-prompt-acp-dead-nack.sh",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'SEAT="${1:?}"\n'
        "shift\n"
        f'exec "{sys.executable}" "{ACP_INJECT}" --seat "$SEAT" --pin-session --stdin\n',
    )


def _forbidden_start_daemon(tmp_path: Path) -> tuple[Path, Path]:
    stamp = tmp_path / "start-daemon-called"
    script = _write_exec(
        tmp_path / "start-seat-daemon-forbidden.sh",
        "#!/usr/bin/env bash\n"
        f'echo called >>"{stamp}"\n'
        'echo "FAT: START_DAEMON should not run while serve is healthy" >&2\n'
        "exit 1\n",
    )
    return script, stamp


def _install_fake_grok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    log = tmp_path / "fake-grok.json"
    log.write_text("[]\n", encoding="utf-8")
    script = (
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "log = Path(os.environ['FAKE_GROK_LOG'])\n"
        "rows = json.loads(log.read_text()) if log.is_file() else []\n"
        "rows.append({'argv': sys.argv[1:]})\n"
        "log.write_text(json.dumps(rows))\n"
        "if '--resume' in sys.argv:\n"
        "    sys.stderr.write('FAT: grok --resume is forbidden on leftover ACP inject\\n')\n"
        "    raise SystemExit(2)\n"
        "sys.stderr.write('FAT: unexpected grok invocation (leftover ACP is session/prompt)\\n')\n"
        "raise SystemExit(2)\n"
    )
    _write_exec(tmp_path / "fake-bin" / "grok", script)
    monkeypatch.setenv("FAKE_GROK_LOG", str(log))
    monkeypatch.setenv(
        "PATH",
        str(tmp_path / "fake-bin") + os.pathsep + os.environ.get("PATH", "/usr/bin:/bin"),
    )
    return log


def _prep_wake(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    unique: str,
    start_daemon: Path,
    prompt_sh: Path,
) -> tuple[ModuleType, Path]:
    monkeypatch.setenv("GCS_ACP_INJECT_TIMEOUT", "2")
    monkeypatch.setenv("GCS_ACP_ACCEPT_DEADLINE", "0.25")
    monkeypatch.setenv("GCS_WAKE_ACP_TIMEOUT", "4")
    monkeypatch.setenv("GCS_ACP_DEAD_STREAK", "3")
    monkeypatch.setenv("GCS_ROOT", str(REPO))
    state = tmp_path / "a2a-state"
    state.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("GCS_A2A_STATE", str(state))
    wake = _load(WAKE_PY, f"gcs_wake_dead_nack_{unique}")
    monkeypatch.setattr(wake, "STATE_DIR", state)
    monkeypatch.setattr(wake, "ROOT", REPO)
    monkeypatch.setattr(wake, "START_DAEMON", start_daemon)
    monkeypatch.setattr(wake, "SEAT_PROMPT_ACP", prompt_sh)
    wake.PROMPT_TIMEOUT_SEC = 4.0
    return wake, state


def _write_healthy_seat(state: Path, seat: str, *, pid: int, port: int, session: str) -> Path:
    sd = state / seat
    sd.mkdir(parents=True, exist_ok=True)
    (sd / "daemon.pid").write_text(f"{pid}\n", encoding="utf-8")
    (sd / "acp.secret").write_text("fat-acp-secret\n", encoding="utf-8")
    (sd / "acp.url").write_text(
        f"ws://127.0.0.1:{port}/ws?server-key=fat-acp-secret\n",
        encoding="utf-8",
    )
    (sd / "acp.session").write_text(session + "\n", encoding="utf-8")
    (sd / "grow.mode").write_text(
        "kind=grok-build-serve\nawake=inbox-acp-prompt\nmode=acp-serve\n",
        encoding="utf-8",
    )
    return sd


def test_gherkin_is_session_dead_nack_not_wake_inbox_clone() -> None:
    """This FAT is leftover ACP SESSION_DEAD, not #103 inbox→session/prompt."""
    assert FEATURE.is_file()
    text = FEATURE.read_text(encoding="utf-8")
    assert "ACP_INJECT_SESSION_DEAD" in text
    assert "session/new" in text
    assert "no-start" in text
    assert "grok --resume" in text
    assert "LIV-85" in text
    assert FEATURE != WAKE_FEATURE
    wake_text = WAKE_FEATURE.read_text(encoding="utf-8")
    assert "ACP_INJECT_SESSION_DEAD" not in wake_text
    env = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "GCS_ACP_ACCEPT_DEADLINE=120" in env
    assert "GCS_ACP_DEAD_STREAK=3" in env
    a2a = (REPO / "docs" / "A2A.md").read_text(encoding="utf-8")
    assert "leftover_acp_session_dead_nack.feature" in a2a
    assert "ACP_INJECT_SESSION_DEAD" in a2a


def test_fake_acp_serve_cli_documents_silent_prompt_mode() -> None:
    proc = subprocess.run(
        [sys.executable, str(FAKE_ACP), "--help"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=10,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "--prompt-mode" in blob
    assert "silent" in blob
    assert "--reborn-session" in blob


def test_wake_does_not_treat_session_dead_as_accepted() -> None:
    wake = _load(WAKE_PY, "gcs_wake_session_dead_not_ok")
    dead = "ACP_INJECT_SESSION_DEAD old=sess-pinned new=sess-reborn evidence=no-accept-streak\n"
    timeout = "ACP_INJECT_TIMEOUT seat=floor session=sess-pinned timeout=120 reason=no-accept\n"
    assert wake.prompt_output_accepted(1, dead) is False
    assert wake.prompt_output_accepted(1, timeout + dead) is False
    assert wake.prompt_output_accepted(1, "ACP_INJECT_OK seat=floor session=s chars=12\n") is True


def test_fat_third_silent_nack_session_new_once_never_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    grok_log = _install_fake_grok(tmp_path, monkeypatch)
    forbidden, stamp = _forbidden_start_daemon(tmp_path)
    prompt_sh = _prompt_wrapper(tmp_path)
    with _fake_acp(tmp_path / "silent-serve", prompt_mode="silent") as acp:
        wake, state = _prep_wake(
            tmp_path,
            monkeypatch,
            unique="third_nack",
            start_daemon=forbidden,
            prompt_sh=prompt_sh,
        )
        sd = _write_healthy_seat(
            state, "floor", pid=acp["pid"], port=acp["port"], session=PINNED_SESSION
        )
        _append_inbox(
            state,
            "floor",
            "task-dead-nack-1",
            f"TASK_ASSIGN: {FAT_TOKEN} STATUS then work. Open a PR.",
        )
        blobs: list[str] = []
        for i in range(2):
            result = wake.process_once("floor")
            captured = capsys.readouterr()
            blob = captured.out + captured.err
            blobs.append(blob)
            assert result["consumed"] == 0, blob
            assert result.get("reason") == "prompt-fail", result
            assert "ACP_INJECT_SESSION_DEAD" not in blob, blob
            assert "reason=no-accept" in blob, blob
            assert "ACP_INJECT_HANDOFF" not in blob, blob
            assert (sd / "acp.session").read_text(encoding="utf-8").strip() == PINNED_SESSION
            evidence = _journal(acp["journal"])
            assert "session/new" not in evidence["methods"], evidence
            streak = (sd / "acp.no_accept_streak").read_text(encoding="utf-8")
            assert f"count={i + 1}" in streak
            assert f"session={PINNED_SESSION}" in streak
            offset_path = sd / "wake.offset"
            assert not offset_path.is_file() or int(
                offset_path.read_text(encoding="utf-8").strip() or "0"
            ) == 0

        third = wake.process_once("floor")
        captured = capsys.readouterr()
        blob3 = captured.out + captured.err
        assert third["consumed"] == 0, blob3
        assert third.get("reason") == "prompt-fail", third
        assert "ACP_INJECT_SESSION_DEAD" in blob3, blob3
        assert f"old={PINNED_SESSION}" in blob3, blob3
        assert f"new={REBORN_SESSION}" in blob3, blob3
        assert "ACP_INJECT_HANDOFF" not in blob3, blob3
        assert "ACP_INJECT_CANCEL" not in blob3, blob3
        assert (sd / "acp.session").read_text(encoding="utf-8").strip() == REBORN_SESSION
        evidence = _journal(acp["journal"])
        assert evidence["methods"].count("session/new") == 1, evidence
        assert evidence["methods"].count("session/prompt") == 3, evidence
        assert "session/cancel" not in evidence["methods"], evidence
        assert REBORN_SESSION in evidence.get("session_ids", []), evidence
        assert not (sd / "acp.no_accept_streak").is_file()
        assert not stamp.is_file()
        grok_rows = json.loads(grok_log.read_text(encoding="utf-8"))
        assert grok_rows == []
        for row in grok_rows:
            assert "--resume" not in row.get("argv", [])
        inject_src = ACP_INJECT.read_text(encoding="utf-8")
        prompt_src = SEAT_PROMPT.read_text(encoding="utf-8")
        wake_src = WAKE_PY.read_text(encoding="utf-8")
        for blob, label in (
            (inject_src, "acp_inject.py"),
            (prompt_src, "seat-prompt-acp.sh"),
            (wake_src, "wake-daemon.py"),
        ):
            assert '"--resume"' not in blob, label
            assert "'--resume'" not in blob, label
        for line in prompt_src.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("echo "):
                continue
            assert not RESUME_RE.search(stripped), stripped
