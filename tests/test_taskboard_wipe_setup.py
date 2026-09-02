"""Remaining tcarac/taskboard WIPE/setup paths under scripts/studio/taskboard.

Board-only deploy / teardown / wipe. Host ticket/tb on PATH. No Agent Kanban.
Does not twin gcs-taskboard-maintainer-kit-beat1849 (maintainer.sh health/docs)
or LIV-86 PIN/upgrade. Does not vendor a compiled taskboard binary.
"""
from __future__ import annotations

import socket
import stat
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FEATURE = REPO / "tests" / "features" / "taskboard_wipe_setup.feature"
TASKBOARD_DIR = REPO / "scripts" / "studio" / "taskboard"
SETUP_TB = TASKBOARD_DIR / "setup-taskboard.sh"
HOST_TICKET = TASKBOARD_DIR / "ticket"
HOST_TB = TASKBOARD_DIR / "tb"
COMMON_SH = TASKBOARD_DIR / "common.sh"
SETUP = REPO / "setup.sh"
CLEANUP = REPO / "cleanup.sh"
RECOVER = REPO / "recover.sh"
DOCTOR = REPO / "doctor.sh"
INSTALL = REPO / "install.sh"
WIPE = REPO / "docs" / "studio" / "WIPE.md"
TASKBOARD_DOC = REPO / "docs" / "studio" / "TASKBOARD.md"
TB_README = TASKBOARD_DIR / "README.md"
GITIGNORE = REPO / ".gitignore"

PRIVATE_GAME = "atebites-hub/" + "palemon"
BLACK_SWAN = "blackswan" + ".money"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _write_exec(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def _fake_taskboard(tmp_path: Path) -> tuple[Path, Path]:
    log = tmp_path / "tb.argv"
    fake = _write_exec(
        tmp_path / "host-bin" / "taskboard",
        "#!/bin/sh\n"
        f'printf "%s\\n" "$@" >> "{log}"\n'
        'for a in "$@"; do\n'
        '  case "$a" in\n'
        "    --foreground|mcp) sleep 20 ;;\n"
        "  esac\n"
        "done\n"
        "exit 0\n",
    )
    return fake, log


def _base_env(tmp_path: Path, *, taskboard_bin: Path | None = None) -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    kit = tmp_path / "kit"
    kit.mkdir(parents=True, exist_ok=True)
    state = tmp_path / "live-state"
    state.mkdir(parents=True, exist_ok=True)
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(home),
        "GCS_ROOT": str(kit),
        "GCS_A2A_STATE": str(state),
        "GCS_TASKBOARD_SKIP_READY": "1",
        "GCS_TASKBOARD_SKIP_INSTALL": "1",
        "GCS_TASKBOARD_SKIP_SUBMODULE": "1",
        "LC_ALL": "C",
        "TERM": "dumb",
        "CURSOR_API_KEY": "test-cursor-api-key-wipe-setup-not-leaked",
    }
    if taskboard_bin is not None:
        env["TASKBOARD_BIN"] = str(taskboard_bin)
        env["PATH"] = f"{taskboard_bin.parent}:/usr/bin:/bin"
    return env


def _run(
    script: Path,
    args: list[str],
    env: dict[str, str],
    *,
    timeout: int = 15,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(script), *args],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _stop(env: dict[str, str]) -> None:
    subprocess.run(
        ["bash", str(SETUP_TB), "stop"],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )


def test_feature_file_names_remaining_wipe_setup_not_maintainer_kit() -> None:
    assert FEATURE.is_file()
    text = FEATURE.read_text(encoding="utf-8")
    fold = " ".join(text.lower().split())
    assert "setup-taskboard.sh" in text
    assert "ticket" in fold and "tb" in fold
    assert "ak_refuse" in fold
    assert "maintainer.sh" in fold
    assert "living sky" in fold or "liv" in fold
    assert "never black swan" in fold
    assert BLACK_SWAN not in fold
    assert PRIVATE_GAME not in text
    assert "demonstrate" in fold and "theatre" in fold


def test_wipe_setup_scripts_exist_and_are_not_compiled_blobs() -> None:
    for path in (SETUP_TB, HOST_TICKET, HOST_TB, COMMON_SH):
        assert path.is_file(), f"missing {path.relative_to(REPO)}"
        head = path.read_bytes()[:4]
        assert head != b"\x7fELF", path
        assert head[:2] == b"#!", path
        assert "go build" not in path.read_text(encoding="utf-8")
        assert "make build" not in path.read_text(encoding="utf-8")
        assert "ak start" not in path.read_text(encoding="utf-8")
        assert "agent-kanban" not in path.read_text(encoding="utf-8") or "AK_REFUSE" in path.read_text(
            encoding="utf-8"
        )


def test_host_ticket_and_tb_are_not_grok_home_copies() -> None:
    for path in (HOST_TICKET, HOST_TB):
        text = path.read_text(encoding="utf-8")
        assert "gcs-host-taskboard-wrapper" in text or "gcs-host-taskboard" in text
        assert "gcs-seat-taskboard-wrapper" not in text
        assert "export GROK_HOME" not in text
        assert "GROK_HOME/" not in text
        assert "echo \"$CURSOR_API_KEY\"" not in text
        assert "CURSOR_API_KEY=" not in text
        assert "TAILSCALE_AUTH_KEY=" not in text
        assert PRIVATE_GAME not in text


def test_setup_taskboard_help_and_secret_free(tmp_path: Path) -> None:
    env = _base_env(tmp_path)
    proc = _run(SETUP_TB, ["--help"], env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "Usage" in blob or "setup-taskboard.sh" in blob
    assert "start" in blob and "stop" in blob and "wipe" in blob
    assert "CURSOR_API_KEY=" not in blob
    assert "test-cursor-api-key-wipe-setup-not-leaked" not in blob
    text = SETUP_TB.read_text(encoding="utf-8")
    assert "ak start" not in text
    assert "mint-floor-ops-worker" not in text
    assert "--daemons" not in text or "NO --daemons" in text or "no --daemons" in text.lower()
    assert "maintainer.sh" not in text
    assert "upgrade-taskboard.sh" not in text
    assert "health-taskboard.sh" not in text
    assert PRIVATE_GAME not in text
    assert BLACK_SWAN not in text.lower()


def test_setup_taskboard_start_installs_ticket_tb_and_starts_ui_mcp(
    tmp_path: Path,
) -> None:
    fake, log = _fake_taskboard(tmp_path)
    env = _base_env(tmp_path, taskboard_bin=fake)
    kit = Path(env["GCS_ROOT"])
    state = Path(env["GCS_A2A_STATE"])
    try:
        proc = _run(SETUP_TB, ["start"], env)
        blob = proc.stdout + proc.stderr
        assert proc.returncode == 0, blob
        assert "TASKBOARD_SETUP_OK" in blob
        assert "CURSOR_API_KEY=" not in blob
        assert env["CURSOR_API_KEY"] not in blob
        ticket = kit / "bin" / "ticket"
        tb = kit / "bin" / "tb"
        assert ticket.exists(), blob
        assert tb.exists(), blob
        db = state / "taskboard" / "taskboard.db"
        argv = log.read_text(encoding="utf-8") if log.is_file() else ""
        assert "--db" in argv
        assert str(db) in argv
        assert "start" in argv
        assert "mcp" in argv or "TASKBOARD_MCP" in blob
        home_ticket = Path(env["HOME"]) / ".local" / "bin" / "ticket"
        assert home_ticket.exists() or ticket.exists()
        listed = subprocess.run(
            [str(ticket), "list"],
            cwd=str(REPO),
            env={**env, "PATH": f"{ticket.parent}:{env['PATH']}"},
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert listed.returncode == 0, listed.stdout + listed.stderr
        recorded = log.read_text(encoding="utf-8")
        assert "ticket" in recorded
        assert "list" in recorded
        assert str(db) in recorded
        tb_list = subprocess.run(
            [str(tb), "list"],
            cwd=str(REPO),
            env={**env, "PATH": f"{tb.parent}:{env['PATH']}"},
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert tb_list.returncode == 0, tb_list.stdout + tb_list.stderr
        status = _run(SETUP_TB, ["status"], env)
        assert status.returncode == 0, status.stdout + status.stderr
        assert "TASKBOARD_SETUP_STATUS" in status.stdout + status.stderr
    finally:
        _stop(env)


def test_setup_taskboard_stop_keeps_studio_env_and_db(tmp_path: Path) -> None:
    fake, _log = _fake_taskboard(tmp_path)
    env = _base_env(tmp_path, taskboard_bin=fake)
    state = Path(env["GCS_A2A_STATE"])
    studio = state / "studio.env"
    studio.write_text("GCS_MIND_SEATS=\n# keep-me\n", encoding="utf-8")
    db = state / "taskboard" / "taskboard.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_text("db\n", encoding="utf-8")
    try:
        start = _run(SETUP_TB, ["start"], env)
        assert start.returncode == 0, start.stdout + start.stderr
        stop = _run(SETUP_TB, ["stop"], env)
        blob = stop.stdout + stop.stderr
        assert stop.returncode == 0, blob
        assert "TASKBOARD_SETUP_STOP" in blob
        assert studio.is_file()
        assert "keep-me" in studio.read_text(encoding="utf-8")
        assert db.is_file()
        ui_pid = state / "taskboard" / "ui.pid"
        mcp_pid = state / "taskboard" / "mcp-http.pid"
        assert not ui_pid.exists()
        assert not mcp_pid.exists()
    finally:
        _stop(env)


def test_setup_taskboard_wipe_clears_db_keeps_inbox_and_studio_env(
    tmp_path: Path,
) -> None:
    fake, log = _fake_taskboard(tmp_path)
    env = _base_env(tmp_path, taskboard_bin=fake)
    env["GCS_TASKBOARD_WIPE"] = "1"
    state = Path(env["GCS_A2A_STATE"])
    studio = state / "studio.env"
    studio.write_text("GCS_MIND_SEATS=\n# keep-studio-env\n", encoding="utf-8")
    inbox = state / "floor" / "inbox.jsonl"
    inbox.parent.mkdir(parents=True, exist_ok=True)
    inbox.write_text("{}\n", encoding="utf-8")
    pin = state / "floor" / "mind" / "session"
    pin.parent.mkdir(parents=True, exist_ok=True)
    pin.write_text("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\n", encoding="utf-8")
    db = state / "taskboard" / "taskboard.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_text("db\n", encoding="utf-8")
    try:
        proc = _run(SETUP_TB, ["wipe"], env)
        blob = proc.stdout + proc.stderr
        assert proc.returncode == 0, blob
        assert "TASKBOARD_WIPE_OK" in blob
        recorded = log.read_text(encoding="utf-8") if log.is_file() else ""
        assert "clear" in recorded
        assert "-f" in recorded
        assert str(db) in recorded
        assert not db.exists()
        assert inbox.is_file()
        assert pin.is_file()
        assert studio.is_file()
        assert "keep-studio-env" in studio.read_text(encoding="utf-8")
        assert env["CURSOR_API_KEY"] not in blob
        assert PRIVATE_GAME not in blob
    finally:
        _stop(env)


def test_setup_taskboard_wipe_removes_sqlite_sidecars(tmp_path: Path) -> None:
    fake, _log = _fake_taskboard(tmp_path)
    env = _base_env(tmp_path, taskboard_bin=fake)
    env["GCS_TASKBOARD_WIPE"] = "1"
    state = Path(env["GCS_A2A_STATE"])
    db = state / "taskboard" / "taskboard.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_text("db\n", encoding="utf-8")
    wal = Path(str(db) + "-wal")
    shm = Path(str(db) + "-shm")
    journal = Path(str(db) + "-journal")
    wal.write_text("wal\n", encoding="utf-8")
    shm.write_text("shm\n", encoding="utf-8")
    journal.write_text("journal\n", encoding="utf-8")
    try:
        proc = _run(SETUP_TB, ["wipe"], env)
        blob = proc.stdout + proc.stderr
        assert proc.returncode == 0, blob
        assert "TASKBOARD_WIPE_OK" in blob
        assert not db.exists()
        assert not wal.exists()
        assert not shm.exists()
        assert not journal.exists()
    finally:
        _stop(env)


def test_setup_taskboard_ready_fail_stops_board(tmp_path: Path) -> None:
    fake, _log = _fake_taskboard(tmp_path)
    env = _base_env(tmp_path, taskboard_bin=fake)
    env.pop("GCS_TASKBOARD_SKIP_READY", None)
    env["GCS_TASKBOARD_READY_TRIES"] = "2"
    env["GCS_TASKBOARD_UI_PORT"] = str(_free_port())
    env["GCS_TASKBOARD_MCP_PORT"] = str(_free_port())
    state = Path(env["GCS_A2A_STATE"])
    try:
        proc = _run(SETUP_TB, ["start"], env)
        blob = proc.stdout + proc.stderr
        assert proc.returncode != 0, blob
        assert "TASKBOARD_SETUP_FAIL" in blob
        assert "TASKBOARD_SETUP_OK" not in blob
        assert not (state / "taskboard" / "ui.pid").exists()
        assert not (state / "taskboard" / "mcp-http.pid").exists()
    finally:
        _stop(env)


def test_setup_forwards_submodule_skip_to_board_setup() -> None:
    text = SETUP.read_text(encoding="utf-8")
    assert "GCS_SETUP_SKIP_SUBMODULE" in text
    assert "GCS_TASKBOARD_SKIP_SUBMODULE" in text


def test_setup_taskboard_wipe_refuses_without_flag(tmp_path: Path) -> None:
    fake, _log = _fake_taskboard(tmp_path)
    env = _base_env(tmp_path, taskboard_bin=fake)
    state = Path(env["GCS_A2A_STATE"])
    db = state / "taskboard" / "taskboard.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_text("db\n", encoding="utf-8")
    proc = _run(SETUP_TB, ["wipe"], env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode != 0, blob
    assert db.is_file()
    assert "TASKBOARD_WIPE_OK" not in blob


def test_setup_taskboard_ak_refuse_start_and_wipe(tmp_path: Path) -> None:
    fake, log = _fake_taskboard(tmp_path)
    env = _base_env(tmp_path, taskboard_bin=fake)
    kit = Path(env["GCS_ROOT"])
    planted = kit / "scripts" / "studio" / "agent-kanban"
    planted.mkdir(parents=True)
    (planted / "ak").write_text("nope\n", encoding="utf-8")
    env["GCS_TASKBOARD_WIPE"] = "1"
    try:
        start = _run(SETUP_TB, ["start"], env)
        blob = start.stdout + start.stderr
        assert start.returncode != 0, blob
        assert "AK_REFUSE" in blob
        assert "ak start" not in blob
        wipe = _run(SETUP_TB, ["wipe"], env)
        wblob = wipe.stdout + wipe.stderr
        assert wipe.returncode != 0, wblob
        assert "AK_REFUSE" in wblob
        recorded = log.read_text(encoding="utf-8") if log.is_file() else ""
        assert "start" not in recorded
        assert "clear" not in recorded
    finally:
        _stop(env)


def test_setup_and_cleanup_delegate_to_setup_taskboard() -> None:
    setup = SETUP.read_text(encoding="utf-8")
    cleanup = CLEANUP.read_text(encoding="utf-8")
    assert "setup-taskboard.sh" in setup
    assert "setup-taskboard.sh" in cleanup
    assert "start-studio-bus.sh start --daemons" not in setup
    assert "agent-kanban" not in setup
    assert "ak start" not in setup
    assert "ak start" not in cleanup
    # cleanup wipe uses the board wipe path, not only rm of the sqlite file.
    assert "wipe" in cleanup.lower()
    assert "CLEANUP_WIPE_STATE" in cleanup
    # Distinct from sibling kits: DR entrypoints do not grow PIN/upgrade or maintainer health.
    assert "upgrade-taskboard.sh" not in setup
    assert "maintainer.sh" not in setup
    assert "health-taskboard.sh" not in setup
    assert "upgrade-taskboard.sh" not in cleanup
    assert "maintainer.sh" not in cleanup


def test_cleanup_wipe_state_calls_setup_taskboard_wipe(tmp_path: Path) -> None:
    fake, log = _fake_taskboard(tmp_path)
    env = _base_env(tmp_path, taskboard_bin=fake)
    env["CLEANUP_WIPE_STATE"] = "1"
    env["GCS_SETUP_SKIP_INSTALL"] = "1"
    env["GCS_SETUP_SKIP_START"] = "1"
    env["GCS_SETUP_SKIP_DOCTOR"] = "1"
    env["GCS_BOT_BIND_OPTIONAL"] = "1"
    state = Path(env["GCS_A2A_STATE"])
    studio = state / "studio.env"
    studio.write_text("GCS_MIND_SEATS=\n# keep-studio-env\n", encoding="utf-8")
    inbox = state / "floor" / "inbox.jsonl"
    inbox.parent.mkdir(parents=True, exist_ok=True)
    inbox.write_text("{}\n", encoding="utf-8")
    pin = state / "floor" / "mind" / "session"
    pin.parent.mkdir(parents=True, exist_ok=True)
    pin.write_text("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\n", encoding="utf-8")
    db = state / "taskboard" / "taskboard.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_text("db\n", encoding="utf-8")
    proc = _run(CLEANUP, [], env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "CLEANUP_OK" in blob
    recorded = log.read_text(encoding="utf-8") if log.is_file() else ""
    assert "clear" in recorded
    assert not db.exists()
    assert not inbox.exists()
    assert not pin.exists()
    assert studio.is_file()
    assert "keep-studio-env" in studio.read_text(encoding="utf-8")


def test_docs_and_doctor_name_setup_taskboard_and_host_ticket() -> None:
    wipe = WIPE.read_text(encoding="utf-8")
    doc = TASKBOARD_DOC.read_text(encoding="utf-8")
    readme = TB_README.read_text(encoding="utf-8")
    doctor = DOCTOR.read_text(encoding="utf-8")
    install = INSTALL.read_text(encoding="utf-8")
    for label, text in (("WIPE.md", wipe), ("TASKBOARD.md", doc), ("taskboard README", readme)):
        assert "setup-taskboard.sh" in text, label
        assert "ticket" in text.lower(), label
        assert PRIVATE_GAME not in text
        assert "Living Sky" in text or "linear.app/livingsky" in text or "Livingsky" in text, label
    assert "setup-taskboard.sh" in doctor
    assert "scripts/studio/taskboard/ticket" in doctor or "taskboard/ticket" in doctor
    assert "setup-taskboard.sh" in install or "taskboard/*.sh" in install
    fold = " ".join(wipe.lower().split())
    assert "setup-taskboard.sh" in fold
    assert "ak start" not in wipe
    gitignore = GITIGNORE.read_text(encoding="utf-8")
    assert "/bin/ticket" in gitignore or "bin/ticket" in gitignore
    assert "/bin/tb" in gitignore or "bin/tb" in gitignore


def test_recover_still_uses_leaf_start_scripts_not_install() -> None:
    """Recover restarts down UI/MCP; it must not brew/tarball/submodule as a side effect."""
    text = RECOVER.read_text(encoding="utf-8")
    assert "start-taskboard.sh" in text
    assert "mcp-http.sh" in text
    assert "install-taskboard.sh" not in text
    assert "upgrade-taskboard.sh" not in text
    assert "maintainer.sh" not in text


def test_common_sh_skips_wrapper_tagged_binaries(tmp_path: Path) -> None:
    kit = tmp_path / "kit"
    wrapped = kit / "bin" / "taskboard"
    _write_exec(
        wrapped,
        "#!/bin/bash\n# gcs-host-taskboard-wrapper\nexit 0\n",
    )
    real = tmp_path / "real" / "taskboard"
    _write_exec(real, "#!/bin/sh\nexit 0\n")
    env = {
        "PATH": f"{real.parent}:/usr/bin:/bin",
        "HOME": str(tmp_path / "home"),
        "GCS_ROOT": str(kit),
        "LC_ALL": "C",
        "TERM": "dumb",
    }
    script = (
        "set -euo pipefail\n"
        f"source {COMMON_SH}\n"
        "gcs_taskboard_bin\n"
    )
    proc = subprocess.run(
        ["bash", "-c", script],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert str(real) in proc.stdout.strip()
    assert str(wrapped) not in proc.stdout
