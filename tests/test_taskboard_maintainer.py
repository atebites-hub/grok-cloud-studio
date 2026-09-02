"""LIV-86: studio-ops maintainer kit for tcarac/taskboard.

Distinct from merged #112 fleet-shepherd TASKBOARD_HEALTH. Does not remint the
v0.6.0 vendor/taskboard pin. Ticket move uses Crockford ULID. Agent Kanban
stays gone. Seat stdio MCP stays in isolated GROK_HOME/config.toml.
"""
from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TASKBOARD_DIR = REPO / "scripts" / "studio" / "taskboard"
PIN_FILE = TASKBOARD_DIR / "PIN"
COMMON_SH = TASKBOARD_DIR / "common.sh"
INSTALL_TB = TASKBOARD_DIR / "install-taskboard.sh"
UPGRADE_TB = TASKBOARD_DIR / "upgrade-taskboard.sh"
TB_README = TASKBOARD_DIR / "README.md"
TASKBOARD_DOC = REPO / "docs" / "studio" / "TASKBOARD.md"
WIPE_DOC = REPO / "docs" / "studio" / "WIPE.md"
GITMODULES = REPO / ".gitmodules"
DASHBOARD_README = REPO / "scripts" / "studio" / "dashboard" / "README.md"
SEAT_COMMON = REPO / "scripts" / "directors" / "seat-daemon-common.sh"
MIND_PY = REPO / "scripts" / "directors" / "mind.py"
STUDIO_OPS_SOUL = REPO / "docs" / "studio" / "directors" / "souls" / "studio-ops" / "SOUL.md"
FLEET_SHEPHERD = REPO / "scripts" / "directors" / "fleet-shepherd.py"
CURSOR_MCP = REPO / ".cursor" / "mcp.json"

PINNED_TAG = "v0.6.0"
SAMPLE_ULID = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")
WORKSPACE_FOLDER_TOKEN = "${" + "workspaceFolder}"


def _write_exec(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def _run(
    argv: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
    timeout: int = 15,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=str(cwd or REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _base_env(tmp_path: Path, **extra: str) -> dict[str, str]:
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path / "home"),
        "GCS_ROOT": str(REPO),
        "GCS_A2A_STATE": str(tmp_path / "a2a-state"),
        "LC_ALL": "C",
        "TERM": "dumb",
    }
    env.update(extra)
    return env


def _fake_kit(tmp_path: Path, *, pin: str = PINNED_TAG, plant_ak: bool = False) -> Path:
    kit = tmp_path / "kit"
    tb = kit / "scripts" / "studio" / "taskboard"
    tb.mkdir(parents=True)
    (tb / "PIN").write_text(f"# pin\n{pin}\n", encoding="utf-8")
    (kit / ".gitmodules").write_text(
        "[submodule \"vendor/taskboard\"]\n"
        "\tpath = vendor/taskboard\n"
        "\turl = https://github.com/tcarac/taskboard.git\n"
        f"\tbranch = {pin}\n",
        encoding="utf-8",
    )
    (kit / "scripts" / "studio" / "dashboard").mkdir(parents=True)
    (kit / "scripts" / "studio" / "dashboard" / "README.md").write_text(
        "# LEGACY studio dashboard\n",
        encoding="utf-8",
    )
    if plant_ak:
        ak = kit / "scripts" / "studio" / "agent-kanban"
        ak.mkdir(parents=True)
        (ak / "ak").write_text("#!/bin/sh\necho AK_RECONNECT\n", encoding="utf-8")
    return kit


def test_pin_file_is_single_source_v060_not_floating_main() -> None:
    assert PIN_FILE.is_file(), "missing scripts/studio/taskboard/PIN"
    lines = [
        ln.strip()
        for ln in PIN_FILE.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    assert lines == [PINNED_TAG], lines
    gm = GITMODULES.read_text(encoding="utf-8")
    assert "vendor/taskboard" in gm
    assert "tcarac/taskboard" in gm
    assert f"branch = {PINNED_TAG}" in gm
    assert "branch = main" not in gm
    assert "branch = master" not in gm


def test_common_sh_reads_pin_file() -> None:
    text = COMMON_SH.read_text(encoding="utf-8")
    assert "gcs_taskboard_pin" in text
    assert "gcs_taskboard_pin_file" in text
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": "/tmp",
        "GCS_ROOT": str(REPO),
        "LC_ALL": "C",
        "TERM": "dumb",
    }
    proc = _run(
        ["bash", "-c", f"source {COMMON_SH} && gcs_taskboard_pin && gcs_taskboard_pin_file"],
        env=env,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    assert PINNED_TAG in lines, blob
    assert any(ln.endswith("scripts/studio/taskboard/PIN") for ln in lines), blob


def test_install_taskboard_uses_pin_not_snowflake_version() -> None:
    text = INSTALL_TB.read_text(encoding="utf-8")
    assert "gcs_taskboard_pin" in text
    assert "TASKBOARD_VERSION" in text
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": "/tmp",
        "GCS_ROOT": str(REPO),
        "LC_ALL": "C",
        "TERM": "dumb",
    }
    proc = _run(
        [
            "bash",
            "-c",
            f"source {COMMON_SH} && echo VERSION=${{TASKBOARD_VERSION:-$(gcs_taskboard_pin)}}",
        ],
        env=env,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert f"VERSION={PINNED_TAG}" in proc.stdout, blob


def test_upgrade_check_passes_on_current_pin() -> None:
    assert UPGRADE_TB.is_file()
    env = {
        **os.environ,
        "GCS_ROOT": str(REPO),
        "LC_ALL": "C",
        "TERM": "dumb",
    }
    proc = _run(["bash", str(UPGRADE_TB), "--check"], env=env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "TASKBOARD_PIN_OK" in blob, blob
    assert PINNED_TAG in blob, blob
    assert "agent-kanban" not in blob.lower() or "AK_REFUSE" not in blob


def test_upgrade_dry_run_does_not_mutate_pin(tmp_path: Path) -> None:
    before = PIN_FILE.read_text(encoding="utf-8")
    gm_before = GITMODULES.read_text(encoding="utf-8")
    env = _base_env(tmp_path)
    proc = _run(["bash", str(UPGRADE_TB), "--dry-run", "v0.7.0"], env=env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "TASKBOARD_UPGRADE_DRY_RUN" in blob, blob
    assert "v0.7.0" in blob, blob
    assert PINNED_TAG in blob, blob
    assert "install-taskboard.sh" in blob, blob
    assert "compile" in blob.lower()
    assert "ak start" not in blob
    assert WORKSPACE_FOLDER_TOKEN not in blob
    assert PIN_FILE.read_text(encoding="utf-8") == before
    assert GITMODULES.read_text(encoding="utf-8") == gm_before


def test_upgrade_refuses_floating_main(tmp_path: Path) -> None:
    env = _base_env(tmp_path)
    proc = _run(["bash", str(UPGRADE_TB), "--dry-run", "main"], env=env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode != 0, blob
    assert "TASKBOARD_UPGRADE_FAIL" in blob, blob
    assert "main" in blob.lower(), blob


def test_upgrade_refuses_agent_kanban_reconnect(tmp_path: Path) -> None:
    kit = _fake_kit(tmp_path, plant_ak=True)
    env = _base_env(tmp_path, GCS_ROOT=str(kit))
    proc = _run(["bash", str(UPGRADE_TB), "--check"], env=env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode != 0, blob
    assert "AK_REFUSE" in blob, blob
    apply_proc = _run(
        ["bash", str(UPGRADE_TB), "--apply", "v0.7.0", "--skip-submodule"],
        env=env,
    )
    apply_blob = apply_proc.stdout + apply_proc.stderr
    assert apply_proc.returncode != 0, apply_blob
    assert "AK_REFUSE" in apply_blob, apply_blob
    assert (kit / "scripts" / "studio" / "taskboard" / "PIN").read_text(
        encoding="utf-8"
    ).strip().endswith(PINNED_TAG)


def test_upgrade_apply_skip_submodule_rewrites_pin_not_dashboard(tmp_path: Path) -> None:
    kit = _fake_kit(tmp_path)
    dash = kit / "scripts" / "studio" / "dashboard" / "README.md"
    dash_before = dash.read_text(encoding="utf-8")
    env = _base_env(tmp_path, GCS_ROOT=str(kit))
    proc = _run(
        ["bash", str(UPGRADE_TB), "--apply", "v0.7.0", "--skip-submodule"],
        env=env,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "TASKBOARD_UPGRADE_OK" in blob, blob
    assert "v0.7.0" in blob, blob
    pin_text = (kit / "scripts" / "studio" / "taskboard" / "PIN").read_text(encoding="utf-8")
    assert "v0.7.0" in pin_text
    assert PINNED_TAG not in [
        ln.strip()
        for ln in pin_text.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    gm = (kit / ".gitmodules").read_text(encoding="utf-8")
    assert "branch = v0.7.0" in gm
    assert "branch = v0.6.0" not in gm
    assert dash.read_text(encoding="utf-8") == dash_before
    assert "LEGACY" in dash_before
    assert "go build" not in blob
    assert WORKSPACE_FOLDER_TOKEN not in blob
    assert "GROK_HOME" not in blob or "never" in blob.lower() or "not copy" in blob.lower()
    # Real checkout pin stays on v0.6.0
    live = [
        ln.strip()
        for ln in PIN_FILE.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    assert live == [PINNED_TAG]


def test_host_taskboard_scripts_never_reconnect_ak() -> None:
    assert not (REPO / "scripts" / "studio" / "agent-kanban").exists()
    offenders: list[str] = []
    for path in TASKBOARD_DIR.rglob("*"):
        if not path.is_file() or path.name == "PIN":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        low = text.lower()
        refuse = (
            "ak_refuse" in low
            or "must stay gone" in low
            or "stays gone" in low
            or "do not reconnect" in low
            or "never reconnect" in low
        )
        if ("ak start" in low or "ama start" in low) and not refuse:
            offenders.append(str(path.relative_to(REPO)))
        if "scripts/studio/agent-kanban" in low and not refuse:
            offenders.append(f"{path.relative_to(REPO)}:reconnect")
    assert offenders == [], offenders
    upgrade = UPGRADE_TB.read_text(encoding="utf-8")
    assert "AK_REFUSE" in upgrade
    assert "agent-kanban" in upgrade


def test_docs_ticket_move_uses_ulid_not_linear_or_ak_ids() -> None:
    doc = TASKBOARD_DOC.read_text(encoding="utf-8")
    readme = TB_README.read_text(encoding="utf-8")
    wipe = WIPE_DOC.read_text(encoding="utf-8")
    soul = STUDIO_OPS_SOUL.read_text(encoding="utf-8")
    blob = "\n".join((doc, readme, wipe, soul))
    assert "ULID" in blob, "maintainer docs must say ticket move uses ULID"
    assert SAMPLE_ULID in doc, "TASKBOARD.md must show a Crockford ULID move"
    assert ULID_RE.match(SAMPLE_ULID)
    assert "ticket move T-1" not in blob
    assert "ticket move PAL-1" not in blob
    assert "upgrade-taskboard.sh" in doc
    assert "upgrade-taskboard.sh" in readme
    assert "upgrade-taskboard.sh" in wipe
    assert "PIN" in doc
    assert "snowflake" in doc.lower() or "LEGACY" in doc
    assert "studio-ops" in soul.lower()
    assert "tcarac/taskboard" in soul.lower()
    assert "upgrade-taskboard.sh" in soul
    assert WORKSPACE_FOLDER_TOKEN not in doc or "never" in doc.lower()


def test_mind_ticket_schema_example_is_ulid() -> None:
    text = MIND_PY.read_text(encoding="utf-8")
    assert SAMPLE_ULID in text or "ULID" in text
    assert '"T-1"' not in text
    schema = text.split("TICKET_SCHEMA", 1)[1].split("A2A_SEND_SCHEMA", 1)[0]
    assert SAMPLE_ULID in schema
    assert "move" in schema


def test_seat_wrappers_fail_closed_on_non_ulid_move(tmp_path: Path) -> None:
    log = tmp_path / "taskboard.argv"
    binary = _write_exec(
        tmp_path / "host-bin" / "taskboard",
        "#!/bin/sh\n"
        f'echo "$@" >> "{log}"\n'
        'echo "$@"\n',
    )
    env = _base_env(tmp_path, TASKBOARD_BIN=str(binary), GROK_HOME=str(tmp_path / "grok-home"))
    script = r"""
set -euo pipefail
source scripts/directors/seat-daemon-common.sh
export_seat_serve_env floor
unset TASKBOARD_BIN
export PATH="${GROK_HOME}/bin:${HOME}/.grok/bin"
ticket move T-1 --status done
"""
    proc = _run(["bash", "-c", script], env=env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode != 0, blob
    assert "ULID" in blob or "GCS_TASKBOARD_FAIL" in blob, blob
    assert not log.is_file() or SAMPLE_ULID not in log.read_text(encoding="utf-8")


def test_seat_wrappers_pass_ulid_move_to_host_binary(tmp_path: Path) -> None:
    log = tmp_path / "taskboard.argv"
    binary = _write_exec(
        tmp_path / "host-bin" / "taskboard",
        "#!/bin/sh\n"
        f'echo "$@" >> "{log}"\n'
        'echo "$@"\n',
    )
    env = _base_env(tmp_path, TASKBOARD_BIN=str(binary), GROK_HOME=str(tmp_path / "grok-home"))
    db = tmp_path / "a2a-state" / "taskboard" / "taskboard.db"
    script = f"""
set -euo pipefail
source scripts/directors/seat-daemon-common.sh
export_seat_serve_env floor
unset TASKBOARD_BIN
export PATH="${{GROK_HOME}}/bin:${{HOME}}/.grok/bin"
ticket move {SAMPLE_ULID} --status in_progress
taskboard ticket move {SAMPLE_ULID} --status done
"""
    proc = _run(["bash", "-c", script], env=env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    argv = log.read_text(encoding="utf-8")
    assert str(db) in argv, argv
    assert f"ticket move {SAMPLE_ULID} --status in_progress" in argv, argv
    assert f"ticket move {SAMPLE_ULID} --status done" in argv, argv


def test_seat_mcp_stays_grok_home_stdio_not_cursor_workspace() -> None:
    common = SEAT_COMMON.read_text(encoding="utf-8")
    upgrade = UPGRADE_TB.read_text(encoding="utf-8")
    cursor = CURSOR_MCP.read_text(encoding="utf-8")
    assert WORKSPACE_FOLDER_TOKEN not in common
    assert WORKSPACE_FOLDER_TOKEN not in upgrade
    assert "mcp_servers.taskboard" in common or "install_seat_grok_mcp" in common
    assert 'args = ["--db"' in common or "mcp" in common
    assert "run-mcp.sh" in cursor
    assert WORKSPACE_FOLDER_TOKEN in cursor
    assert "config.toml" not in cursor
    assert "GROK_HOME" not in cursor


def test_dashboard_stays_legacy_not_snowflake_board() -> None:
    text = DASHBOARD_README.read_text(encoding="utf-8")
    assert "LEGACY" in text
    assert "tcarac/taskboard" in text
    html = list((REPO / "scripts" / "studio" / "dashboard").glob("*.html"))
    assert html == [], html
    upgrade = UPGRADE_TB.read_text(encoding="utf-8")
    assert "dashboard" in upgrade.lower()
    assert "LEGACY" in upgrade or "snowflake" in upgrade.lower()


def test_maintainer_kit_does_not_twin_shepherd_health_probe() -> None:
    """Merged #112 is fleet-shepherd TASKBOARD_HEALTH; this slice is the pin kit."""
    text = FLEET_SHEPHERD.read_text(encoding="utf-8")
    assert "TASKBOARD_HEALTH" in text
    upgrade = UPGRADE_TB.read_text(encoding="utf-8")
    assert "fleet-shepherd" not in upgrade
    assert "TASKBOARD_HEALTH" not in upgrade
