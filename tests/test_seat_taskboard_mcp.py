"""Seat start must register taskboard stdio MCP in GROK_HOME/config.toml.

Isolated GROK_HOME does not inherit ~/.grok/config.toml. Cursor workspace
MCP paths with ${workspaceFolder} never expand and must not be the serve
config. Fake binary only — no live grok serve, no live ticket moves.
"""
from __future__ import annotations

import importlib.util
import os
import stat
import subprocess
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SEAT_COMMON = REPO / "scripts" / "directors" / "seat-daemon-common.sh"
START_DAEMON = REPO / "scripts" / "directors" / "start-seat-daemon.sh"
INSTALL_GROK_MCP = REPO / "scripts" / "directors" / "install-grok-mcp.sh"
DOCTOR = REPO / "doctor.sh"
TASKBOARD_DOC = REPO / "docs" / "studio" / "TASKBOARD.md"

WORKSPACE_FOLDER_TOKEN = "${" + "workspaceFolder}"
BANNED_BOX = "/home/" + "box"
BANNED_WORKSPACE_PRIVATE = "/workspace/" + "pale" + "mon"


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
    env = {
        "PATH": extra_path or "/usr/bin:/bin",
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


def _read_seat_config(path: Path) -> str:
    assert path.is_file(), f"missing seat MCP config: {path}"
    return path.read_text(encoding="utf-8")


def test_identity_install_writes_absolute_db_stdio_mcp(tmp_path: Path) -> None:
    binary, _log = _fake_taskboard(tmp_path)
    env = _base_env(tmp_path, taskboard_bin=binary)
    db = tmp_path / "a2a-state" / "taskboard" / "taskboard.db"
    script = r"""
set -euo pipefail
source scripts/directors/seat-daemon-common.sh
install_seat_identity floor
printf 'GROK_HOME=%s\n' "$GROK_HOME"
printf 'DB=%s\n' "${GCS_TASKBOARD_DB}"
"""
    proc = _run_seat_bash(script, env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    grok_home = Path(env["GROK_HOME"])
    cfg = grok_home / "config.toml"
    text = _read_seat_config(cfg)
    assert WORKSPACE_FOLDER_TOKEN not in text, text
    assert str(binary.resolve()) in text, text
    assert str(db) in text, text
    assert "--db" in text, text
    assert "mcp" in text, text
    assert "[mcp_servers.taskboard]" in text, text
    assert "[mcp_servers.linear]" in text, text
    assert "https://mcp.linear.app/mcp" in text, text
    assert "${LINEAR_API_KEY}" in text, text
    assert f'command = "{binary.resolve()}"' in text or f"command = '{binary.resolve()}'" in text or str(
        binary.resolve()
    ) in text
    assert text.strip().startswith("/") is False
    # args must be stdio: --db <absolute db> mcp
    assert "--db" in text and "mcp" in text
    lowered = text.lower()
    assert BANNED_BOX not in text
    assert BANNED_WORKSPACE_PRIVATE not in lowered
    assert ".cursor/mcp.json" not in text
    assert "SEAT_GROK_MCP_OK" in blob or "mcp_servers" in blob.lower() or cfg.is_file()


def test_export_seat_serve_env_registers_mcp_without_workspace_folder(tmp_path: Path) -> None:
    binary, _log = _fake_taskboard(tmp_path)
    env = _base_env(tmp_path, taskboard_bin=binary)
    db = tmp_path / "a2a-state" / "taskboard" / "taskboard.db"
    script = r"""
set -euo pipefail
source scripts/directors/seat-daemon-common.sh
export_seat_serve_env floor
"""
    proc = _run_seat_bash(script, env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    text = _read_seat_config(Path(env["GROK_HOME"]) / "config.toml")
    assert WORKSPACE_FOLDER_TOKEN not in text
    assert str(db) in text
    assert str(binary.resolve()) in text
    assert "[mcp_servers.taskboard]" in text
    assert "[mcp_servers.linear]" in text
    assert "https://mcp.linear.app/mcp" in text
    assert "${LINEAR_API_KEY}" in text


def test_default_grok_home_under_state_dir_gets_mcp(tmp_path: Path) -> None:
    """Live seats use $sd/grok-home when GROK_HOME is unset."""
    binary, _log = _fake_taskboard(tmp_path)
    env = _base_env(tmp_path, taskboard_bin=binary)
    env.pop("GROK_HOME", None)
    db = tmp_path / "a2a-state" / "taskboard" / "taskboard.db"
    script = r"""
set -euo pipefail
source scripts/directors/seat-daemon-common.sh
install_seat_identity floor
"""
    proc = _run_seat_bash(script, env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    cfg = tmp_path / "a2a-state" / "floor" / "grok-home" / "config.toml"
    text = _read_seat_config(cfg)
    assert WORKSPACE_FOLDER_TOKEN not in text
    assert str(db) in text
    assert str(binary.resolve()) in text
    assert "[mcp_servers.taskboard]" in text
    assert "[mcp_servers.linear]" in text
    assert "https://mcp.linear.app/mcp" in text
    assert "${LINEAR_API_KEY}" in text


def test_mcp_install_is_idempotent_and_preserves_other_toml(tmp_path: Path) -> None:
    binary, _log = _fake_taskboard(tmp_path)
    env = _base_env(tmp_path, taskboard_bin=binary)
    grok_home = Path(env["GROK_HOME"])
    grok_home.mkdir(parents=True, exist_ok=True)
    existing = grok_home / "config.toml"
    existing.write_text("[cli]\nuse_leader = true\n", encoding="utf-8")
    script = r"""
set -euo pipefail
source scripts/directors/seat-daemon-common.sh
install_seat_grok_mcp floor
install_seat_grok_mcp floor
"""
    proc = _run_seat_bash(script, env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    text = _read_seat_config(existing)
    assert text.count("[mcp_servers.taskboard]") == 1, text
    assert text.count("[compat.cursor]") == 1, text
    assert text.count("# gcs-seat-taskboard-mcp\n") == 1, text
    assert text.count("# gcs-seat-taskboard-mcp-end") == 1, text
    assert "use_leader = true" in text
    assert WORKSPACE_FOLDER_TOKEN not in text
    parsed = tomllib.loads(text)
    assert parsed["cli"]["use_leader"] is True
    assert parsed["compat"]["cursor"]["mcps"] is False
    assert parsed["mcp_servers"]["taskboard"]["command"]
    assert parsed["mcp_servers"]["linear"]["url"] == "https://mcp.linear.app/mcp"
    assert text.count("[mcp_servers.linear]") == 1, text


def test_mcp_install_idempotent_when_unmarked_tables_already_exist(
    tmp_path: Path,
) -> None:
    """Grok rewrite drops markers; a second write must not duplicate tables."""
    binary, _log = _fake_taskboard(tmp_path)
    env = _base_env(tmp_path, taskboard_bin=binary)
    grok_home = Path(env["GROK_HOME"])
    grok_home.mkdir(parents=True, exist_ok=True)
    existing = grok_home / "config.toml"
    existing.write_text(
        "[cli]\n"
        "use_leader = true\n"
        "\n"
        "[compat.cursor]\n"
        "mcps = false\n"
        "\n"
        "[mcp_servers.taskboard]\n"
        'command = "/old/taskboard"\n'
        'args = ["--db", "/old/taskboard.db", "mcp"]\n'
        "\n"
        "# gcs-seat-taskboard-mcp\n"
        "[compat.cursor]\n"
        "mcps = false\n"
        "\n"
        "[mcp_servers.taskboard]\n"
        'command = "/also-old/taskboard"\n'
        'args = ["--db", "/also-old.db", "mcp"]\n'
        "# gcs-seat-taskboard-mcp-end\n",
        encoding="utf-8",
    )
    script = r"""
set -euo pipefail
source scripts/directors/seat-daemon-common.sh
install_seat_grok_mcp floor
install_seat_grok_mcp floor
"""
    proc = _run_seat_bash(script, env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    text = _read_seat_config(existing)
    assert text.count("[mcp_servers.taskboard]") == 1, text
    assert text.count("[compat.cursor]") == 1, text
    assert text.count("# gcs-seat-taskboard-mcp\n") == 1, text
    assert text.count("# gcs-seat-taskboard-mcp-end") == 1, text
    assert "use_leader = true" in text
    assert "/old/taskboard" not in text
    assert "/also-old" not in text
    parsed = tomllib.loads(text)
    assert parsed["cli"]["use_leader"] is True
    assert parsed["compat"]["cursor"]["mcps"] is False
    command = parsed["mcp_servers"]["taskboard"]["command"]
    assert str(binary.resolve()) == command or str(binary) in str(command)
    assert parsed["mcp_servers"]["taskboard"]["args"][-1] == "mcp"


def test_cursor_compat_mcps_disabled_in_seat_config(tmp_path: Path) -> None:
    """Grok must not load Cursor .cursor/mcp.json (${workspaceFolder} never expands)."""
    binary, _log = _fake_taskboard(tmp_path)
    env = _base_env(tmp_path, taskboard_bin=binary)
    script = r"""
set -euo pipefail
source scripts/directors/seat-daemon-common.sh
install_seat_grok_mcp floor
"""
    proc = _run_seat_bash(script, env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    text = _read_seat_config(Path(env["GROK_HOME"]) / "config.toml")
    assert "[compat.cursor]" in text, text
    assert "mcps = false" in text, text
    assert WORKSPACE_FOLDER_TOKEN not in text


def test_seat_mcp_wiring_sources_have_no_workspace_folder_token() -> None:
    common = SEAT_COMMON.read_text(encoding="utf-8")
    daemon = START_DAEMON.read_text(encoding="utf-8")
    installer = INSTALL_GROK_MCP.read_text(encoding="utf-8")
    assert WORKSPACE_FOLDER_TOKEN not in common
    assert WORKSPACE_FOLDER_TOKEN not in daemon
    assert WORKSPACE_FOLDER_TOKEN not in installer
    assert BANNED_BOX not in common
    assert BANNED_WORKSPACE_PRIVATE not in common
    identity_fn = common.split("install_seat_identity() {", 1)[1]
    assert "install_seat_grok_mcp" in identity_fn
    assert "install_seat_grok_mcp" in common
    assert "mcp_servers" in common
    assert "seat_grok_mcp.py" in common
    assert "GCS_TASKBOARD_DB" in common
    assert "export_seat_serve_env" in daemon
    already = daemon.split("SEAT_DAEMON_ALREADY")[0]
    assert "export_seat_serve_env" in already or "install_seat_identity" in already
    after_already = daemon.split("SEAT_DAEMON_ALREADY", 1)[1]
    assert "kill" not in after_already.split("SEAT_DAEMON_STALE_KILL")[0]
    doc = TASKBOARD_DOC.read_text(encoding="utf-8")
    assert "GROK_HOME" in doc
    assert "config.toml" in doc
    assert "mcp" in doc.lower()
    assert WORKSPACE_FOLDER_TOKEN not in doc or "never" in doc.lower()


def test_install_grok_mcp_script_does_not_start_serve() -> None:
    text = INSTALL_GROK_MCP.read_text(encoding="utf-8")
    assert "install_seat_grok_mcp" in text
    assert "grok agent serve" not in text
    assert "start-seat-daemon" not in text


def test_doctor_warns_on_workspace_folder_in_seat_mcp(tmp_path: Path) -> None:
    doctor = DOCTOR.read_text(encoding="utf-8")
    assert WORKSPACE_FOLDER_TOKEN in doctor
    assert "WARN" in doctor
    assert "mcp" in doctor.lower() or "GROK_HOME" in doctor or "config.toml" in doctor

    poisoned = tmp_path / "a2a-state" / "floor" / "grok-home" / "config.toml"
    poisoned.parent.mkdir(parents=True, exist_ok=True)
    poisoned.write_text(
        "[mcp_servers.taskboard]\n"
        f'command = "bash"\n'
        f'args = ["{WORKSPACE_FOLDER_TOKEN}/plugins/taskboard/run-mcp.sh"]\n',
        encoding="utf-8",
    )
    env = {
        **os.environ,
        "GCS_ROOT": str(REPO),
        "GCS_A2A_STATE": str(tmp_path / "a2a-state"),
        "GCS_BOT_BIND_OPTIONAL": "1",
        "LC_ALL": "C",
        "TERM": "dumb",
    }
    proc = subprocess.run(
        ["bash", str(DOCTOR)],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    blob = proc.stdout + proc.stderr
    assert "WARN" in blob, blob
    assert WORKSPACE_FOLDER_TOKEN in blob, blob
    assert "config.toml" in blob, blob


def test_merge_seat_taskboard_mcp_strips_unmarked_and_marked_dupes(tmp_path: Path) -> None:
    spec_path = REPO / "scripts" / "directors" / "seat_grok_mcp.py"
    spec = importlib.util.spec_from_file_location("gcs_seat_grok_mcp", spec_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    poisoned = (
        "[cli]\nuse_leader = true\n\n"
        "[compat.cursor]\nmcps = true\n\n"
        "[mcp_servers.taskboard]\n"
        'command = "/stale"\n'
        'args = ["mcp"]\n\n'
        "# gcs-seat-taskboard-mcp\n"
        "[compat.cursor]\nmcps = false\n\n"
        "[mcp_servers.taskboard]\n"
        'command = "/also-stale"\n'
        "# gcs-seat-taskboard-mcp-end\n"
    )
    out = mod.merge_seat_taskboard_mcp(poisoned, "/bin/taskboard", "/tmp/db")
    parsed = tomllib.loads(out)
    assert parsed["cli"]["use_leader"] is True
    assert parsed["compat"]["cursor"]["mcps"] is False
    assert parsed["mcp_servers"]["taskboard"]["command"] == "/bin/taskboard"
    assert out.count("[compat.cursor]") == 1
    assert out.count("[mcp_servers.taskboard]") == 1
    again = mod.merge_seat_taskboard_mcp(out, "/bin/taskboard", "/tmp/db")
    assert tomllib.loads(again)["mcp_servers"]["taskboard"]["command"] == "/bin/taskboard"
    assert again.count("[mcp_servers.taskboard]") == 1
