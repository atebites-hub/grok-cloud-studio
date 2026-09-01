"""LIV-63: Directors spawn Cursor Cloud specialists via Extra High.

Fail-closed GCS_CLOUD_REPO, grok-4.6 xhigh fast=false, autoCreatePR.
Never Grok Bot CloudAgent. Never copy GROK_HOME MCP into Cursor CLI.
Never vendor Hermes. Do not land harvest mailbox PRs #26/#28.
"""
from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[1]
CLOUD = REPO / "scripts" / "cloud"
LAUNCH = REPO / "scripts" / "launch-cloud-extra-high.sh"
MIND_PY = REPO / "scripts" / "directors" / "mind.py"
MCP = REPO / "scripts" / "mcp" / "gcs_mcp.py"
CURSOR_MCP = REPO / ".cursor" / "mcp.json"
STUDIO_ENV = REPO / "studio.env.example"
PLUGIN_JS = REPO / "plugins" / "gcs-cursor-cloud" / "server.mjs"
GITMODULES = REPO / ".gitmodules"
STUDIO_REPO = "https://github.com/atebites-hub/grok-cloud-studio"

CLOUD_CONTROL_PLANE = {
    "cloud_launch",
    "cloud_list",
    "cloud_status",
    "cloud_followup",
    "cloud_result",
}

MIND_CLOUD_PLUGINS = CLOUD_CONTROL_PLANE
BANNED_BOT = "Bot CloudAgent"
HARVEST_MARKERS = (
    "defang",
    "mail envelope",
    "mind/heartbeat",
)


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


def test_sdk_extra_high_model_is_pinned_grok_xhigh() -> None:
    """Cloud create is grok-4.6 / xhigh / fast=false. Not the Cursor CLI model id."""
    common = (CLOUD / "sdk" / "common.ts").read_text(encoding="utf-8")
    launch = (CLOUD / "sdk" / "launch.ts").read_text(encoding="utf-8")
    bash = LAUNCH.read_text(encoding="utf-8")
    assert "process.env.CURSOR_CLOUD_MODEL" not in common
    assert "CURSOR_CLOUD_EFFORT" not in common
    assert 'id: "grok-4.6"' in common
    assert 'value: "xhigh"' in common
    assert 'value: "false"' in common
    assert "cursor-grok-4.6-xhigh" not in common
    assert "extraHighModel()" in launch
    assert "grok-4.6" in bash
    assert "autoCreatePR" in common
    assert "autoCreatePR" in bash


def test_studio_env_example_sets_cloud_repo_for_this_studio() -> None:
    text = STUDIO_ENV.read_text(encoding="utf-8")
    assert "GCS_CLOUD_REPO=" in text
    assert STUDIO_REPO in text
    assert "GCS_CLOUD_REF=" in text
    private = "atebites-hub/" + "palemon"
    assert private not in text
    assert "Grok Bot CloudAgent" not in text


def test_cursor_mcp_catalog_exposes_cloud_without_copying_grok_home() -> None:
    raw = CURSOR_MCP.read_text(encoding="utf-8")
    data = json.loads(raw)
    servers = data.get("mcpServers") or {}
    assert "taskboard" in servers
    cloud_name = None
    for name in ("gcs-cursor-cloud", "cursor-cloud", "cloud"):
        if name in servers:
            cloud_name = name
            break
    assert cloud_name is not None, f"Cursor CLI catalog missing cloud MCP: {sorted(servers)}"
    blob = json.dumps(data)
    low = blob.lower()
    assert "gcs_mcp.py" in blob or "cursor-cloud" in blob
    assert "--plane" in blob and "cloud" in blob
    assert "grok-home" not in low
    assert "config.toml" not in low
    assert "${GROK_HOME}" not in blob
    assert "CURSOR_API_KEY" not in blob
    assert BANNED_BOT not in blob


def test_mcp_cloud_plane_is_the_control_plane() -> None:
    msg = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}) + "\n"
    proc = subprocess.run(
        ["python3", str(MCP), "--plane", "cloud", "--ndjson"],
        cwd=str(REPO),
        input=msg,
        capture_output=True,
        text=True,
        timeout=10,
        env={**os.environ, "GCS_ROOT": str(REPO), "GCS_MCP_NDJSON": "1"},
    )
    assert proc.returncode == 0, proc.stderr
    reply = json.loads(proc.stdout.splitlines()[0])
    names = {t["name"] for t in reply["result"]["tools"]}
    assert names == CLOUD_CONTROL_PLANE
    assert "cloud_watch" not in names


def test_mind_plugins_wrap_cloud_control_plane(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    logs = {name: tmp_path / f"{name}.argv" for name in MIND_CLOUD_PLUGINS}
    scripts = {
        "cloud_launch": tmp_path / "scripts" / "launch-cloud-extra-high.sh",
        "cloud_list": tmp_path / "scripts" / "cloud" / "list-cloud-agents.sh",
        "cloud_status": tmp_path / "scripts" / "cloud" / "status-cloud-agent.sh",
        "cloud_followup": tmp_path / "scripts" / "cloud" / "followup-cloud-agent.sh",
        "cloud_result": tmp_path / "scripts" / "cloud" / "result-cloud-agent.sh",
    }
    for name, path in scripts.items():
        _write_exec(
            path,
            "#!/bin/sh\n"
            f'printf "%s\\n" "$@" >> "{logs[name]}"\n'
            f'echo CLOUD_{name.split("_", 1)[1].upper()}_OK "$@"\n',
        )
    mind = _load(MIND_PY, "gcs_mind_cloud_plane")
    monkeypatch.setattr(mind, "ROOT", tmp_path)
    monkeypatch.setattr(mind, "STATE_DIR", tmp_path / "a2a-state")
    for name in MIND_CLOUD_PLUGINS:
        assert name in mind.PLUGINS, name
    launch_out = mind.call_plugin("cloud_launch", {"prompt": "ship it", "name": "floor-x"})
    assert "CLOUD_LAUNCH_OK" in launch_out
    assert "ship it" in logs["cloud_launch"].read_text(encoding="utf-8")
    listed = mind.call_plugin("cloud_list", {"limit": "5"})
    assert "CLOUD_LIST_OK" in listed
    status_out = mind.call_plugin("cloud_status", {"id": "bc-status-1"})
    assert "CLOUD_STATUS_OK" in status_out
    follow_out = mind.call_plugin(
        "cloud_followup", {"id": "bc-follow-1", "prompt": "keep going"}
    )
    assert "CLOUD_FOLLOWUP_OK" in follow_out
    result_out = mind.call_plugin("cloud_result", {"id": "bc-result-1"})
    assert "CLOUD_RESULT_OK" in result_out
    missing = mind.call_plugin("cloud_followup", {"id": "bc-x"})
    assert "PLUGIN_ERR" in missing
    assert "a2a_list_seats" in mind.PLUGINS


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
    grok_bin = Path(env["GROK_HOME"]) / "bin"
    for name in ("cloud_launch", "cloud_list", "cloud_status", "cloud_followup", "cloud_result"):
        wrap = grok_bin / name
        assert wrap.is_file(), name
        text = wrap.read_text(encoding="utf-8")
        assert "launch-cloud-extra-high.sh" in text or "scripts/cloud/" in text
        assert "config.toml" not in text
        assert ".cursor/mcp.json" not in text
    assert "cloud_watch" not in (proc.stdout or "")


def test_cloud_plane_never_launches_bot_cloudagent() -> None:
    paths = [
        LAUNCH,
        CLOUD / "sdk" / "launch.ts",
        CLOUD / "sdk" / "common.ts",
        MCP,
        MIND_PY,
        PLUGIN_JS,
        REPO / "plugins" / "cursor-cloud" / "server.py",
        REPO / "scripts" / "directors" / "common_footer.txt",
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert BANNED_BOT not in text, path.name
        assert "Grok Bot CloudAgent" not in text, path.name
    launch = LAUNCH.read_text(encoding="utf-8")
    assert "grok-4.6" in launch
    mind = MIND_PY.read_text(encoding="utf-8")
    assert "launch-cloud-extra-high.sh" in mind


def test_liv63_does_not_vendor_hermes_or_land_harvest_mailbox() -> None:
    assert not (REPO / "vendor" / "hermes-agent").exists()
    assert not (REPO / "vendor" / "hermes").exists()
    modules = GITMODULES.read_text(encoding="utf-8")
    assert "hermes-agent" not in modules
    assert "tcarac/taskboard" in modules
    mind = MIND_PY.read_text(encoding="utf-8")
    hub = (REPO / "scripts" / "a2a" / "hub.py").read_text(encoding="utf-8")
    blob = mind + "\n" + hub
    for marker in HARVEST_MARKERS:
        assert marker not in blob, marker
    assert "message_agent.py" not in mind
    assert "plugin.yaml" not in mind
