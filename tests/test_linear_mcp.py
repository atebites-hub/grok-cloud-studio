"""Linear MCP on both runtimes. Palemon workspace is Living Sky, never Black Swan Money.

Grok minds: GROK_HOME/config.toml HTTP catalog (not a Cursor mcp.json copy).
Cursor Cloud / Cursor CLI: .cursor/mcp.json Linear + taskboard only.
Cloud agents cannot scrape GROK_HOME; LINEAR_API_KEY comes from a secret file.
"""
from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SEAT_MCP = REPO / "scripts" / "directors" / "seat_grok_mcp.py"
LINEAR_KEY = REPO / "scripts" / "directors" / "linear_key.py"
SEAT_COMMON = REPO / "scripts" / "directors" / "seat-daemon-common.sh"
CURSOR_MCP = REPO / ".cursor" / "mcp.json"
MIND_DOC = REPO / "docs" / "studio" / "MIND.md"
WIPE = REPO / "docs" / "studio" / "WIPE.md"
CLOUD_DOC = REPO / "docs" / "CLOUD.md"
AGENTS = REPO / "AGENTS.md"
STUDIO_ENV = REPO / "studio.env.example"

LINEAR_MCP_URL = "https://mcp.linear.app/mcp"
LIVING_SKY = "livingsky"
TEAM_KEY = "LIV"
BLACK_SWAN = "Black Swan Money"
WORKSPACE_FOLDER_TOKEN = "${" + "workspaceFolder}"
BANNED_GROK_CATALOG = ("higgsfield", "studio-mind", "mcp_servers", "GROK_HOME", "config.toml")


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_exec(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def _fake_taskboard(tmp_path: Path) -> Path:
    return _write_exec(
        tmp_path / "host-bin" / "taskboard",
        "#!/bin/sh\necho taskboard\n",
    )


def _base_env(tmp_path: Path, *, taskboard_bin: Path | None = None) -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    env = {
        "PATH": "/usr/bin:/bin",
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


def test_seat_identity_registers_linear_http_catalog_in_grok_home(tmp_path: Path) -> None:
    binary = _fake_taskboard(tmp_path)
    env = _base_env(tmp_path, taskboard_bin=binary)
    proc = subprocess.run(
        [
            "bash",
            "-c",
            "set -euo pipefail; source scripts/directors/seat-daemon-common.sh; install_seat_identity floor",
        ],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    text = (Path(env["GROK_HOME"]) / "config.toml").read_text(encoding="utf-8")
    parsed = tomllib.loads(text)
    linear = parsed["mcp_servers"]["linear"]
    assert linear["url"] == LINEAR_MCP_URL
    assert "[mcp_servers.taskboard]" in text
    assert "[compat.cursor]" in text
    assert "mcps = false" in text
    assert WORKSPACE_FOLDER_TOKEN not in text
    assert ".cursor/mcp.json" not in text
    assert "command =" not in text.split("[mcp_servers.linear]", 1)[1].split("[", 1)[0]
    assert BLACK_SWAN.lower() not in text.lower() or "never" in text.lower()


def test_linear_toml_is_idempotent_and_uses_api_key_interpolation(tmp_path: Path) -> None:
    mod = _load(SEAT_MCP, "gcs_seat_grok_mcp_linear")
    poisoned = (
        "[cli]\nuse_leader = true\n\n"
        "[mcp_servers.linear]\n"
        'url = "https://mcp.linear.app/sse"\n'
        "# gcs-seat-linear-mcp\n"
        "[mcp_servers.linear]\n"
        'url = "https://example.invalid/mcp"\n'
        "# gcs-seat-linear-mcp-end\n"
    )
    out = mod.merge_seat_taskboard_mcp(poisoned, "/bin/taskboard", "/tmp/db")
    if hasattr(mod, "merge_seat_linear_mcp"):
        out = mod.merge_seat_linear_mcp(out)
    parsed = tomllib.loads(out)
    assert parsed["mcp_servers"]["linear"]["url"] == LINEAR_MCP_URL
    assert out.count("[mcp_servers.linear]") == 1
    assert "${LINEAR_API_KEY}" in out
    assert "Bearer" in out
    assert "/sse" not in parsed["mcp_servers"]["linear"]["url"]
    again = mod.merge_seat_taskboard_mcp(out, "/bin/taskboard", "/tmp/db")
    if hasattr(mod, "merge_seat_linear_mcp"):
        again = mod.merge_seat_linear_mcp(again)
    assert tomllib.loads(again)["mcp_servers"]["linear"]["url"] == LINEAR_MCP_URL
    assert again.count("[mcp_servers.linear]") == 1
    assert again.count("[mcp_servers.taskboard]") == 1


def test_linear_key_file_loads_without_printing_secret(tmp_path: Path) -> None:
    mod = _load(LINEAR_KEY, "gcs_linear_key")
    secret = "lin_api_" + ("x" * 24)
    key_file = tmp_path / "a2a-state" / "linear.env"
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.write_text(f"LINEAR_API_KEY={secret}\n", encoding="utf-8")
    env: dict[str, str] = {}
    applied = mod.apply_linear_key_env(
        env,
        state_dir=tmp_path / "a2a-state",
        key_file=key_file,
    )
    assert applied is True
    assert env["LINEAR_API_KEY"] == secret
    dumped = json.dumps(mod.__dict__, default=str)
    assert secret not in dumped


def test_cursor_mcp_json_is_linear_plus_taskboard_only() -> None:
    data = json.loads(CURSOR_MCP.read_text(encoding="utf-8"))
    servers = data.get("mcpServers") or {}
    assert set(servers) == {"taskboard", "linear"}, servers
    linear = servers["linear"]
    assert linear.get("url") == LINEAR_MCP_URL
    headers = linear.get("headers") or {}
    auth = str(headers.get("Authorization") or headers.get("authorization") or "")
    assert "${LINEAR_API_KEY}" in auth
    assert "Bearer" in auth
    blob = json.dumps(data)
    low = blob.lower()
    for banned in BANNED_GROK_CATALOG:
        assert banned.lower() not in low, banned
    assert "lin_api_" not in low
    assert BLACK_SWAN.lower() not in low
    assert "ak" not in servers
    spec = servers["taskboard"]
    joined = " ".join(str(x) for x in ([spec.get("command", "")] + list(spec.get("args") or [])))
    assert "run-mcp.sh" in joined or "run-mcp.sh" in blob


def test_docs_name_living_sky_and_forbid_black_swan_money() -> None:
    mind = MIND_DOC.read_text(encoding="utf-8")
    wipe = WIPE.read_text(encoding="utf-8")
    agents = AGENTS.read_text(encoding="utf-8")
    blob = mind + "\n" + wipe + "\n" + agents
    low = blob.lower()
    assert LIVING_SKY in low
    assert TEAM_KEY.lower() in low or "livingsky" in low
    assert "save_issue" in mind
    assert "save_comment" in mind
    assert "prepare_attachment_upload" in mind
    assert "screenshot" in mind.lower()
    assert "never" in low and BLACK_SWAN.lower() in low
    assert "do not copy" in mind.lower()
    assert "GROK_HOME" in mind
    assert LINEAR_MCP_URL in mind or "mcp.linear.app/mcp" in mind
    assert "LINEAR_API_KEY" in mind
    assert "linear.env" in wipe.lower() or "secret file" in wipe.lower() or "LINEAR_API_KEY" in wipe


def test_seat_common_sources_linear_key_file_without_echo() -> None:
    text = SEAT_COMMON.read_text(encoding="utf-8")
    assert "load_linear_api_key" in text or "LINEAR_API_KEY" in text
    assert "linear.env" in text
    assert "echo \"$LINEAR_API_KEY\"" not in text
    assert "echo $LINEAR_API_KEY" not in text
    identity = text.split("install_seat_identity() {", 1)[1]
    assert "install_seat_grok_mcp" in identity


def test_studio_env_example_documents_linear_secret_file_not_value() -> None:
    text = STUDIO_ENV.read_text(encoding="utf-8")
    assert "LINEAR_API_KEY" in text
    assert "livingsky" in text.lower() or "living sky" in text.lower()
    assert BLACK_SWAN in text
    assert "never" in text.lower()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("LINEAR_API_KEY=") and not stripped.startswith("#"):
            raise AssertionError("studio.env.example must not assign LINEAR_API_KEY")


def test_cloud_doc_says_agents_cannot_scrape_grok_home() -> None:
    cloud = CLOUD_DOC.read_text(encoding="utf-8")
    low = cloud.lower()
    assert "linear" in low
    assert "linear_api_key" in low
    assert "grok_home" in low or "cannot scrape" in low or "mcp.json" in low
    assert BLACK_SWAN.lower() in low or "living sky" in low or LIVING_SKY in low
