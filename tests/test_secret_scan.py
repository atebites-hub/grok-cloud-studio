"""Repo-wide secret/lore scan must stay clean.

.cursor/mcp.json must fail closed on API key literals (including JSON
LINEAR_API_KEY values and Bearer tokens). Linear MCP may only use env refs
such as ${LINEAR_API_KEY} / ${env:LINEAR_API_KEY}.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN = ROOT / "scripts" / "secret_scan.py"
CURSOR_MCP = ROOT / ".cursor" / "mcp.json"
LINEAR_MCP_URL = "https://mcp.linear.app/mcp"


def _run_scan(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SCAN), "--root", str(root)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )


def _write_cursor_mcp(root: Path, servers: dict) -> Path:
    path = root / ".cursor" / "mcp.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"mcpServers": servers}, indent=2) + "\n", encoding="utf-8")
    return path


def _linear_token(tag: str) -> str:
    """Build a fake Linear key without embedding a complete literal in this file."""
    return "lin" + "_api_" + tag + ("x" * 20)


def test_secret_scan_clean() -> None:
    proc = _run_scan(ROOT)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "secret_scan=clean" in proc.stdout


def test_no_private_repo_default_in_launchers() -> None:
    banned = "atebites-hub/" + "palemon"
    roots = [ROOT / "scripts", ROOT / "docs", ROOT / "prompts"]
    hits: list[str] = []
    for folder in roots:
        for path in folder.rglob("*"):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if banned in text:
                hits.append(str(path.relative_to(ROOT)))
    assert hits == []


def test_secret_scan_fails_on_mcp_json_linear_api_key_literal(tmp_path: Path) -> None:
    token = _linear_token("envlit")
    _write_cursor_mcp(
        tmp_path,
        {
            "linear": {
                "url": LINEAR_MCP_URL,
                "env": {"LINEAR_API_KEY": token},
            }
        },
    )
    proc = _run_scan(tmp_path)
    blob = proc.stdout + proc.stderr
    assert proc.returncode != 0, blob
    assert "secret_scan=FAIL" in proc.stdout
    assert "mcp_api_key_literal" in blob
    assert ".cursor/mcp.json" in blob
    assert token not in blob


def test_secret_scan_fails_on_mcp_json_bearer_literal(tmp_path: Path) -> None:
    token = _linear_token("bearlit")
    _write_cursor_mcp(
        tmp_path,
        {
            "linear": {
                "url": LINEAR_MCP_URL,
                "headers": {"Authorization": "Bearer " + token},
            }
        },
    )
    proc = _run_scan(tmp_path)
    blob = proc.stdout + proc.stderr
    assert proc.returncode != 0, blob
    assert "secret_scan=FAIL" in proc.stdout
    assert "mcp_bearer_literal" in blob or "mcp_api_key_literal" in blob
    assert ".cursor/mcp.json" in blob
    assert token not in blob


def test_secret_scan_allows_mcp_json_linear_env_refs(tmp_path: Path) -> None:
    _write_cursor_mcp(
        tmp_path,
        {
            "taskboard": {
                "command": "bash",
                "args": ["${workspaceFolder}/scripts/studio/taskboard/run-mcp.sh"],
            },
            "linear": {
                "url": LINEAR_MCP_URL,
                "headers": {"Authorization": "Bearer ${LINEAR_API_KEY}"},
                "env": {"LINEAR_API_KEY": "${LINEAR_API_KEY}"},
            },
        },
    )
    proc = _run_scan(tmp_path)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "secret_scan=clean" in proc.stdout


def test_secret_scan_allows_env_colon_linear_ref(tmp_path: Path) -> None:
    _write_cursor_mcp(
        tmp_path,
        {
            "linear": {
                "url": LINEAR_MCP_URL,
                "headers": {"Authorization": "Bearer ${env:LINEAR_API_KEY}"},
            }
        },
    )
    proc = _run_scan(tmp_path)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "secret_scan=clean" in proc.stdout


def test_secret_scan_fails_on_linear_api_key_assignment(tmp_path: Path) -> None:
    token = _linear_token("assign")
    (tmp_path / "leak.env").write_text("LINEAR_API_KEY=" + token + "\n", encoding="utf-8")
    proc = _run_scan(tmp_path)
    blob = proc.stdout + proc.stderr
    assert proc.returncode != 0, blob
    assert "linear_key_assignment" in blob
    assert token not in blob


def test_committed_cursor_mcp_linear_uses_env_refs_only() -> None:
    raw = CURSOR_MCP.read_text(encoding="utf-8")
    data = json.loads(raw)
    servers = data.get("mcpServers") or {}
    assert "linear" in servers, "Linear MCP must be in .cursor/mcp.json (env refs only)"
    linear = servers["linear"]
    assert linear.get("url") == LINEAR_MCP_URL
    headers = linear.get("headers") or {}
    env = linear.get("env") or {}
    auth = str(headers.get("Authorization") or headers.get("authorization") or "")
    env_val = str(env.get("LINEAR_API_KEY") or "")
    assert "${LINEAR_API_KEY}" in auth or env_val in {
        "${LINEAR_API_KEY}",
        "${env:LINEAR_API_KEY}",
    }
    if auth:
        assert "Bearer" in auth
        assert "${LINEAR_API_KEY}" in auth or "${env:LINEAR_API_KEY}" in auth
    if env_val:
        assert env_val in {"${LINEAR_API_KEY}", "${env:LINEAR_API_KEY}"}
    assert "LINEAR_API_KEY=" not in raw
    low = raw.lower()
    assert "lin_api_" not in low
    for line in raw.splitlines():
        stripped = line.strip()
        if "LINEAR_API_KEY" in stripped and "${LINEAR_API_KEY}" not in stripped and "${env:LINEAR_API_KEY}" not in stripped:
            raise AssertionError("LINEAR_API_KEY must only appear as an env ref")
