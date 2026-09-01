"""MCP cloud_list + list helper: print runStatus, not only agent ACTIVE.

Bash list.sh runStatus is PR #29 — this covers the Cursor Cloud MCP plugin
and the Python list helper it uses. ACTIVE + FINISHED leftovers are not
live workers.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
MCP = ROOT / "scripts" / "mcp" / "gcs_mcp.py"
HELPER = ROOT / "scripts" / "cloud" / "list_helper.py"
CURSOR_CLOUD_PLUGIN = ROOT / "plugins" / "cursor-cloud"
FAKE_KEY = "test-cursor-api-key-mcp-list"

sys.path.insert(0, str(ROOT / "scripts" / "cloud"))
from list_helper import (  # noqa: E402
    format_list_row,
    is_live_worker,
    list_cloud_agents,
    map_run_status,
)


def _rpc(plane: str, method: str, params: dict | None = None, env: dict[str, str] | None = None) -> dict:
    msg = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    merged = {**os.environ, "GCS_ROOT": str(ROOT), "GCS_MCP_NDJSON": "1"}
    if env:
        merged.update(env)
    proc = subprocess.run(
        ["python3", str(MCP), "--plane", plane, "--ndjson"],
        cwd=str(ROOT),
        input=json.dumps(msg) + "\n",
        capture_output=True,
        text=True,
        timeout=15,
        env=merged,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.splitlines()[0])


@dataclass
class ListMockAPI:
    list_items: list[dict[str, Any]] = field(default_factory=list)
    run_status_by_id: dict[str, str] = field(default_factory=dict)
    run_not_found_ids: set[str] = field(default_factory=set)
    gets: list[str] = field(default_factory=list)
    auth_users: list[str] = field(default_factory=list)
    _httpd: ThreadingHTTPServer | None = None
    _thread: threading.Thread | None = None
    base: str = ""

    def __enter__(self) -> "ListMockAPI":
        api = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: Any) -> None:
                return

            def _send(self, code: int, payload: dict[str, Any] | None = None) -> None:
                blob = b"" if payload is None else json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(blob)))
                self.end_headers()
                if blob:
                    self.wfile.write(blob)

            def do_GET(self) -> None:
                header = self.headers.get("Authorization") or ""
                user = ""
                if header.startswith("Basic "):
                    raw = base64.b64decode(header.split(" ", 1)[1]).decode("utf-8")
                    user = raw.split(":", 1)[0]
                api.auth_users.append(user)
                parsed = urlparse(self.path)
                api.gets.append(parsed.path)
                parts = [p for p in parsed.path.split("/") if p]
                if parts == ["v1", "agents"]:
                    self._send(200, {"items": api.list_items})
                    return
                if len(parts) == 5 and parts[:2] == ["v1", "agents"] and parts[3] == "runs":
                    run_id = parts[4]
                    if run_id in api.run_not_found_ids:
                        self._send(404, {"error": "not_found"})
                        return
                    status = api.run_status_by_id.get(run_id, "RUNNING")
                    self._send(200, {"id": run_id, "agentId": parts[2], "status": status})
                    return
                self._send(404, {"error": "not_found"})

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self._httpd.server_address[1]}"
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)


def _leftover_and_live_items() -> list[dict[str, Any]]:
    return [
        {
            "id": "bc-leftover",
            "name": "done-grunt",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-leftover",
            "latestRunId": "run-done",
        },
        {
            "id": "bc-live",
            "name": "busy-grunt",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-live",
            "latestRunId": "run-live",
        },
        {
            "id": "bc-idle",
            "name": "no-run",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-idle",
            "latestRunId": "",
        },
    ]


def _row(text: str, agent_id: str) -> str:
    rows = [line for line in text.splitlines() if agent_id in line]
    assert rows, text
    return rows[0]


def test_map_run_status_normalizes_empty_and_case() -> None:
    assert map_run_status(None) == "none"
    assert map_run_status("") == "none"
    assert map_run_status("running") == "RUNNING"
    assert map_run_status("FINISHED") == "FINISHED"


def test_format_list_row_prints_run_status_beside_agent_status() -> None:
    leftover = format_list_row(
        {
            "id": "bc-leftover",
            "status": "ACTIVE",
            "name": "done-grunt",
            "url": "https://cursor.com/agents/bc-leftover",
            "latestRunId": "run-done",
        },
        "FINISHED",
    )
    live = format_list_row(
        {
            "id": "bc-live",
            "status": "ACTIVE",
            "name": "busy-grunt",
            "url": "https://cursor.com/agents/bc-live",
            "latestRunId": "run-live",
        },
        "RUNNING",
    )
    assert "status=ACTIVE" in leftover
    assert "runStatus=FINISHED" in leftover
    assert "runStatus=RUNNING" not in leftover
    assert "status=ACTIVE" in live
    assert "runStatus=RUNNING" in live
    assert "runStatus=FINISHED" not in live


def test_active_finished_leftover_is_not_a_live_worker() -> None:
    assert is_live_worker("ACTIVE", "FINISHED") is False
    assert is_live_worker("ACTIVE", "RUNNING") is True
    assert is_live_worker("ACTIVE", "CREATING") is True
    assert is_live_worker("ACTIVE", "ERROR") is False
    assert is_live_worker("ACTIVE", "none") is False


def test_list_helper_fetches_latest_run_status(tmp_path: Path) -> None:
    items = _leftover_and_live_items()
    with ListMockAPI(
        list_items=items,
        run_status_by_id={"run-done": "FINISHED", "run-live": "RUNNING"},
    ) as api:
        env = {
            "CURSOR_API_BASE": api.base,
            "CURSOR_API_KEY": FAKE_KEY,
            "HOME": str(tmp_path),
            "CLOUD_CURL_MAX_TIME": "5",
        }
        old = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        try:
            text, ok = list_cloud_agents(limit=20)
        finally:
            for key, value in old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
    assert ok, text
    leftover = _row(text, "bc-leftover")
    live = _row(text, "bc-live")
    idle = _row(text, "bc-idle")
    assert "runStatus=FINISHED" in leftover
    assert "runStatus=RUNNING" in live
    assert "runStatus=none" in idle
    assert any(path.endswith("/runs/run-done") for path in api.gets), api.gets
    assert any(path.endswith("/runs/run-live") for path in api.gets), api.gets
    assert FAKE_KEY not in text


def test_list_helper_missing_run_is_run_status_none(tmp_path: Path) -> None:
    items = [
        {
            "id": "bc-stale-id",
            "name": "ghost-run",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-stale-id",
            "latestRunId": "run-missing",
        }
    ]
    with ListMockAPI(list_items=items, run_not_found_ids={"run-missing"}) as api:
        env = {
            "CURSOR_API_BASE": api.base,
            "CURSOR_API_KEY": FAKE_KEY,
            "HOME": str(tmp_path),
            "CLOUD_CURL_MAX_TIME": "5",
        }
        old = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        try:
            text, ok = list_cloud_agents(limit=20)
        finally:
            for key, value in old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
    assert ok, text
    row = _row(text, "bc-stale-id")
    assert "status=ACTIVE" in row
    assert "runStatus=none" in row
    assert FAKE_KEY not in text


def test_cloud_mcp_advertises_cloud_list_with_run_status() -> None:
    reply = _rpc("cloud", "tools/list")
    tools = {t["name"]: t for t in reply["result"]["tools"]}
    assert "cloud_list" in tools
    desc = tools["cloud_list"]["description"]
    assert "runStatus" in desc
    assert "RUNNING" in desc
    assert "FINISHED" in desc


def test_mcp_cloud_list_prints_run_status_not_only_agent_active(tmp_path: Path) -> None:
    """Directors must see RUNNING vs FINISHED; leftover ACTIVE is not a worker."""
    items = _leftover_and_live_items()
    with ListMockAPI(
        list_items=items,
        run_status_by_id={"run-done": "FINISHED", "run-live": "RUNNING"},
    ) as api:
        reply = _rpc(
            "cloud",
            "tools/call",
            {"name": "cloud_list", "arguments": {"limit": "20"}},
            env={
                "CURSOR_API_BASE": api.base,
                "CURSOR_API_KEY": FAKE_KEY,
                "HOME": str(tmp_path),
                "CLOUD_CURL_MAX_TIME": "5",
            },
        )
    result = reply["result"]
    assert result.get("isError") is False, result
    text = result["content"][0]["text"]
    leftover = _row(text, "bc-leftover")
    live = _row(text, "bc-live")
    assert "status=ACTIVE" in leftover
    assert "runStatus=FINISHED" in leftover
    assert "status=ACTIVE" in live
    assert "runStatus=RUNNING" in live
    assert FAKE_KEY not in text
    assert any(path.endswith("/runs/run-done") for path in api.gets), api.gets


def test_mcp_cloud_list_uses_list_helper_not_bash_list_sh() -> None:
    """Do not twin bash list.sh PR #29; MCP must resolve runStatus via the helper."""
    src = MCP.read_text(encoding="utf-8")
    assert "cloud_list" in src
    assert "list_helper" in src
    assert "list-cloud-agents.sh" not in src.split("cloud_list", 1)[-1][:800]


def test_node_cursor_cloud_plugin_routes_list_through_helper() -> None:
    src = (ROOT / "plugins" / "gcs-cursor-cloud" / "server.mjs").read_text(encoding="utf-8")
    assert "cloud_list" in src
    assert "list_helper.py" in src
    assert "runStatus" in src or "list_helper.py" in src


def test_cursor_cloud_plugin_never_bot_cloudagent() -> None:
    banned = "Bot " + "CloudAgent"
    paths = [
        CURSOR_CLOUD_PLUGIN / "server.py",
        CURSOR_CLOUD_PLUGIN / "README.md",
        MCP,
        HELPER,
        ROOT / "plugins" / "gcs-cursor-cloud" / "server.mjs",
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert banned not in text, path
