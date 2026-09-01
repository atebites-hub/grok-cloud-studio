"""Directors spawn Extra High specialists via Cloud API PATH + wipe env.

Unique vs main after later catalog/mind law:

- Palemon wipe `studio.env.example` assigns `GCS_CLOUD_REPO` / `GCS_CLOUD_REF`
- Seat PATH wrappers (`install_seat_cloud_cli`) for launch/list/status/followup/result

Do not restack #47 `cloud_list` / `cloud_followup` into `mind.py`. Checkout
`.cursor/mcp.json` stays Linear HTTP + taskboard only. Extra High pin stays
grok-4.6 / xhigh / fast=false (leaked CURSOR_CLOUD_MODEL is rejected on main).
Never Bot CloudAgent. Never copy GROK_HOME MCP into Cursor CLI.
"""
from __future__ import annotations

import json
import stat
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CLOUD = REPO / "scripts" / "cloud"
LAUNCH = REPO / "scripts" / "launch-cloud-extra-high.sh"
MIND_PY = REPO / "scripts" / "directors" / "mind.py"
SEAT_COMMON = REPO / "scripts" / "directors" / "seat-daemon-common.sh"
CURSOR_MCP = REPO / ".cursor" / "mcp.json"
STUDIO_ENV = REPO / "studio.env.example"
MIND_DOC = REPO / "docs" / "studio" / "MIND.md"
CLOUD_DOC = REPO / "docs" / "CLOUD.md"

STUDIO_REPO = "https://github.com/atebites-hub/grok-cloud-studio"
BANNED_BOT = "Bot CloudAgent"
SEAT_CLOUD_CMDS = (
    "cloud_launch",
    "cloud_list",
    "cloud_status",
    "cloud_followup",
    "cloud_result",
)
PR47_MIND_RESTACK = ("cloud_list", "cloud_followup")


def test_sdk_extra_high_model_stays_pinned_grok_xhigh() -> None:
    """Create is grok-4.6 / xhigh / fast=false. Leaked CLI model ids are rejected."""
    common = (CLOUD / "sdk" / "common.ts").read_text(encoding="utf-8")
    launch = (CLOUD / "sdk" / "launch.ts").read_text(encoding="utf-8")
    bash = LAUNCH.read_text(encoding="utf-8")
    assert 'id: "grok-4.6"' in common
    assert 'value: "xhigh"' in common
    assert 'value: "false"' in common
    assert "cursor-grok-4.6-xhigh" not in common
    assert "extraHighModel()" in launch
    assert "CURSOR_CLOUD_MODEL" in common
    assert "rejected" in common or "CLOUD_BLOCKED" in common
    assert '"id": "grok-4.6"' in bash or 'id": "grok-4.6"' in bash
    assert "autoCreatePR" in common
    assert "autoCreatePR" in bash


def test_studio_env_example_sets_cloud_repo_for_this_studio() -> None:
    text = STUDIO_ENV.read_text(encoding="utf-8")
    assigned = [
        ln.strip()
        for ln in text.splitlines()
        if ln.strip().startswith("GCS_CLOUD_REPO=")
    ]
    assert assigned, "wipe studio.env.example must assign GCS_CLOUD_REPO"
    assert STUDIO_REPO in assigned[0]
    ref = [
        ln.strip()
        for ln in text.splitlines()
        if ln.strip().startswith("GCS_CLOUD_REF=")
    ]
    assert ref and ref[0].split("=", 1)[1].strip() == "main"
    assert "CURSOR_API_KEY=" not in text or "# CURSOR_API_KEY" in text
    private = "atebites-hub/" + "palemon"
    assert private not in text


def test_cursor_mcp_catalog_stays_linear_plus_taskboard_only() -> None:
    """Later Extra High catalog law: do not add gcs-cursor-cloud here."""
    raw = CURSOR_MCP.read_text(encoding="utf-8")
    data = json.loads(raw)
    servers = data.get("mcpServers") or {}
    assert set(servers) == {"taskboard", "linear"}, servers
    blob = json.dumps(data)
    low = blob.lower()
    assert "gcs_mcp.py" not in blob
    assert "gcs-cursor-cloud" not in low
    assert "--plane" not in blob
    assert "grok-home" not in low
    assert "config.toml" not in low
    assert "CURSOR_API_KEY" not in blob
    assert BANNED_BOT not in blob


def test_mind_py_does_not_restack_pr47_list_followup() -> None:
    mind = MIND_PY.read_text(encoding="utf-8")
    for name in PR47_MIND_RESTACK:
        assert f'"{name}"' not in mind, name
        assert f"plugin_{name}" not in mind, name


def test_seat_cloud_cli_wrappers_do_not_copy_mcp(tmp_path: Path) -> None:
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path / "home"),
        "GCS_ROOT": str(REPO),
        "GCS_A2A_STATE": str(tmp_path / "a2a-state"),
        "GROK_HOME": str(tmp_path / "grok-home"),
        "LC_ALL": "C",
        "TERM": "dumb",
    }
    script = r"""
set -euo pipefail
source scripts/directors/seat-daemon-common.sh
install_seat_cloud_cli floor
printf 'GROK_HOME=%s\n' "$GROK_HOME"
ls -1 "${GROK_HOME}/bin"
"""
    proc = subprocess.run(
        ["bash", "-c", script],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "SEAT_CLOUD_CLI_OK" in blob
    grok_bin = Path(env["GROK_HOME"]) / "bin"
    home_bin = Path(env["HOME"]) / ".grok" / "bin"
    for name in SEAT_CLOUD_CMDS:
        wrap = grok_bin / name
        assert wrap.is_file(), name
        assert wrap.stat().st_mode & stat.S_IXUSR
        text = wrap.read_text(encoding="utf-8")
        assert "launch-cloud-extra-high.sh" in text or "scripts/cloud/" in text
        assert "config.toml" not in text
        assert ".cursor/mcp.json" not in text
        assert BANNED_BOT not in text
        assert (home_bin / name).is_file(), name
    assert not (grok_bin / "cloud_watch").exists()
    assert "install_seat_cloud_cli" in SEAT_COMMON.read_text(encoding="utf-8")
    identity = SEAT_COMMON.read_text(encoding="utf-8").split(
        "install_seat_identity() {", 1
    )[1]
    assert "install_seat_cloud_cli" in identity


def test_docs_point_directors_at_path_wrappers_not_cursor_catalog() -> None:
    mind = MIND_DOC.read_text(encoding="utf-8")
    cloud = CLOUD_DOC.read_text(encoding="utf-8")
    common = SEAT_COMMON.read_text(encoding="utf-8")
    assert "install_seat_cloud_cli" in mind or "cloud_followup" in mind
    assert "install_seat_cloud_cli" in cloud or "GROK_HOME/bin" in cloud
    assert "install_seat_cloud_cli" in common
    assert "do not restack" in mind.lower() or "cloud_list" in mind
    launch = LAUNCH.read_text(encoding="utf-8")
    assert "grok-4.6" in launch
    for path in (LAUNCH, CLOUD / "sdk" / "launch.ts", CLOUD / "sdk" / "common.ts", MIND_PY):
        text = path.read_text(encoding="utf-8")
        low = text.lower()
        assert "never" in low and "bot cloudagent" in low, path.name
        # Grunt runtime must stay Extra High, not a Grok Bot CloudAgent id.
