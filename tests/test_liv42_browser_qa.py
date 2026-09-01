"""LIV-42 BDD: a Grok Build mind can open the Palemon client in a browser plugin.

Feature: Grok catalog live Chrome for visual QA
  Living Sky only. Never Bot CloudAgent. Never Cursor CLI browser tools.
  Never Playwright MCP (not in the Grok catalog). Two catalogs: do not copy
  GROK_HOME into `.cursor/mcp.json`.

  Scenario: a Grok Build mind can open the Palemon client for visual QA
    Given a Grok Build mind seat GROK_HOME
    And the Palemon client origin is http://127.0.0.1:5173/
    When seat MCP is registered and chrome-devtools is plugin-installed
    Then GROK_HOME/config.toml has [mcp_servers.chrome-devtools]
      as `npx -y chrome-devtools-mcp@latest`
    And `grok plugin install chrome-devtools --trust` ran against that GROK_HOME
    And qa-a can navigate_page that origin (chrome-devtools, not Python mind)
    And Cursor `.cursor/mcp.json` stays taskboard-only
"""
from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
import tomllib
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parents[1]
SEAT_MCP_PY = REPO / "scripts" / "directors" / "seat_grok_mcp.py"
SEAT_COMMON = REPO / "scripts" / "directors" / "seat-daemon-common.sh"
MIND_LOOP = REPO / "scripts" / "directors" / "seat-mind-loop.sh"
MIND_PY = REPO / "scripts" / "directors" / "mind.py"
MIND_DOC = REPO / "docs" / "studio" / "MIND.md"
WIPE_DOC = REPO / "docs" / "studio" / "WIPE.md"
QA_A_SOUL = REPO / "docs" / "studio" / "directors" / "souls" / "qa-a" / "SOUL.md"
CURSOR_MCP = REPO / ".cursor" / "mcp.json"
PLAYTEST_URL = "http://127.0.0.1:5173/"
BANNED_BROWSERS = ("playwright", "browser-use", "browser_use")
BANNED_BOT_CLOUD = ("bot cloudagent", "grok bot cloudagent")


def _load_seat_mcp() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gcs_seat_grok_mcp_liv42", SEAT_MCP_PY)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gcs_seat_grok_mcp_liv42"] = mod
    spec.loader.exec_module(mod)
    return mod


def _write_exec(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def _base_env(tmp_path: Path, *, extra_path: str = "") -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update(
        {
            "PATH": extra_path or "/usr/bin:/bin",
            "HOME": str(home),
            "GCS_ROOT": str(REPO),
            "GCS_A2A_STATE": str(tmp_path / "a2a-state"),
            "GROK_HOME": str(tmp_path / "grok-home"),
            "TASKBOARD_BIN": str(
                _write_exec(tmp_path / "host-bin" / "taskboard", "#!/bin/sh\nexit 0\n")
            ),
            "LC_ALL": "C",
            "TERM": "dumb",
        }
    )
    return env


def test_given_playtest_origin_when_merged_then_grok_catalog_has_chrome_devtools() -> None:
    """Given the Palemon client origin, When MCP is merged, Then chrome-devtools is in GROK_HOME."""
    mod = _load_seat_mcp()
    assert mod.CLIENT_PLAYTEST_URL == PLAYTEST_URL
    assert mod.CHROME_DEVTOOLS_SERVER == "chrome-devtools"
    assert mod.CHROME_DEVTOOLS_COMMAND == "npx"
    assert mod.CHROME_DEVTOOLS_ARGS == ("-y", "chrome-devtools-mcp@latest")
    tool = mod.chrome_devtools_open_client_tool()
    assert tool["server"] == "chrome-devtools"
    assert tool["name"] == "navigate_page"
    assert tool["arguments"]["url"] == PLAYTEST_URL
    out = mod.merge_seat_taskboard_mcp("", "/bin/taskboard", "/tmp/db")
    parsed = tomllib.loads(out)
    chrome = parsed["mcp_servers"]["chrome-devtools"]
    assert chrome["command"] == "npx"
    assert chrome["args"] == ["-y", "chrome-devtools-mcp@latest"]
    assert parsed["mcp_servers"]["taskboard"]["command"] == "/bin/taskboard"
    assert parsed["compat"]["cursor"]["mcps"] is False
    low = out.lower()
    for banned in BANNED_BROWSERS:
        assert banned not in low
    assert "cloudagent" not in low


def test_when_seat_mcp_installs_then_qa_a_grok_home_can_open_client(
    tmp_path: Path,
) -> None:
    """When install_seat_grok_mcp runs, Then qa-a GROK_HOME can open 127.0.0.1:5173/."""
    env = _base_env(tmp_path)
    script = r"""
set -euo pipefail
source scripts/directors/seat-daemon-common.sh
install_seat_grok_mcp qa-a
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
    chrome = parsed["mcp_servers"]["chrome-devtools"]
    assert chrome["command"] == "npx"
    assert chrome["args"] == ["-y", "chrome-devtools-mcp@latest"]
    assert PLAYTEST_URL.startswith("http://127.0.0.1:5173")
    cursor = json.loads(CURSOR_MCP.read_text(encoding="utf-8"))
    servers = cursor.get("mcpServers") or {}
    assert list(servers) == ["taskboard"]
    assert "chrome-devtools" not in servers


def test_when_mind_installs_chrome_devtools_plugin_then_grok_catalog_trusts_it(
    tmp_path: Path,
) -> None:
    """When install_chrome_devtools_plugin runs, Then grok plugin install chrome-devtools --trust."""
    log = tmp_path / "plugin.argv"
    grok = _write_exec(
        tmp_path / "fake-bin" / "grok",
        "#!/bin/sh\n"
        f'printf "%s\\n" "$@" >> "{log}"\n'
        'printf "GROK_HOME=%s\\n" "$GROK_HOME" >> '
        f'"{log}.env"\n'
        "exit 0\n",
    )
    env = _base_env(tmp_path, extra_path=f"{grok.parent}:/usr/bin:/bin")
    script = r"""
set -euo pipefail
source scripts/directors/seat-daemon-common.sh
install_chrome_devtools_plugin qa-a
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
    assert "MIND_PLUGIN_OK" in blob, blob
    assert "plugin=chrome-devtools" in blob, blob
    argv = log.read_text(encoding="utf-8")
    parts = argv.split()
    assert "plugin" in parts
    assert "install" in parts
    assert "--trust" in parts
    assert "chrome-devtools" in parts
    assert "studio-mind" not in parts
    assert "-p" not in parts
    assert "--plugin-dir" not in argv
    grok_home = (tmp_path / "plugin.argv.env").read_text(encoding="utf-8")
    assert env["GROK_HOME"] in grok_home


def test_when_chrome_devtools_already_installed_then_mind_plugin_ok(
    tmp_path: Path,
) -> None:
    """Already-installed marketplace chrome-devtools is MIND_PLUGIN_OK, not install-fail."""
    log = tmp_path / "plugin.argv"
    stamp = tmp_path / "plugin.installed"
    grok = _write_exec(
        tmp_path / "fake-bin" / "grok",
        "#!/bin/sh\n"
        f'printf "%s\\n" "$@" >> "{log}"\n'
        f'if [ -f "{stamp}" ]; then\n'
        '  echo "Error: repo chrome-devtools-deadbeef already installed" >&2\n'
        "  exit 1\n"
        "fi\n"
        f'touch "{stamp}"\n'
        "exit 0\n",
    )
    env = _base_env(tmp_path, extra_path=f"{grok.parent}:/usr/bin:/bin")
    script = r"""
set -euo pipefail
source scripts/directors/seat-daemon-common.sh
install_chrome_devtools_plugin qa-a
install_chrome_devtools_plugin qa-a
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
    assert blob.count("MIND_PLUGIN_OK") >= 2, blob
    assert "reason=install-fail" not in blob, blob
    assert "MIND_PLUGIN_SKIP" not in blob, blob
    argv = log.read_text(encoding="utf-8")
    assert argv.count("chrome-devtools") >= 2


def test_then_cursor_catalog_and_mind_python_stay_out_of_the_browser() -> None:
    """Then Cursor catalog has no chrome-devtools; Python mind is not a second browser loop."""
    loop = MIND_LOOP.read_text(encoding="utf-8")
    common = SEAT_COMMON.read_text(encoding="utf-8")
    mind_src = MIND_PY.read_text(encoding="utf-8")
    studio_at = loop.find("install_studio_mind_plugin")
    chrome_at = loop.find("install_chrome_devtools_plugin")
    assert studio_at != -1
    assert chrome_at != -1
    assert studio_at < chrome_at
    assert "install_chrome_devtools_plugin" in common
    assert "chrome-devtools" in common
    assert 'plugin install chrome-devtools' in common or '"chrome-devtools"' in common
    assert "palemon" not in mind_src.lower()
    assert "palemon" not in loop.lower()
    cursor = json.loads(CURSOR_MCP.read_text(encoding="utf-8"))
    servers = cursor.get("mcpServers") or {}
    assert list(servers) == ["taskboard"]
    for banned in ("chrome-devtools", "playwright", "browser-use"):
        assert banned not in servers
    assert "chrome_devtools" not in mind_src
    assert "navigate_page" not in mind_src
    assert "def parse_tool_calls" not in mind_src


def test_then_living_sky_docs_name_chrome_devtools_not_bot_cloudagent() -> None:
    """Then MIND/WIPE/qa-a document Grok catalog chrome-devtools playtest, not Bot CloudAgent."""
    mind = MIND_DOC.read_text(encoding="utf-8")
    wipe = WIPE_DOC.read_text(encoding="utf-8")
    soul = QA_A_SOUL.read_text(encoding="utf-8")
    assert "palemon" not in mind.lower()
    for label, text in (("MIND.md", mind), ("WIPE.md", wipe), ("qa-a SOUL.md", soul)):
        low = text.lower()
        assert "chrome-devtools" in low, label
        assert "127.0.0.1:5173" in text, label
        assert "not cursor" in low or "not cursor cli" in low, label
        assert any(n in low for n in BANNED_BOT_CLOUD) or "not bot" in low, label
        for banned in BANNED_BROWSERS:
            assert banned not in low, f"{label} must not name {banned}"
    assert "chrome-devtools-mcp" in mind
    assert "npx -y chrome-devtools-mcp@latest" in mind or "npx -y chrome-devtools-mcp@latest" in wipe
