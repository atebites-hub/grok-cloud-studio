"""LIV-67: list compact rows include runStatus and prUrl (Living Sky).

Agent `status=ACTIVE` is leftover membership. Capacity is the latest run
(`runStatus=RUNNING` vs `FINISHED`). Compact list rows must print
`runStatus=` and `prUrl=` so Directors can count live workers and open PRs
without N serial `status.sh` calls.

Distinct from leftover GCS #50 (`list --repo`) and #60 (`status --ids`).
Never Bot CloudAgent. Model stays grok-4.6 xhigh fast=false.
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parents[1]
CLOUD = REPO / "scripts" / "cloud"
LIST_SH = CLOUD / "list.sh"
LIST_LONG = CLOUD / "list-cloud-agents.sh"
STATUS_SH = CLOUD / "status.sh"
FAKE_KEY = "test-cursor-api-key-liv67-list"
EXAMPLE_REPO = "https://github.com/atebites-hub/grok-cloud-studio"
PR_LIVE = f"{EXAMPLE_REPO}/pull/67"
_KV_RE = re.compile(r"(\w+)=(\S*)")


def _script_env(home: Path, base: str, **extra: str) -> dict[str, str]:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "TMPDIR": str(home),
        "CURSOR_API_BASE": base,
        "GCS_CLOUD_REPO": EXAMPLE_REPO,
        "GCS_CLOUD_REF": "main",
        "GCS_SPAWN_WAITER": "0",
        "CLOUD_SPAWN_WAITER": "0",
        "CLOUD_CURL_CONNECT_TIMEOUT": "2",
        "CLOUD_CURL_MAX_TIME": "8",
        "LC_ALL": "C",
        "GCS_ROOT": str(REPO),
        "CURSOR_API_KEY": FAKE_KEY,
    }
    env.update(extra)
    return env


def _run(
    path: Path,
    args: list[str],
    env: dict[str, str],
    timeout: float = 25,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(path), *args],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
    )


def _basic_user(header: str | None) -> str:
    if not header or not header.startswith("Basic "):
        return ""
    raw = base64.b64decode(header.split(" ", 1)[1]).decode("utf-8")
    return raw.split(":", 1)[0]


def parse_compact_rows(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("CLOUD_"):
            continue
        if "id=" not in stripped:
            continue
        fields = {m.group(1): m.group(2) for m in _KV_RE.finditer(stripped)}
        if fields.get("id"):
            rows.append(fields)
    return rows


def row_by_id(rows: list[dict[str, str]], agent_id: str) -> dict[str, str]:
    for row in rows:
        if row.get("id") == agent_id:
            return row
    raise AssertionError(f"missing compact row for {agent_id}: {rows!r}")


@dataclass
class ListMockAPI:
    """REST stand-in: list items plus per-run payloads (optional delay)."""

    items: list[dict[str, Any]]
    runs: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    run_delay: float = 0.0
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
                api.auth_users.append(_basic_user(self.headers.get("Authorization")))
                parsed = urlparse(self.path)
                api.gets.append(parsed.path)
                parts = [p for p in parsed.path.split("/") if p]
                if parts == ["v1", "agents"]:
                    self._send(200, {"items": api.items})
                    return
                if len(parts) == 5 and parts[:2] == ["v1", "agents"] and parts[3] == "runs":
                    if api.run_delay > 0:
                        time.sleep(api.run_delay)
                    key = (parts[2], parts[4])
                    run = api.runs.get(key)
                    if run is None:
                        self._send(404, {"error": "not_found"})
                        return
                    self._send(200, run)
                    return
                if len(parts) == 3 and parts[:2] == ["v1", "agents"]:
                    agent_id = parts[2]
                    for item in api.items:
                        if item.get("id") == agent_id:
                            self._send(200, item)
                            return
                    self._send(404, {"error": "not_found"})
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

    def run_gets(self) -> list[str]:
        return [p for p in self.gets if "/runs/" in p]


def _fleet_items() -> list[dict[str, Any]]:
    return [
        {
            "id": "bc-live",
            "name": "liv-mechanic",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-live",
            "latestRunId": "run-live",
        },
        {
            "id": "bc-leftover",
            "name": "stale-shell",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-leftover",
            "latestRunId": "run-done",
        },
        {
            "id": "bc-empty",
            "name": "no-run",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-empty",
            "latestRunId": "",
        },
        {
            "id": "bc-missing",
            "name": "run-404",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-missing",
            "latestRunId": "run-gone",
        },
    ]


def _fleet_runs() -> dict[tuple[str, str], dict[str, Any]]:
    return {
        ("bc-live", "run-live"): {
            "id": "run-live",
            "agentId": "bc-live",
            "status": "RUNNING",
            "git": {
                "branches": [
                    {"branch": "cursor/liv-67", "prUrl": PR_LIVE},
                ]
            },
        },
        ("bc-leftover", "run-done"): {
            "id": "run-done",
            "agentId": "bc-leftover",
            "status": "FINISHED",
            "git": {"branches": [{"branch": "cursor/old"}]},
        },
    }


def test_list_compact_rows_include_run_status_and_pr_url(tmp_path: Path) -> None:
    with ListMockAPI(items=_fleet_items(), runs=_fleet_runs()) as api:
        proc = _run(LIST_SH, ["8"], _script_env(tmp_path, api.base))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert FAKE_KEY not in proc.stdout + proc.stderr
    assert "run_status=" not in proc.stdout
    rows = parse_compact_rows(proc.stdout)
    live = row_by_id(rows, "bc-live")
    leftover = row_by_id(rows, "bc-leftover")
    empty = row_by_id(rows, "bc-empty")
    missing = row_by_id(rows, "bc-missing")
    assert live["status"] == "ACTIVE"
    assert live["runStatus"] == "RUNNING"
    assert live["prUrl"] == PR_LIVE
    assert leftover["status"] == "ACTIVE"
    assert leftover["runStatus"] == "FINISHED"
    assert leftover["prUrl"] == "none"
    assert empty["runStatus"] == "none"
    assert empty["prUrl"] == "none"
    assert missing["runStatus"] == "none"
    assert missing["prUrl"] == "none"
    running = [r for r in rows if r.get("runStatus") == "RUNNING"]
    assert [r["id"] for r in running] == ["bc-live"]


def test_list_cloud_agents_wrapper_prints_same_compact_fields(tmp_path: Path) -> None:
    with ListMockAPI(items=_fleet_items()[:1], runs=_fleet_runs()) as api:
        proc = _run(LIST_LONG, ["5"], _script_env(tmp_path, api.base))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    live = row_by_id(parse_compact_rows(proc.stdout), "bc-live")
    assert live["runStatus"] == "RUNNING"
    assert live["prUrl"] == PR_LIVE


def test_list_fetches_latest_runs_in_parallel(tmp_path: Path) -> None:
    """Capacity beat: one list, not N serial status.sh / get_agent_run."""
    n = 8
    delay = 0.35
    items = [
        {
            "id": f"bc-{i}",
            "name": f"w{i}",
            "status": "ACTIVE",
            "url": f"https://cursor.com/agents/bc-{i}",
            "latestRunId": f"run-{i}",
        }
        for i in range(n)
    ]
    runs = {
        (f"bc-{i}", f"run-{i}"): {
            "id": f"run-{i}",
            "agentId": f"bc-{i}",
            "status": "RUNNING" if i % 2 == 0 else "FINISHED",
            "git": {
                "branches": (
                    [{"branch": f"b{i}", "prUrl": f"{EXAMPLE_REPO}/pull/{i}"}]
                    if i % 2 == 0
                    else [{"branch": f"b{i}"}]
                )
            },
        }
        for i in range(n)
    }
    serial_floor = delay * n
    with ListMockAPI(items=items, runs=runs, run_delay=delay) as api:
        t0 = time.monotonic()
        proc = _run(LIST_SH, [str(n)], _script_env(tmp_path, api.base), timeout=20)
        elapsed = time.monotonic() - t0
    assert proc.returncode == 0, proc.stdout + proc.stderr
    rows = parse_compact_rows(proc.stdout)
    assert len(rows) == n
    assert {r["runStatus"] for r in rows} == {"RUNNING", "FINISHED"}
    assert any(r.get("prUrl", "").startswith(EXAMPLE_REPO) for r in rows)
    assert len(api.run_gets()) == n
    assert elapsed < serial_floor * 0.55, (
        f"list fetched runs serially ({elapsed:.2f}s >= {serial_floor * 0.55:.2f}s); "
        "capacity beats must Promise.all / ThreadPoolExecutor latest runs"
    )
    status_gets = [p for p in api.gets if re.fullmatch(r"/v1/agents/bc-\d+", p)]
    assert not status_gets, "list must not N-serial GET /v1/agents/{id} (that is status.sh)"


def test_list_does_not_print_keys(tmp_path: Path) -> None:
    with ListMockAPI(items=_fleet_items()[:1], runs=_fleet_runs()) as api:
        proc = _run(LIST_SH, [], _script_env(tmp_path, api.base))
    blob = proc.stdout + proc.stderr
    assert FAKE_KEY not in blob
    assert proc.returncode == 0


def test_list_source_does_not_remint_repo_filter_or_status_ids() -> None:
    """Distinct from leftover GCS #50 (list --repo) and #60 (status --ids)."""
    list_sh = LIST_SH.read_text(encoding="utf-8")
    list_ts = (CLOUD / "sdk" / "list.ts").read_text(encoding="utf-8")
    list_long = LIST_LONG.read_text(encoding="utf-8")
    status_sh = STATUS_SH.read_text(encoding="utf-8")
    status_ts = (CLOUD / "sdk" / "status.ts").read_text(encoding="utf-8")
    for src, label in ((list_sh, "list.sh"), (list_ts, "list.ts"), (list_long, "list-cloud-agents.sh")):
        assert "--repo" not in src, f"{label} must not remint leftover #50 --repo"
    assert "--ids" not in status_sh
    assert "--ids" not in status_ts
    assert "MUST_LAUNCH" not in list_sh
    assert "capacity.py" not in list_sh


def test_sdk_list_compacts_runstatus_prurl_in_parallel() -> None:
    src = (CLOUD / "sdk" / "list.ts").read_text(encoding="utf-8")
    assert "runStatus=" in src
    assert "prUrl=" in src
    assert "Promise.all" in src
    assert "pickGit" in src


def test_footer_and_docs_living_sky_never_bot() -> None:
    footer = (REPO / "scripts" / "directors" / "common_footer.txt").read_text(encoding="utf-8")
    cloud_doc = (REPO / "docs" / "CLOUD.md").read_text(encoding="utf-8")
    readme = (CLOUD / "README.md").read_text(encoding="utf-8")
    blob = footer + cloud_doc + readme
    assert "runStatus" in blob
    assert "prUrl" in blob
    assert "Bot CloudAgent" in blob or "Bot as a CloudAgent" in blob
    assert "grok-4.6" in blob
    assert "xhigh" in blob
    assert "fast=false" in footer + cloud_doc + readme
    assert "Black Swan" not in blob
