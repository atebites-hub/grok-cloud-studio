"""Cursor Cloud Extra High Linear MCP via .cursor/mcp.json (cloud-env).

Cloud specialists cannot scrape GROK_HOME. Linear lives in the Cursor catalog
only: Linear HTTP + taskboard. LINEAR_API_KEY comes from the cloud snapshot,
dashboard Secrets, or process env — never hardcoded.

Grok minds keep a separate GROK_HOME catalog (not copied here). Studio Linear
is Living Sky (linear.app/livingsky, LIV). NEVER Black Swan Money.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CURSOR_MCP = REPO / ".cursor" / "mcp.json"
CLOUD_DOC = REPO / "docs" / "CLOUD.md"
MIND_DOC = REPO / "docs" / "studio" / "MIND.md"
SECRET_SCAN = REPO / "scripts" / "secret_scan.py"
GITIGNORE = REPO / ".gitignore"
DOT_ENV_EXAMPLE = REPO / ".env.example"
STUDIO_ENV_EXAMPLE = REPO / "studio.env.example"
AGENTS = REPO / "AGENTS.md"

LINEAR_MCP_URL = "https://mcp.linear.app/mcp"
LIVING_SKY_HOST = "linear.app/livingsky"
BLACK_SWAN = "Black Swan Money"
BANNED_GROK_CATALOG = (
    "higgsfield",
    "studio-mind",
    "chrome-devtools",
    "GROK_HOME",
    "config.toml",
    "mcp_servers",
)


def _mcp_servers() -> dict:
    data = json.loads(CURSOR_MCP.read_text(encoding="utf-8"))
    servers = data.get("mcpServers")
    assert isinstance(servers, dict), data
    return servers


def test_cursor_mcp_json_is_linear_plus_taskboard_only() -> None:
    servers = _mcp_servers()
    assert set(servers) == {"taskboard", "linear"}, servers
    linear = servers["linear"]
    assert linear.get("url") == LINEAR_MCP_URL
    headers = linear.get("headers") or {}
    auth = str(headers.get("Authorization") or headers.get("authorization") or "")
    assert "Bearer" in auth
    assert "${LINEAR_API_KEY}" in auth
    blob = json.dumps(servers)
    low = blob.lower()
    for banned in BANNED_GROK_CATALOG:
        assert banned.lower() not in low, banned
    assert "lin_api_" not in low
    assert BLACK_SWAN.lower() not in low
    assert "ak" not in servers
    taskboard = servers["taskboard"]
    joined = " ".join(
        str(x) for x in ([taskboard.get("command", "")] + list(taskboard.get("args") or []))
    )
    assert "run-mcp.sh" in joined or "run-mcp.sh" in blob
    assert "scripts/studio/taskboard" in blob


def test_mcp_json_never_hardcodes_linear_api_key() -> None:
    raw = CURSOR_MCP.read_text(encoding="utf-8")
    assert "LINEAR_API_KEY=" not in raw
    assert "${LINEAR_API_KEY}" in raw
    assert "lin_" not in raw.lower() or "linear.app" in raw.lower()
    for line in raw.splitlines():
        stripped = line.strip()
        if "LINEAR_API_KEY" in stripped and "${LINEAR_API_KEY}" not in stripped:
            raise AssertionError("LINEAR_API_KEY must only appear as ${LINEAR_API_KEY}")


def test_cloud_and_mind_docs_split_linear_catalogs() -> None:
    cloud = CLOUD_DOC.read_text(encoding="utf-8")
    mind = MIND_DOC.read_text(encoding="utf-8")
    cloud_low = cloud.lower()
    mind_low = mind.lower()
    assert "linear" in cloud_low
    assert ".cursor/mcp.json" in cloud or "mcp.json" in cloud_low
    assert "linear_api_key" in cloud_low
    assert "cannot scrape" in cloud_low or "grok_home" in cloud_low
    assert "snapshot" in cloud_low or "secret" in cloud_low
    assert "save_comment" in cloud_low
    assert LIVING_SKY_HOST in cloud_low or "livingsky" in cloud_low
    assert "living sky" in cloud_low
    assert "never" in cloud_low and BLACK_SWAN.lower() in cloud_low
    assert "LIV" in cloud
    assert "palemon" not in mind_low
    assert "GROK_HOME" in mind
    assert "linear" in mind_low
    assert ".cursor/mcp.json" in mind
    assert "do not copy" in mind_low
    assert "LINEAR_API_KEY" in mind
    assert LIVING_SKY_HOST in mind_low or "livingsky" in mind_low
    assert "living sky" in mind_low
    assert "never" in mind_low and BLACK_SWAN.lower() in mind_low
    assert "LIV" in mind
    assert "save_comment" in mind_low


def test_secret_scan_flags_hardcoded_linear_api_key(tmp_path: Path) -> None:
    fake = "lin_" + ("a" * 24)
    poisoned = tmp_path / "leak.env"
    poisoned.write_text("LINEAR_API_KEY=" + fake + "\n", encoding="utf-8")
    proc = subprocess.run(
        ["python3", str(SECRET_SCAN), "--root", str(tmp_path)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=15,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode != 0, blob
    assert "linear_key_assignment" in blob
    assert fake not in blob


def test_gitignore_and_env_examples_document_linear_secret_without_value() -> None:
    ignore = GITIGNORE.read_text(encoding="utf-8")
    assert "linear.env" in ignore
    for path in (DOT_ENV_EXAMPLE, STUDIO_ENV_EXAMPLE):
        text = path.read_text(encoding="utf-8")
        assert "LINEAR_API_KEY" in text
        assert "livingsky" in text.lower() or "living sky" in text.lower()
        assert BLACK_SWAN in text
        assert "never" in text.lower()
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("LINEAR_API_KEY=") and not stripped.startswith("#"):
                raise AssertionError(f"{path.name} must not assign LINEAR_API_KEY")


def test_agents_md_names_two_runtime_linear_and_living_sky() -> None:
    text = AGENTS.read_text(encoding="utf-8")
    low = text.lower()
    assert "linear" in low
    assert ".cursor/mcp.json" in text
    assert "GROK_HOME" in text
    assert "livingsky" in low or "living sky" in low
    assert BLACK_SWAN.lower() in low
    assert "never" in low
    assert "LINEAR_API_KEY" in text
