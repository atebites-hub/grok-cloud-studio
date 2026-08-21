"""Seat start must put taskboard/ticket/tb on grok serve PATH.

Directors exec `ticket list` / `taskboard ticket move` against
`$GCS_A2A_STATE/taskboard/taskboard.db` without a box-local symlink.
Fake binary only — no live grok serve, no ticket moves on a live board.
"""
from __future__ import annotations

import stat
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SEAT_COMMON = REPO / "scripts" / "directors" / "seat-daemon-common.sh"
START_DAEMON = REPO / "scripts" / "directors" / "start-seat-daemon.sh"
WAKE_LOOP = REPO / "scripts" / "directors" / "seat-wake-loop.sh"
SEAT_PROMPT = REPO / "scripts" / "directors" / "seat-prompt-acp.sh"
FOOTER = REPO / "scripts" / "directors" / "common_footer.txt"
TASKBOARD_DOC = REPO / "docs" / "studio" / "TASKBOARD.md"
HOST_TICKER = REPO / "scripts" / "a2a" / "host-ticker.py"
HOST_CLOCK = REPO / "scripts" / "directors" / "host-clock-ticker.sh"


def _write_exec(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def _fake_taskboard(tmp_path: Path) -> tuple[Path, Path]:
    log = tmp_path / "taskboard.argv"
    binary = _write_exec(
        tmp_path / "host-bin" / "taskboard",
        "#!/bin/sh\n"
        f'echo "$@" >> "{log}"\n'
        'echo "$@"\n',
    )
    return binary, log


def _base_env(
    tmp_path: Path,
    *,
    taskboard_bin: Path | None = None,
    extra_path: str = "",
) -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    path = extra_path or "/usr/bin:/bin"
    env = {
        "PATH": path,
        "HOME": str(home),
        "GCS_ROOT": str(REPO),
        "GCS_A2A_STATE": str(tmp_path / "a2a-state"),
        "GROK_HOME": str(tmp_path / "grok-home"),
        "LC_ALL": "C",
        "TERM": "dumb",
    }
    if taskboard_bin is not None:
        env["TASKBOARD_BIN"] = str(taskboard_bin)
    return env


def _run_seat_bash(script: str, env: dict[str, str], *, timeout: int = 15) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", script],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def test_mocked_seat_env_which_taskboard_and_ticket_succeed(tmp_path: Path) -> None:
    binary, _log = _fake_taskboard(tmp_path)
    env = _base_env(tmp_path, taskboard_bin=binary)
    script = r"""
set -euo pipefail
source scripts/directors/seat-daemon-common.sh
install_seat_taskboard_cli floor
command -v taskboard
command -v ticket
command -v tb
"""
    proc = _run_seat_bash(script, env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    assert any(ln.endswith("/taskboard") for ln in lines), blob
    assert any(ln.endswith("/ticket") for ln in lines), blob
    assert any(ln.endswith("/tb") for ln in lines), blob


def test_wrappers_invoke_db_to_state_dir_taskboard(tmp_path: Path) -> None:
    binary, log = _fake_taskboard(tmp_path)
    env = _base_env(tmp_path, taskboard_bin=binary)
    db = tmp_path / "a2a-state" / "taskboard" / "taskboard.db"
    script = r"""
set -euo pipefail
source scripts/directors/seat-daemon-common.sh
export_seat_serve_env floor
# Simulate grok agent serve PATH: wrapper dirs only (no host-bin).
# Live serve does not inherit TASKBOARD_BIN; wrappers bake the binary path.
unset TASKBOARD_BIN
export PATH="${GROK_HOME}/bin:${HOME}/.grok/bin"
command -v taskboard >/dev/null
command -v ticket >/dev/null
command -v tb >/dev/null
taskboard ticket list
ticket move T-1 --status done
tb create --title "demo"
printf 'DB=%s\n' "${GCS_TASKBOARD_DB}"
printf 'STATE=%s\n' "${GCS_A2A_STATE}"
"""
    proc = _run_seat_bash(script, env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    argv = log.read_text(encoding="utf-8") if log.is_file() else ""
    assert "--db" in argv, argv or blob
    assert str(db) in argv, argv or blob
    lines = [ln.strip() for ln in argv.splitlines() if ln.strip()]
    assert any(ln.startswith(f"--db {db} ticket list") for ln in lines), argv
    assert any("ticket move T-1 --status done" in ln for ln in lines), argv
    assert any("ticket create --title demo" in ln or 'ticket create --title "demo"' in ln for ln in lines), argv
    assert f"DB={db}" in proc.stdout, blob
    assert f"STATE={tmp_path / 'a2a-state'}" in proc.stdout, blob


def test_serve_path_fixture_includes_wrapper_dir(tmp_path: Path) -> None:
    binary, _log = _fake_taskboard(tmp_path)
    env = _base_env(tmp_path, taskboard_bin=binary)
    script = r"""
set -euo pipefail
source scripts/directors/seat-daemon-common.sh
export_seat_serve_env floor
printf 'PATH=%s\n' "$PATH"
printf 'GROK_HOME=%s\n' "$GROK_HOME"
ls -1 "${GROK_HOME}/bin"
ls -1 "${HOME}/.grok/bin"
"""
    proc = _run_seat_bash(script, env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    grok_bin = str(Path(env["GROK_HOME"]) / "bin")
    host_grok_bin = str(Path(env["HOME"]) / ".grok" / "bin")
    assert grok_bin in proc.stdout, blob
    path_line = next(ln for ln in proc.stdout.splitlines() if ln.startswith("PATH="))
    path_val = path_line.split("=", 1)[1]
    assert grok_bin in path_val.split(":") or host_grok_bin in path_val.split(":"), path_val
    names = set(blob.split())
    assert "taskboard" in names
    assert "ticket" in names
    assert "tb" in names


def test_start_scripts_fail_closed_without_taskboard_on_path() -> None:
    """Law: seats must install wrappers onto the grok serve PATH."""
    common = SEAT_COMMON.read_text(encoding="utf-8")
    daemon = START_DAEMON.read_text(encoding="utf-8")
    wake = WAKE_LOOP.read_text(encoding="utf-8")
    prompt = SEAT_PROMPT.read_text(encoding="utf-8")
    assert "install_seat_taskboard_cli" in common
    assert "export_seat_serve_env" in common
    assert "GCS_TASKBOARD_DB" in common
    assert "GCS_A2A_STATE" in common
    identity_fn = common.split("install_seat_identity() {", 1)[1]
    assert "install_seat_taskboard_cli" in identity_fn
    assert "export_seat_serve_env" in daemon
    assert "GCS_TASKBOARD_DB" in daemon
    assert 'GROK_HOME}/bin' in daemon or "${GROK_HOME}/bin" in daemon
    assert "export_seat_serve_env" in wake or "GCS_TASKBOARD_DB" in wake
    assert "export_seat_serve_env" in prompt or "GCS_TASKBOARD_DB" in prompt
    assert "taskboard ticket move" in common
    footer = FOOTER.read_text(encoding="utf-8")
    ticker = HOST_TICKER.read_text(encoding="utf-8")
    clock = HOST_CLOCK.read_text(encoding="utf-8")
    assert "taskboard ticket move" in footer or "ticket move" in footer
    assert "taskboard ticket move" in ticker
    assert "taskboard ticket move" in clock
    doc = TASKBOARD_DOC.read_text(encoding="utf-8")
    assert "GCS_TASKBOARD_DB" in doc
    assert "ticket move" in doc
    assert "tb " in doc or "`tb " in doc


def test_wrappers_exist_when_host_taskboard_is_off_path(tmp_path: Path) -> None:
    """Serve PATH is only ~/.grok/bin — host /workspace/bin must not be required."""
    binary, log = _fake_taskboard(tmp_path)
    env = _base_env(tmp_path, taskboard_bin=binary, extra_path="/usr/bin:/bin")
    assert "taskboard" not in env["PATH"]
    script = r"""
set -euo pipefail
source scripts/directors/seat-daemon-common.sh
export_seat_serve_env floor
# Strip everything except serve PATH dirs (LIVE: grok serve PATH is only ~/.grok/bin).
unset TASKBOARD_BIN
export PATH="${HOME}/.grok/bin"
command -v taskboard
command -v ticket
ticket list
"""
    proc = _run_seat_bash(script, env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    which_taskboard = next(ln.strip() for ln in proc.stdout.splitlines() if ln.strip().endswith("/taskboard"))
    assert str(Path(env["HOME"]) / ".grok" / "bin" / "taskboard") == which_taskboard
    argv = log.read_text(encoding="utf-8")
    db = tmp_path / "a2a-state" / "taskboard" / "taskboard.db"
    assert f"--db {db} ticket list" in argv


def test_identity_install_does_not_start_or_kill_serve(tmp_path: Path) -> None:
    binary, _log = _fake_taskboard(tmp_path)
    env = _base_env(tmp_path, taskboard_bin=binary)
    script = r"""
set -euo pipefail
source scripts/directors/seat-daemon-common.sh
install_seat_identity floor
"""
    proc = _run_seat_bash(script, env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    common = SEAT_COMMON.read_text(encoding="utf-8")
    daemon = START_DAEMON.read_text(encoding="utf-8")
    assert "install_seat_taskboard_cli" in common
    # Wrapper install must not remint a healthy serve.
    already = daemon.split("SEAT_DAEMON_ALREADY")[0]
    assert (
        "export_seat_serve_env" in already
        or "install_seat_taskboard_cli" in already
        or "install_seat_identity" in already
    )
    after_already = daemon.split("SEAT_DAEMON_ALREADY", 1)[1]
    assert "kill" not in after_already.split("SEAT_DAEMON_STALE_KILL")[0]
    wrap = Path(env["GROK_HOME"]) / "bin" / "ticket"
    host_wrap = Path(env["HOME"]) / ".grok" / "bin" / "ticket"
    assert wrap.is_file() or host_wrap.is_file(), blob
