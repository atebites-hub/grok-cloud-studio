"""Doctor lints existing GROK_HOME taskboard stdio catalogs.

Unique remaining slice vs OPEN GCS #100 (factory mcp-seats / setup.sh write).
This module does not add mcp-seats, does not call setup.sh, and does not
start grok agent serve. Fake TOML only. Living Sky LIV. Never Bot CloudAgent.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SEAT_GROK_MCP = REPO / "scripts" / "directors" / "seat_grok_mcp.py"
DOCTOR = REPO / "doctor.sh"
FEATURE = REPO / "tests" / "features" / "seat_taskboard_mcp_catalog_hygiene.feature"
TASKBOARD_DOC = REPO / "docs" / "studio" / "TASKBOARD.md"
WORKSPACE_FOLDER_TOKEN = "${" + "workspaceFolder}"


def _mod():
    spec = importlib.util.spec_from_file_location("gcs_seat_grok_mcp_lint", SEAT_GROK_MCP)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _doctor_env(tmp_path: Path) -> dict[str, str]:
    env = {
        **os.environ,
        "GCS_ROOT": str(REPO),
        "GCS_A2A_STATE": str(tmp_path / "a2a-state"),
        "GCS_BOT_BIND_OPTIONAL": "1",
        "LC_ALL": "C",
        "TERM": "dumb",
    }
    env.pop("GROK_HOME", None)
    return env


def _run_doctor(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(DOCTOR)],
        cwd=str(REPO),
        env=_doctor_env(tmp_path),
        capture_output=True,
        text=True,
        timeout=30,
    )


def _write_seat_cfg(tmp_path: Path, text: str, seat: str = "floor") -> Path:
    path = tmp_path / "a2a-state" / seat / "grok-home" / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_bdd_feature_binds_hygiene_scenarios() -> None:
    assert FEATURE.is_file(), "missing tests/features/seat_taskboard_mcp_catalog_hygiene.feature"
    text = FEATURE.read_text(encoding="utf-8")
    assert "GROK_HOME" in text
    assert "config.toml" in text
    assert "--db" in text and "mcp" in text
    assert "missing-taskboard-table" in text
    assert "args-not-db-mcp" in text
    assert "OPEN #100" in text or "mcp-seats" in text
    assert "workspaceFolder" in text
    assert "Living Sky" in text or "LIV" in text
    assert "Bot CloudAgent" in text
    for title in (
        "missing taskboard table is a WARN not a FAIL",
        "missing mcp arg is a WARN",
        "relative db path is a WARN",
        "healthy absolute stdio catalog is quiet",
    ):
        assert title in text, title
    assert "db-not-absolute" in text
    assert "WARN seat MCP catalog missing-taskboard-table" in text


def test_lint_seat_taskboard_mcp_flags_missing_table() -> None:
    reasons = _mod().lint_seat_taskboard_mcp("[cli]\nuse_leader = true\n")
    assert "missing-taskboard-table" in reasons


def test_lint_seat_taskboard_mcp_flags_args_not_db_mcp() -> None:
    text = (
        "[mcp_servers.taskboard]\n"
        'command = "/usr/bin/taskboard"\n'
        'args = ["mcp"]\n'
    )
    reasons = _mod().lint_seat_taskboard_mcp(text)
    assert "args-not-db-mcp" in reasons


def test_lint_seat_taskboard_mcp_flags_relative_db() -> None:
    text = (
        "[mcp_servers.taskboard]\n"
        'command = "/usr/bin/taskboard"\n'
        'args = ["--db", "taskboard.db", "mcp"]\n'
    )
    reasons = _mod().lint_seat_taskboard_mcp(text)
    assert "db-not-absolute" in reasons


def test_lint_seat_taskboard_mcp_flags_command_not_absolute() -> None:
    text = (
        "[mcp_servers.taskboard]\n"
        'command = "taskboard"\n'
        'args = ["--db", "/tmp/taskboard.db", "mcp"]\n'
    )
    reasons = _mod().lint_seat_taskboard_mcp(text)
    assert "command-not-absolute" in reasons


def test_lint_does_not_reject_linear_http_beside_taskboard() -> None:
    """PAL-45 Linear MCP is not this slice; do not fail a grok Linear table."""
    text = (
        "[mcp_servers.linear]\n"
        'url = "https://mcp.linear.app/mcp"\n'
        "\n"
        "[mcp_servers.taskboard]\n"
        'command = "/bin/taskboard"\n'
        'args = ["--db", "/tmp/taskboard.db", "mcp"]\n'
    )
    assert _mod().lint_seat_taskboard_mcp(text) == []


def test_lint_seat_taskboard_mcp_accepts_merge_output() -> None:
    mod = _mod()
    text = mod.merge_seat_taskboard_mcp("", "/bin/taskboard", "/tmp/taskboard.db")
    assert mod.lint_seat_taskboard_mcp(text) == []


def test_lint_seat_taskboard_mcp_flags_invalid_toml() -> None:
    reasons = _mod().lint_seat_taskboard_mcp("this is not = toml [")
    assert "invalid-toml" in reasons


def test_lint_cli_prints_reasons_and_keeps_write_usage(tmp_path: Path) -> None:
    dest = tmp_path / "config.toml"
    dest.write_text("[cli]\nuse_leader = true\n", encoding="utf-8")
    lint = subprocess.run(
        ["python3", str(SEAT_GROK_MCP), "lint", str(dest)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert lint.returncode == 0, lint.stderr
    assert "missing-taskboard-table" in lint.stdout
    help_proc = subprocess.run(
        ["python3", str(SEAT_GROK_MCP)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert help_proc.returncode == 2
    blob = help_proc.stdout + help_proc.stderr
    assert "DEST_TOML COMMAND DB" in blob
    assert "lint" in blob


def test_doctor_warns_on_missing_taskboard_table_not_fail(tmp_path: Path) -> None:
    doctor_src = DOCTOR.read_text(encoding="utf-8")
    assert "scripts/directors/seat_grok_mcp.py" in doctor_src
    assert "lint-failed" in doctor_src
    assert "2>/dev/null || true" not in doctor_src.split("_gcs_warn_seat_taskboard_mcp_catalog()")[1].split("mcp_configs=")[0]
    _write_seat_cfg(tmp_path, "[cli]\nuse_leader = true\n")
    proc = _run_doctor(tmp_path)
    blob = proc.stdout + proc.stderr
    assert "WARN seat MCP catalog missing-taskboard-table:" in blob, blob
    assert "config.toml" in blob, blob
    assert "doctor: OK" in blob, blob
    assert proc.returncode == 0, blob
    assert not any(
        ln.startswith("ERR") and "missing-taskboard-table" in ln
        for ln in blob.splitlines()
    )


def test_doctor_warns_on_args_not_db_mcp(tmp_path: Path) -> None:
    _write_seat_cfg(
        tmp_path,
        "[mcp_servers.taskboard]\n"
        'command = "/usr/bin/taskboard"\n'
        'args = ["stdio"]\n',
    )
    proc = _run_doctor(tmp_path)
    blob = proc.stdout + proc.stderr
    assert "WARN seat MCP catalog args-not-db-mcp:" in blob, blob
    assert "doctor: OK" in blob, blob
    assert proc.returncode == 0, blob


def test_doctor_warns_on_relative_db(tmp_path: Path) -> None:
    _write_seat_cfg(
        tmp_path,
        "[mcp_servers.taskboard]\n"
        'command = "/usr/bin/taskboard"\n'
        'args = ["--db", "taskboard.db", "mcp"]\n',
    )
    proc = _run_doctor(tmp_path)
    blob = proc.stdout + proc.stderr
    assert "WARN seat MCP catalog db-not-absolute:" in blob, blob
    assert "doctor: OK" in blob, blob
    assert proc.returncode == 0, blob


def test_doctor_quiet_on_healthy_absolute_stdio_catalog(tmp_path: Path) -> None:
    _write_seat_cfg(
        tmp_path,
        "# gcs-seat-taskboard-mcp\n"
        "[compat.cursor]\n"
        "mcps = false\n"
        "\n"
        "[mcp_servers.taskboard]\n"
        'command = "/usr/bin/taskboard"\n'
        'args = ["--db", "/tmp/taskboard.db", "mcp"]\n'
        "# gcs-seat-taskboard-mcp-end\n",
    )
    proc = _run_doctor(tmp_path)
    blob = proc.stdout + proc.stderr
    assert "missing-taskboard-table" not in blob, blob
    assert "args-not-db-mcp" not in blob, blob
    assert "db-not-absolute" not in blob, blob
    assert "command-not-absolute" not in blob, blob
    assert WORKSPACE_FOLDER_TOKEN not in blob


def test_docs_name_catalog_hygiene_not_cursor_workspace() -> None:
    doc = TASKBOARD_DOC.read_text(encoding="utf-8")
    assert "GROK_HOME" in doc
    assert "config.toml" in doc
    assert "missing-taskboard-table" in doc
    assert "args-not-db-mcp" in doc
    assert "db-not-absolute" in doc
    assert "seat_grok_mcp.py lint" in doc
    assert "never" in doc.lower()
    assert WORKSPACE_FOLDER_TOKEN not in doc or "never" in doc.lower()
