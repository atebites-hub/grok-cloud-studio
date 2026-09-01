"""Linear MCP on both mind runtimes. Palemon workspace is Living Sky / LIV.

Grok catalog: seat GROK_HOME/config.toml (not a copy of .cursor/mcp.json).
Cursor catalog: checkout .cursor/mcp.json Linear + taskboard only.
Cloud agents cannot scrape GROK_HOME; they get Linear via snapshot
LINEAR_API_KEY (secret file) and/or that Cursor mcp.json.
Never print or commit the key. Never Black Swan Money.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import tomllib
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[1]
SEAT_MCP = REPO / "scripts" / "directors" / "seat_grok_mcp.py"
LINEAR_ENV = REPO / "scripts" / "directors" / "linear_env.py"
SEAT_COMMON = REPO / "scripts" / "directors" / "seat-daemon-common.sh"
LOAD_LINEAR = REPO / "scripts" / "cloud" / "load-linear-env.sh"
CURSOR_MCP = REPO / ".cursor" / "mcp.json"
MIND_DOC = REPO / "docs" / "studio" / "MIND.md"
WIPE_DOC = REPO / "docs" / "studio" / "WIPE.md"
CLOUD_DOC = REPO / "docs" / "CLOUD.md"
TASKBOARD_DOC = REPO / "docs" / "studio" / "TASKBOARD.md"
FOOTER = REPO / "scripts" / "directors" / "common_footer.txt"
STUDIO_ENV = REPO / "studio.env.example"

LINEAR_MCP_URL = "https://mcp.linear.app/mcp"
LIVING_SKY_HOST = "linear.app/livingsky"
BANNED_WORKSPACE = "Black Swan Money"
WORKSPACE_FOLDER_TOKEN = "${" + "workspaceFolder}"
GROK_ONLY_CURSOR_SERVERS = (
    "gcs-a2a",
    "gcs-cursor-cloud",
    "studio-mind",
    "higgsfield",
    "filesystem",
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


def _fake_taskboard(tmp_path: Path) -> Path:
    return _write_exec(
        tmp_path / "host-bin" / "taskboard",
        "#!/bin/sh\necho fake-taskboard\n",
    )


def test_seat_grok_mcp_registers_linear_http_from_grok_catalog(tmp_path: Path) -> None:
    binary = _fake_taskboard(tmp_path)
    env = _base_env(tmp_path, taskboard_bin=binary)
    script = r"""
set -euo pipefail
source scripts/directors/seat-daemon-common.sh
install_seat_grok_mcp floor
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
    text = (Path(env["GROK_HOME"]) / "config.toml").read_text(encoding="utf-8")
    parsed = tomllib.loads(text)
    assert parsed["compat"]["cursor"]["mcps"] is False
    assert parsed["mcp_servers"]["taskboard"]["args"][-1] == "mcp"
    linear = parsed["mcp_servers"]["linear"]
    assert linear["url"] == LINEAR_MCP_URL
    headers = linear["headers"]
    auth = headers.get("Authorization") or headers.get("authorization")
    assert auth == "Bearer ${LINEAR_API_KEY}"
    assert text.count("[mcp_servers.linear]") == 1, text
    assert WORKSPACE_FOLDER_TOKEN not in text
    assert ".cursor/mcp.json" not in text
    assert "mcp-remote" not in text
    assert BANNED_WORKSPACE.lower() not in text.lower()


def test_linear_mcp_block_is_idempotent_and_strips_dupes() -> None:
    mod = _load(SEAT_MCP, "gcs_seat_grok_mcp_linear")
    poisoned = (
        "[cli]\nuse_leader = true\n\n"
        "[mcp_servers.linear]\n"
        'url = "https://example.invalid/old"\n\n'
        "# gcs-seat-taskboard-mcp\n"
        "[compat.cursor]\nmcps = false\n\n"
        "[mcp_servers.taskboard]\n"
        'command = "/stale"\n'
        'args = ["mcp"]\n\n'
        "[mcp_servers.linear]\n"
        'url = "https://example.invalid/also-stale"\n'
        "# gcs-seat-taskboard-mcp-end\n"
    )
    out = mod.merge_seat_taskboard_mcp(poisoned, "/bin/taskboard", "/tmp/db")
    parsed = tomllib.loads(out)
    assert parsed["mcp_servers"]["linear"]["url"] == LINEAR_MCP_URL
    assert out.count("[mcp_servers.linear]") == 1
    again = mod.merge_seat_taskboard_mcp(out, "/bin/taskboard", "/tmp/db")
    assert tomllib.loads(again)["mcp_servers"]["linear"]["url"] == LINEAR_MCP_URL
    assert again.count("[mcp_servers.linear]") == 1


def test_cursor_mcp_json_is_linear_plus_taskboard_only() -> None:
    data = json.loads(CURSOR_MCP.read_text(encoding="utf-8"))
    servers = data.get("mcpServers") or {}
    assert set(servers) == {"taskboard", "linear"}, servers
    linear = servers["linear"]
    blob = json.dumps(data)
    assert LINEAR_MCP_URL in blob
    auth = (linear.get("headers") or {}).get("Authorization") or ""
    assert "Bearer" in auth
    assert "${LINEAR_API_KEY}" in auth
    assert "lin_" not in blob
    assert "mcp-remote" not in blob
    for banned in GROK_ONLY_CURSOR_SERVERS:
        assert banned not in servers
    assert BANNED_WORKSPACE.lower() not in blob.lower()
    assert WORKSPACE_FOLDER_TOKEN not in blob or "run-mcp.sh" in blob


def test_load_linear_api_key_from_secret_file_never_prints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mod = _load(LINEAR_ENV, "gcs_linear_env")
    secret = tmp_path / "secrets" / "linear.api_key"
    secret.parent.mkdir(parents=True)
    key = "lin_test_secret_file_value"
    secret.write_text(key + "\n", encoding="utf-8")
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    monkeypatch.setenv("LINEAR_API_KEY_FILE", str(secret))
    monkeypatch.setenv("GCS_A2A_STATE", str(tmp_path / "a2a-state"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    got = mod.load_linear_api_key()
    assert got == key
    # CLI value path used by snapshot / seat env. Stdout is the key; callers
    # must capture it with set +x. Tests never log the value in assertions
    # that dump the whole proc blob alongside other secrets.
    cli_env = {**os.environ, "LINEAR_API_KEY_FILE": str(secret)}
    cli_env.pop("LINEAR_API_KEY", None)
    proc = subprocess.run(
        ["python3", str(LINEAR_ENV), "value"],
        cwd=str(REPO),
        env=cli_env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == key
    assert proc.stderr.strip() == ""


def test_load_linear_env_script_exports_from_file_without_echoing(
    tmp_path: Path,
) -> None:
    secret = tmp_path / "linear.api_key"
    key = "lin_snapshot_env_from_file"
    secret.write_text(f"LINEAR_API_KEY={key}\n", encoding="utf-8")
    script = f"""
set -euo pipefail
unset LINEAR_API_KEY
export LINEAR_API_KEY_FILE={secret}
source scripts/cloud/load-linear-env.sh
python3 -c 'import os; print("HAS" if os.environ.get("LINEAR_API_KEY") else "MISSING")'
python3 -c 'import os; print("MATCH" if os.environ.get("LINEAR_API_KEY") == open("{secret}").read().split("=",1)[-1].strip() else "NOMATCH")'
"""
    proc = subprocess.run(
        ["bash", "-c", script],
        cwd=str(REPO),
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": str(tmp_path / "home"),
            "GCS_ROOT": str(REPO),
            "GCS_A2A_STATE": str(tmp_path / "a2a-state"),
            "LC_ALL": "C",
        },
        capture_output=True,
        text=True,
        timeout=15,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "HAS" in proc.stdout
    assert "MATCH" in proc.stdout
    assert key not in blob


def test_linear_workspace_is_living_sky_never_black_swan() -> None:
    mod = _load(LINEAR_ENV, "gcs_linear_env_ws")
    assert "livingsky" in mod.LINEAR_WORKSPACE_HOST
    assert mod.LINEAR_TEAM_KEY == "LIV"
    assert "livingsky" in mod.LINEAR_TEAM.lower()
    assert BANNED_WORKSPACE.lower() in mod.BANNED_LINEAR_WORKSPACE.lower()
    mind = MIND_DOC.read_text(encoding="utf-8")
    wipe = WIPE_DOC.read_text(encoding="utf-8")
    cloud = CLOUD_DOC.read_text(encoding="utf-8")
    board = TASKBOARD_DOC.read_text(encoding="utf-8")
    footer = FOOTER.read_text(encoding="utf-8")
    blob = "\n".join((mind, wipe, cloud, board, footer))
    low = blob.lower()
    assert LIVING_SKY_HOST in low
    assert "livingsky" in low or "living sky" in low
    assert " LIV" in blob or "team Livingsky" in blob or "team `LIV`" in blob or "/ LIV" in blob
    assert "black swan" in low
    assert "never" in low
    assert "save_issue" in mind
    assert "save_comment" in mind
    assert "prepare_attachment_upload" in mind
    assert "screenshot" in mind.lower()
    assert "do not copy" in mind.lower()
    assert "LINEAR_API_KEY" in mind
    assert "LINEAR_API_KEY" in cloud
    assert "secret file" in (mind + cloud + wipe).lower()
    assert BANNED_WORKSPACE.lower() not in CURSOR_MCP.read_text(encoding="utf-8").lower()


def test_studio_env_example_documents_linear_secret_file_not_value() -> None:
    text = STUDIO_ENV.read_text(encoding="utf-8")
    assert "LINEAR_API_KEY_FILE" in text or "linear.api_key" in text
    assert not re.search(r"(?m)^[ \t]*LINEAR_API_KEY=", text)
    assert "never" in text.lower() and "black swan" in text.lower()
    assert "livingsky" in text.lower() or "living sky" in text.lower()


def test_seat_common_loads_linear_key_and_mentions_grok_catalog() -> None:
    common = SEAT_COMMON.read_text(encoding="utf-8")
    assert "load_linear_api_key" in common
    assert "linear_env.py" in common
    serve = common.split("export_seat_serve_env() {", 1)[1]
    assert "load_linear_api_key" in serve.split("install_seat_identity() {", 1)[0]
    assert LOAD_LINEAR.is_file()
