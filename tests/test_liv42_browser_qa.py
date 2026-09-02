"""LIV-42 BDD: a Grok Build mind can open the Palemon client in a browser plugin.

Feature: Grok catalog live Chrome for visual QA
  Living Sky only. Never Bot CloudAgent. Never Cursor CLI browser tools.
  Never Playwright MCP (not in the Grok catalog). Two catalogs: do not copy
  GROK_HOME into `.cursor/mcp.json`.

  Scenario: a Grok Build mind can open the Palemon client for visual QA
    Given a Grok Build mind seat GROK_HOME
    And the Palemon client origin is http://127.0.0.1:5173/
    When seat MCP is registered in GROK_HOME/config.toml
    Then GROK_HOME/config.toml has [mcp_servers.chrome-devtools]
      as `npx -y chrome-devtools-mcp@latest`
    And qa-a can navigate_page that origin (chrome-devtools, not Python mind)
    And Cursor `.cursor/mcp.json` has no chrome-devtools (Linear + taskboard only)

  Scenario: a Grok Build mind can call chrome-devtools navigate_page
    Given qa-a GROK_HOME has [mcp_servers.chrome-devtools]
    When a grok-catalog MCP client (what grok does) tools/list and tools/call
    Then navigate_page opens http://127.0.0.1:5173/
    And Python mind.py did not issue the call (no second agent loop)

  Scenario: visual QA is one grok-catalog session
    Given qa-a GROK_HOME chrome-devtools
    When grok tools/call navigate_page then take_screenshot in one session
    Then both calls share one MCP pid
    And qa-a director prompt names that playtest
"""
from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
import tomllib
import uuid
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[1]
SEAT_MCP_PY = REPO / "scripts" / "directors" / "seat_grok_mcp.py"
CATALOG_MCP_PY = REPO / "scripts" / "directors" / "grok_catalog_mcp.py"
FAKE_CHROME_MCP = REPO / "tests" / "fakes" / "chrome_devtools_mcp.py"
SEAT_COMMON = REPO / "scripts" / "directors" / "seat-daemon-common.sh"
MIND_LOOP = REPO / "scripts" / "directors" / "seat-mind-loop.sh"
MIND_PY = REPO / "scripts" / "directors" / "mind.py"
MIND_DOC = REPO / "docs" / "studio" / "MIND.md"
WIPE_DOC = REPO / "docs" / "studio" / "WIPE.md"
QA_A_SOUL = REPO / "docs" / "studio" / "directors" / "souls" / "qa-a" / "SOUL.md"
QA_A_PROMPT = REPO / "prompts" / "qa_a_director_prompt.txt"
QA_A_TXT = REPO / "prompts" / "qa_a.txt"
DOCTOR = REPO / "doctor.sh"
CURSOR_MCP = REPO / ".cursor" / "mcp.json"
PLAYTEST_URL = "http://127.0.0.1:5173/"
BANNED_BROWSERS = ("playwright", "browser-use", "browser_use")
BANNED_BOT_CLOUD = ("bot cloudagent", "grok bot cloudagent")
NPX_CHROME_TOML = 'command = "npx"\nargs = ["-y", "chrome-devtools-mcp@latest"]'


def _load_py(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_seat_mcp() -> ModuleType:
    return _load_py(SEAT_MCP_PY, "gcs_seat_grok_mcp_liv42")


def _load_catalog() -> ModuleType:
    return _load_py(CATALOG_MCP_PY, "gcs_grok_catalog_mcp_liv42")


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


def _bind_chrome_devtools_fake(cfg: Path, fake: Path) -> None:
    """Point GROK_HOME chrome-devtools stdio at the fake (no live Chrome/npx)."""
    text = cfg.read_text(encoding="utf-8")
    assert NPX_CHROME_TOML in text, text
    replacement = (
        f"command = {json.dumps(sys.executable)}\n"
        f"args = [{json.dumps(str(fake))}]"
    )
    cfg.write_text(text.replace(NPX_CHROME_TOML, replacement, 1), encoding="utf-8")


def _install_qa_a_grok_mcp(tmp_path: Path) -> Path:
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
    grok_home = Path(env["GROK_HOME"])
    assert (grok_home / "config.toml").is_file()
    return grok_home


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
    assert parsed["mcp_servers"]["linear"]["url"] == "https://mcp.linear.app/mcp"
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
    assert parsed["mcp_servers"]["linear"]["url"] == "https://mcp.linear.app/mcp"
    cursor = json.loads(CURSOR_MCP.read_text(encoding="utf-8"))
    servers = cursor.get("mcpServers") or {}
    assert "chrome-devtools" not in servers
    assert "playwright" not in servers
    assert "browser-use" not in servers
    assert "taskboard" in servers


def test_when_seat_mcp_registers_chrome_devtools_then_mind_loop_does_not_plugin_install() -> None:
    """chrome-devtools is GROK_HOME stdio, not grok plugin install in seat-mind-loop.sh."""
    loop = MIND_LOOP.read_text(encoding="utf-8")
    common = SEAT_COMMON.read_text(encoding="utf-8")
    assert "install_studio_mind_plugin" in loop
    assert "install_chrome_devtools_plugin" not in loop
    assert "chrome-devtools" not in loop
    assert "install_chrome_devtools_plugin" not in common
    assert "chrome-devtools" in common
    assert "chrome-devtools-mcp" in common
    assert "plugin install chrome-devtools" not in common


def test_when_chrome_devtools_stdio_is_already_in_config_then_merge_is_idempotent(
    tmp_path: Path,
) -> None:
    """A second install_seat_grok_mcp keeps one chrome-devtools table (no plugin install)."""
    grok_home = _install_qa_a_grok_mcp(tmp_path)
    cfg = grok_home / "config.toml"
    first = tomllib.loads(cfg.read_text(encoding="utf-8"))
    assert first["mcp_servers"]["chrome-devtools"]["args"][-1] == "chrome-devtools-mcp@latest"
    env = _base_env(tmp_path)
    env["GROK_HOME"] = str(grok_home)
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
    text = cfg.read_text(encoding="utf-8")
    assert text.count("[mcp_servers.chrome-devtools]") == 1, text
    parsed = tomllib.loads(text)
    assert parsed["mcp_servers"]["linear"]["url"] == "https://mcp.linear.app/mcp"


def test_then_cursor_catalog_and_mind_python_stay_out_of_the_browser() -> None:
    """Then Cursor catalog has no chrome-devtools; Python mind is not a second browser loop."""
    loop = MIND_LOOP.read_text(encoding="utf-8")
    common = SEAT_COMMON.read_text(encoding="utf-8")
    mind_src = MIND_PY.read_text(encoding="utf-8")
    assert "install_studio_mind_plugin" in loop
    assert "install_chrome_devtools_plugin" not in loop
    assert "chrome-devtools" not in loop
    assert "install_chrome_devtools_plugin" not in common
    assert "chrome-devtools" in common
    assert "chrome-devtools-mcp" in common
    assert "palemon" not in mind_src.lower()
    assert "palemon" not in loop.lower()
    cursor = json.loads(CURSOR_MCP.read_text(encoding="utf-8"))
    servers = cursor.get("mcpServers") or {}
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
    assert "grok_catalog_mcp.py" in mind
    assert "tools/call" in mind
    assert "navigate_page" in mind
    assert "take_screenshot" in mind
    assert "tools/call" in soul.lower() or "navigate_page" in soul


def test_when_grok_catalog_client_calls_then_navigate_page_opens_playtest(
    tmp_path: Path,
) -> None:
    """When a grok-catalog MCP client tools/call navigate_page, Then the playtest origin is opened.

    This is the LIV-42 proof a Grok Build mind can call chrome-devtools.
    Live grok uses the same GROK_HOME table. Python mind.py does not.
    Fake chrome-devtools MCP only — no live Chrome, no npx, no Bot CloudAgent.
    """
    assert CATALOG_MCP_PY.is_file()
    assert FAKE_CHROME_MCP.is_file()
    grok_home = _install_qa_a_grok_mcp(tmp_path)
    cfg = grok_home / "config.toml"
    parsed = tomllib.loads(cfg.read_text(encoding="utf-8"))
    chrome = parsed["mcp_servers"]["chrome-devtools"]
    assert chrome["command"] == "npx"
    assert chrome["args"] == ["-y", "chrome-devtools-mcp@latest"]
    log = tmp_path / "chrome-devtools.calls.jsonl"
    _bind_chrome_devtools_fake(cfg, FAKE_CHROME_MCP)
    catalog = _load_catalog()
    names = catalog.list_mcp_tools(grok_home, "chrome-devtools")
    assert "navigate_page" in names
    assert "new_page" in names
    assert "take_screenshot" in names
    env = dict(os.environ)
    env["GCS_CHROME_DEVTOOLS_FAKE_LOG"] = str(log)
    result = catalog.call_chrome_devtools_navigate_page(grok_home, env=env)
    assert result.get("isError") is not True, result
    texts = [c.get("text", "") for c in result.get("content") or [] if isinstance(c, dict)]
    blob = " ".join(texts)
    assert PLAYTEST_URL in blob or PLAYTEST_URL.rstrip("/") in blob
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows, "fake chrome-devtools must record tools/call"
    assert any(
        row.get("name") == "navigate_page"
        and (row.get("arguments") or {}).get("url") == PLAYTEST_URL
        for row in rows
    )
    cursor = json.loads(CURSOR_MCP.read_text(encoding="utf-8"))
    assert "chrome-devtools" not in (cursor.get("mcpServers") or {})
    mind_src = MIND_PY.read_text(encoding="utf-8")
    assert "grok_catalog_mcp" not in mind_src
    assert "navigate_page" not in mind_src
    assert "call_chrome_devtools" not in mind_src


def test_when_qa_a_mind_turn_then_grok_can_reach_chrome_devtools(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When qa-a mind runs grok, Then that GROK_HOME still exposes chrome-devtools for tools/call."""
    state = tmp_path / "a2a-state"
    grok_home = state / "qa-a" / "grok-home"
    grok_home.mkdir(parents=True, exist_ok=True)
    log = tmp_path / "grok.argv.json"
    grok = _write_exec(
        tmp_path / "fake-bin" / "grok",
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        f"log = Path({str(log)!r})\n"
        "rows = json.loads(log.read_text()) if log.is_file() else []\n"
        "rows.append({'argv': sys.argv[1:], 'GROK_HOME': os.environ.get('GROK_HOME', '')})\n"
        "log.write_text(json.dumps(rows))\n"
        "sys.stdout.write(json.dumps({'ok': True, 'role': 'assistant'}))\n"
        "raise SystemExit(0)\n",
    )
    env = _base_env(tmp_path)
    env["GROK_HOME"] = str(grok_home)
    env["GCS_A2A_STATE"] = str(state)
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
    assert proc.returncode == 0, proc.stdout + proc.stderr
    parsed = tomllib.loads((grok_home / "config.toml").read_text(encoding="utf-8"))
    assert parsed["mcp_servers"]["chrome-devtools"]["command"] == "npx"

    mind = _load_py(MIND_PY, f"gcs_mind_liv42_{uuid.uuid4().hex[:8]}")
    db = state / "taskboard" / "taskboard.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_text("", encoding="utf-8")
    monkeypatch.setattr(mind, "STATE_DIR", state)
    monkeypatch.setattr(mind, "ROOT", REPO)
    monkeypatch.setenv("GCS_A2A_STATE", str(state))
    monkeypatch.setenv("GCS_ROOT", str(REPO))
    monkeypatch.setenv("GCS_TASKBOARD_DB", str(db))
    monkeypatch.setenv("GROK_BIN", str(grok))
    monkeypatch.delenv("GCS_MIND_RUNNER", raising=False)
    inbox = state / "qa-a" / "inbox.jsonl"
    inbox.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "taskId": "liv42-playtest",
        "contextId": "ctx-liv42",
        "parts": [{"kind": "text", "text": "open the playtest client for visual QA"}],
        "metadata": {"from": "floor"},
    }
    inbox.write_text(json.dumps(rec) + "\n", encoding="utf-8")
    result = mind.process_once("qa-a")
    assert result.get("consumed") == 1, result
    rows = json.loads(log.read_text(encoding="utf-8"))
    assert rows, "mind must launch grok"
    assert grok_home.as_posix() in rows[0]["GROK_HOME"]
    call_log = tmp_path / "chrome-devtools.calls.jsonl"
    _bind_chrome_devtools_fake(grok_home / "config.toml", FAKE_CHROME_MCP)
    catalog = _load_catalog()
    catalog_env = dict(os.environ)
    catalog_env["GCS_CHROME_DEVTOOLS_FAKE_LOG"] = str(call_log)
    names = catalog.list_mcp_tools(grok_home, "chrome-devtools")
    assert "navigate_page" in names
    called = catalog.call_chrome_devtools_navigate_page(grok_home, env=catalog_env)
    assert called.get("isError") is not True, called
    recorded = [json.loads(line) for line in call_log.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any((row.get("arguments") or {}).get("url") == PLAYTEST_URL for row in recorded)
    assert "navigate_page" not in MIND_PY.read_text(encoding="utf-8")


def test_when_visual_qa_then_one_session_navigates_then_screenshots(
    tmp_path: Path,
) -> None:
    """When visual QA runs, Then navigate_page and take_screenshot share one MCP pid."""
    grok_home = _install_qa_a_grok_mcp(tmp_path)
    cfg = grok_home / "config.toml"
    log = tmp_path / "chrome-devtools.calls.jsonl"
    _bind_chrome_devtools_fake(cfg, FAKE_CHROME_MCP)
    catalog = _load_catalog()
    env = dict(os.environ)
    env["GCS_CHROME_DEVTOOLS_FAKE_LOG"] = str(log)
    result = catalog.call_chrome_devtools_visual_qa(grok_home, env=env)
    assert result.get("isError") is not True, result
    assert result.get("url") == PLAYTEST_URL
    nav = result.get("navigate_page") or {}
    shot = result.get("take_screenshot") or {}
    assert nav.get("isError") is not True, nav
    assert shot.get("isError") is not True, shot
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
    names = [row.get("name") for row in rows]
    assert "navigate_page" in names
    assert "take_screenshot" in names
    assert names.index("navigate_page") < names.index("take_screenshot")
    nav_row = next(row for row in rows if row.get("name") == "navigate_page")
    shot_row = next(row for row in rows if row.get("name") == "take_screenshot")
    assert (nav_row.get("arguments") or {}).get("url") == PLAYTEST_URL
    assert nav_row.get("pid")
    assert nav_row.get("pid") == shot_row.get("pid")
    mind_src = MIND_PY.read_text(encoding="utf-8")
    assert "take_screenshot" not in mind_src
    assert "call_chrome_devtools_visual_qa" not in mind_src
    cursor = json.loads(CURSOR_MCP.read_text(encoding="utf-8"))
    assert "chrome-devtools" not in (cursor.get("mcpServers") or {})


def test_then_qa_a_prompt_and_doctor_name_chrome_devtools_playtest() -> None:
    """Then qa-a prompts tell grok to playtest; doctor WARNs npx and lists grok_catalog_mcp.py."""
    prompt = QA_A_PROMPT.read_text(encoding="utf-8")
    short = QA_A_TXT.read_text(encoding="utf-8")
    doctor = DOCTOR.read_text(encoding="utf-8")
    for label, text in (("qa_a_director_prompt.txt", prompt), ("qa_a.txt", short)):
        low = text.lower()
        assert "chrome-devtools" in low, label
        assert "127.0.0.1:5173" in text, label
        assert "take_screenshot" in low or "navigate_page" in low, label
        assert "not cursor" in low or "not cursor cli" in low, label
        for banned in BANNED_BROWSERS:
            assert banned not in low, f"{label} must not name {banned}"
    assert "scripts/directors/grok_catalog_mcp.py" in doctor
    assert "npx" in doctor
    assert "chrome-devtools" in doctor
    assert "WARN" in doctor
