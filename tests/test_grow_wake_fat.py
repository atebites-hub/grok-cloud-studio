"""FAT: leftover ACP GROW wake. inbox.jsonl → session/prompt in serve pid.

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
WAKE_LOOP = REPO / "scripts" / "directors" / "seat-wake-loop.sh"
SEAT_PROMPT = REPO / "scripts" / "directors" / "seat-prompt-acp.sh"
START_DAEMON = REPO / "scripts" / "directors" / "start-seat-daemon.sh"
BUS_SH = REPO / "scripts" / "a2a" / "start-studio-bus.sh"
LAUNCH = REPO / "scripts" / "launch-cloud-extra-high.sh"
REGISTRY = REPO / "docs" / "a2a" / "registry.json"
FEATURE = REPO / "tests" / "features" / "grow_wake_inbox_session_prompt.feature"
FAKE_ACP = REPO / "tests" / "fake_acp_serve.py"
ACP_INJECT = REPO / "scripts" / "directors" / "acp_inject.py"

FAT_TOKEN = "FAT_WAKE_TOKEN_9f3a"
FAT_TOKEN_SECOND = "FAT_WAKE_TOKEN_SECOND"
PINNED_SESSION = "sess-pinned-grow-fat"
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
        "contextId": "ctx-fat-1",
        "parts": [{"kind": "text", "text": text}],
        "metadata": {"from": "ops"},
    }
    with inbox.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    return inbox


def _noncomment(src: str) -> str:
    return "\n".join(
        line for line in src.splitlines() if line.strip() and not line.strip().startswith("#")
    )


def _journal(path: Path) -> dict[str, Any]:
    assert path.is_file(), f"missing ACP journal {path}"
    return json.loads(path.read_text(encoding="utf-8"))


@contextlib.contextmanager
def _fake_acp(tmp_path: Path, *, session: str = PINNED_SESSION) -> Iterator[dict[str, Any]]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    journal = tmp_path / "fake-acp.json"
    ready = tmp_path / "fake-acp.ready"
    proc = subprocess.Popen(
        [
            sys.executable,
            str(FAKE_ACP),
            "--journal",
            str(journal),
            "--ready",
            str(ready),
            "--session",
            session,
        ],
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
        tmp_path / "seat-prompt-acp-fat.sh",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'SEAT="${1:?}"\n'
        "shift\n"
        f'exec "{sys.executable}" "{ACP_INJECT}" --seat "$SEAT" --pin-session --stdin\n',
    )


def _start_daemon_script(tmp_path: Path, *, log: Path, session: str) -> Path:
    return _write_exec(
        tmp_path / "start-seat-daemon-fat.sh",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'SEAT="${1:?}"\n'
        'SD="${GCS_A2A_STATE}/${SEAT}"\n'
        'mkdir -p "$SD"\n'
        f'echo "$SEAT" >>"{log}"\n'
        'READY="$SD/fake-acp.ready"\n'
        'rm -f "$READY"\n'
        f'"{sys.executable}" "{FAKE_ACP}" '
        '--journal "$SD/fake-acp.json" --ready "$READY" '
        f'--session "{session}" >/dev/null 2>"$SD/fake-acp.serve.err" &\n'
        'echo $! >"$SD/daemon.pid"\n'
        "for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do\n"
        '  if [[ -f "$READY" ]]; then break; fi\n'
        "  sleep 0.05\n"
        "done\n"
        'PORT="$(sed -n \'s/^FAKE_ACP_READY port=\\([0-9]*\\).*/\\1/p\' "$READY")"\n'
        'SECRET="fat-acp-secret"\n'
        'printf "%s\\n" "$SECRET" >"$SD/acp.secret"\n'
        'printf "ws://127.0.0.1:%s/ws?server-key=%s\\n" "$PORT" "$SECRET" >"$SD/acp.url"\n'
        f'if [[ ! -f "$SD/acp.session" ]]; then printf "%s\\n" "{session}" >"$SD/acp.session"; fi\n'
        'echo "SEAT_DAEMON_START seat=$SEAT pid=$(cat "$SD/daemon.pid") port=$PORT"\n',
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
        "    sys.stderr.write('FAT: grok --resume is forbidden on leftover ACP GROW wake\\n')\n"
        "    raise SystemExit(2)\n"
        "sys.stderr.write('FAT: unexpected grok invocation (wake must session/prompt)\\n')\n"
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
    monkeypatch.setenv("GCS_ACP_INJECT_TIMEOUT", "8")
    monkeypatch.setenv("GCS_ACP_ACCEPT_DEADLINE", "8")
    monkeypatch.setenv("GCS_WAKE_ACP_TIMEOUT", "8")
    monkeypatch.setenv("GCS_ACP_DEAD_STREAK", "3")
    monkeypatch.setenv("GCS_ROOT", str(REPO))
    state = tmp_path / "a2a-state"
    state.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("GCS_A2A_STATE", str(state))
    wake = _load(WAKE_PY, f"gcs_wake_fat_{unique}")
    monkeypatch.setattr(wake, "STATE_DIR", state)
    monkeypatch.setattr(wake, "ROOT", REPO)
    monkeypatch.setattr(wake, "START_DAEMON", start_daemon)
    monkeypatch.setattr(wake, "SEAT_PROMPT_ACP", prompt_sh)
    wake.PROMPT_TIMEOUT_SEC = 8.0
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


def test_fat_gherkin_forbids_resume_and_names_session_prompt() -> None:
    assert FEATURE.is_file()
    text = FEATURE.read_text(encoding="utf-8")
    assert "inbox.jsonl" in text
    assert "session/prompt" in text
    assert "grok --resume" in text
    assert "same serve pid" in text or "same serve" in text
    assert "Hermes" in text
    assert "Bot CloudAgent" in text


def test_serve_healthy_requires_listening_acp_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wake, state = _prep_wake(
        tmp_path,
        monkeypatch,
        unique="healthy_port",
        start_daemon=_forbidden_start_daemon(tmp_path)[0],
        prompt_sh=_prompt_wrapper(tmp_path),
    )
    sd = state / "floor"
    sd.mkdir(parents=True)
    (sd / "daemon.pid").write_text(f"{os.getpid()}\n", encoding="utf-8")
    (sd / "acp.url").write_text("ws://127.0.0.1:59999/ws\n", encoding="utf-8")
    (sd / "acp.secret").write_text("secret\n", encoding="utf-8")
    assert wake.serve_healthy("floor") is False

    with _fake_acp(tmp_path / "up") as acp:
        _write_healthy_seat(
            state, "floor", pid=acp["pid"], port=acp["port"], session=PINNED_SESSION
        )
        assert wake.serve_healthy("floor") is True


def test_fat_inbox_session_prompt_same_serve_pid_never_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    grok_log = _install_fake_grok(tmp_path, monkeypatch)
    forbidden, stamp = _forbidden_start_daemon(tmp_path)
    prompt_sh = _prompt_wrapper(tmp_path)
    with _fake_acp(tmp_path) as acp:
        wake, state = _prep_wake(
            tmp_path,
            monkeypatch,
            unique="inbox_prompt",
            start_daemon=forbidden,
            prompt_sh=prompt_sh,
        )
        _write_healthy_seat(
            state, "floor", pid=acp["pid"], port=acp["port"], session=PINNED_SESSION
        )
        _append_inbox(
            state,
            "floor",
            "task-fat-1",
            f"TASK_ASSIGN: {FAT_TOKEN} then STATUS. Open a PR.",
        )
        first = wake.process_once("floor")
        assert first["consumed"] == 1, first
        assert first["serve_pid"] == acp["pid"]
        assert first["acp_session"] == PINNED_SESSION
        pin = (state / "floor" / "acp.session").read_text(encoding="utf-8").strip()
        assert pin == PINNED_SESSION
        offset = int((state / "floor" / "wake.offset").read_text(encoding="utf-8").strip())
        assert offset > 0
        assert not stamp.is_file()
        evidence = _journal(acp["journal"])
        assert "session/prompt" in evidence["methods"], evidence
        assert "session/load" in evidence["methods"], evidence
        assert "session/new" not in evidence["methods"], evidence
        assert any(FAT_TOKEN in p for p in evidence["prompts"]), evidence["prompts"]
        assert evidence["pid"] == acp["pid"]
        assert evidence["resume_seen"] is False
        grok_rows = json.loads(grok_log.read_text(encoding="utf-8"))
        assert grok_rows == []
        for row in grok_rows:
            assert "--resume" not in row.get("argv", [])

        _append_inbox(
            state,
            "floor",
            "task-fat-2",
            f"TASK_ASSIGN: {FAT_TOKEN_SECOND} stay on this serve. Open a PR.",
        )
        second = wake.process_once("floor")
        assert second["consumed"] == 1, second
        assert second["serve_pid"] == first["serve_pid"] == acp["pid"]
        assert second["acp_session"] == first["acp_session"] == PINNED_SESSION
        evidence2 = _journal(acp["journal"])
        prompts = evidence2["prompts"]
        assert any(FAT_TOKEN in p for p in prompts)
        assert any(FAT_TOKEN_SECOND in p for p in prompts)
        assert evidence2["methods"].count("session/prompt") == 2
        assert "session/new" not in evidence2["methods"]


def test_fat_serve_down_restarts_serve_not_grok_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    grok_log = _install_fake_grok(tmp_path, monkeypatch)
    start_log = tmp_path / "start-daemon.log"
    start_sh = _start_daemon_script(tmp_path, log=start_log, session=PINNED_SESSION)
    prompt_sh = _prompt_wrapper(tmp_path)
    wake, state = _prep_wake(
        tmp_path,
        monkeypatch,
        unique="serve_down",
        start_daemon=start_sh,
        prompt_sh=prompt_sh,
    )
    _append_inbox(
        state,
        "ops",
        "task-fat-down-1",
        f"STATUS: {FAT_TOKEN} after serve restart. Open a PR.",
    )
    result = wake.process_once("ops")
    assert result["consumed"] == 1, result
    assert start_log.is_file()
    assert "ops" in start_log.read_text(encoding="utf-8")
    sd = state / "ops"
    serve_pid = int((sd / "daemon.pid").read_text(encoding="utf-8").strip())
    assert result["serve_pid"] == serve_pid
    assert serve_pid > 0
    assert result["acp_session"] == PINNED_SESSION
    journal = _journal(sd / "fake-acp.json")
    assert "session/prompt" in journal["methods"], journal
    assert any(FAT_TOKEN in p for p in journal["prompts"]), journal["prompts"]
    assert journal["pid"] == serve_pid
    grok_rows = json.loads(grok_log.read_text(encoding="utf-8"))
    for row in grok_rows:
        assert "--resume" not in row.get("argv", []), row
    src = WAKE_PY.read_text(encoding="utf-8")
    assert "ensure_seat_serve" in src
    assert "prompt_acp" in src
    child = subprocess.run(
        ["kill", "-0", str(serve_pid)],
        capture_output=True,
        timeout=5,
        check=False,
    )
    if child.returncode == 0:
        subprocess.run(["kill", str(serve_pid)], check=False, timeout=5)
        time.sleep(0.1)
        subprocess.run(["kill", "-9", str(serve_pid)], check=False, timeout=5)


def test_fat_source_law_never_resume_bot_cloudagent_or_hermes() -> None:
    wake_src = WAKE_PY.read_text(encoding="utf-8")
    loop_src = WAKE_LOOP.read_text(encoding="utf-8")
    prompt_src = SEAT_PROMPT.read_text(encoding="utf-8")
    daemon_src = START_DAEMON.read_text(encoding="utf-8")
    bus_src = BUS_SH.read_text(encoding="utf-8")
    # Argv law: leftover ACP wake must not pass --resume to grok. Docstrings
    # may name the forbidden path in prose ("never grok --resume").
    for blob, label in (
        (wake_src, "wake-daemon.py"),
        (_noncomment(loop_src), "seat-wake-loop.sh"),
        (_noncomment(prompt_src), "seat-prompt-acp.sh"),
        (_noncomment(daemon_src), "start-seat-daemon.sh"),
    ):
        assert '"--resume"' not in blob, f"{label} must not pass --resume argv"
        assert "'--resume'" not in blob, f"{label} must not pass --resume argv"
    # Echo/docs may name the forbidden path; argv must not invoke it.
    for blob, label in (
        (_noncomment(loop_src), "seat-wake-loop.sh"),
        (_noncomment(prompt_src), "seat-prompt-acp.sh"),
        (_noncomment(daemon_src), "start-seat-daemon.sh"),
    ):
        for line in blob.splitlines():
            stripped = line.strip()
            if stripped.startswith("echo ") or "WAKE_LOOP_FAIL" in stripped or "ACP_PROMPT_FAIL" in stripped:
                continue
            assert not RESUME_RE.search(stripped), f"{label}: {stripped}"
    assert "session/prompt" in wake_src.lower() or "ACP_PROMPT" in wake_src
    assert "wake-daemon.py" in loop_src
    assert "--pin-session" in prompt_src
    assert "acp_inject.py" in prompt_src
    assert "agent" in daemon_src and "serve" in daemon_src
    assert "--no-leader" in daemon_src
    assert "seat-wake-loop.sh" in bus_src
    assert "start-seat-daemon.sh" in _noncomment(bus_src)
    launch = LAUNCH.read_text(encoding="utf-8")
    assert "grok-4.6" in launch
    assert "xhigh" in launch
    assert "fast=false" in launch
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    skip = {str(s) for s in registry.get("skipSeats") or []}
    assert "orchestrator" in skip
    assert "launch-cloud-extra-high.sh" not in wake_src
    hermes = REPO / "vendor" / "hermes-agent"
    assert not hermes.exists()
    assert not (REPO / "vendor" / "hermes").exists()
    agents = (REPO / "AGENTS.md").read_text(encoding="utf-8")
    a2a = (REPO / "docs" / "A2A.md").read_text(encoding="utf-8")
    blob = agents + "\n" + a2a
    assert "session/prompt" in blob
    assert "never `grok --resume`" in blob or "never grok --resume" in blob.lower()
    assert "Do not launch Bot CloudAgent" in a2a
