"""Occupancy beat: latest runStatus via listRuns; CREATING maps as RUNNING.

Leftover ACTIVE+FINISHED is not a worker. Split Palemon vs GCS toward
floor 8 per bound repo. Distinct from #142 catalog nextCursor paginate
and HOLD #132 listRuns concurrency/timeout. Never Bot CloudAgent.
"""
from __future__ import annotations

import base64
import importlib.util
import json
import os
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import parse_qs, urlparse

REPO = Path(__file__).resolve().parents[1]
CLOUD = REPO / "scripts" / "cloud"
OCCUPANCY_PY = CLOUD / "occupancy_count.py"
OCCUPANCY_SH = CLOUD / "occupancy-count.sh"
OCCUPANCY_TS = CLOUD / "sdk" / "occupancy.ts"
CATALOG_PY = CLOUD / "list_catalog.py"
LATEST_PY = CLOUD / "latest_run.py"
FOOTER = REPO / "scripts" / "directors" / "common_footer.txt"
CLOUD_DOC = REPO / "docs" / "CLOUD.md"
README = CLOUD / "README.md"
FAKE_KEY = "test-cursor-api-key-occupancy-listruns"
GAME = "pale" + "mon"
PALEMON_REPO = "https://github.com/example/" + GAME
GCS_REPO = "https://github.com/atebites-hub/grok-cloud-studio"
FLOOR = 8


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _script_env(home: Path, base: str, **extra: str) -> dict[str, str]:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "TMPDIR": str(home),
        "CURSOR_API_BASE": base,
        "CURSOR_API_KEY": FAKE_KEY,
        "CLOUD_FORCE_REST": "1",
        "LC_ALL": "C",
        "GCS_ROOT": str(REPO),
        "GCS_CLOUD_MIN_RUNNING": str(FLOOR),
    }
    env.update(extra)
    return env


def _run_occupancy(env: dict[str, str], *, timeout: float = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(OCCUPANCY_SH)],
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


def _catalog(items: list[dict[str, Any]], pages: int = 1) -> Any:
    cat = _load(CATALOG_PY, "gcs_list_catalog_listruns")
    return cat.CatalogResult(items=items, pages=pages)


@dataclass
class OccupancyListRunsAPI:
    """REST stand-in: catalog + GET /v1/agents/{id}/runs collection (listRuns)."""

    list_items: list[dict[str, Any]] = field(default_factory=list)
    runs_by_agent: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    list_http: int = 200
    runs_http: int = 200
    gets: list[str] = field(default_factory=list)
    auth_users: list[str] = field(default_factory=list)
    _httpd: ThreadingHTTPServer | None = None
    _thread: threading.Thread | None = None
    base: str = ""

    def __enter__(self) -> "OccupancyListRunsAPI":
        api = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: Any) -> None:
                return

            def _send(self, code: int, payload: Any = None) -> None:
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
                    if api.list_http != 200:
                        self._send(api.list_http, {"error": "list_failed"})
                        return
                    qs = parse_qs(parsed.query, keep_blank_values=True)
                    try:
                        limit = int((qs.get("limit") or ["100"])[0])
                    except ValueError:
                        limit = 100
                    self._send(200, {"items": api.list_items[: max(limit, 1)]})
                    return
                if len(parts) == 4 and parts[:2] == ["v1", "agents"] and parts[3] == "runs":
                    if api.runs_http != 200:
                        self._send(api.runs_http, {"error": "runs_failed"})
                        return
                    agent_id = parts[2]
                    self._send(200, {"items": api.runs_by_agent.get(agent_id, [])})
                    return
                if len(parts) == 5 and parts[:2] == ["v1", "agents"] and parts[3] == "runs":
                    # Pinned leftover GET — occupancy must not treat this as latest.
                    run_id = parts[4]
                    self._send(200, {"id": run_id, "status": "FINISHED"})
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


def test_creating_maps_as_running_toward_floor() -> None:
    occ = _load(OCCUPANCY_PY, "gcs_occupancy_listruns")
    catalog = _catalog(
        [{"id": "bc-boot", "status": "ACTIVE", "latestRunId": "run-boot"}],
    )
    summary = occ.occupancy_from_catalog(
        catalog,
        lambda _aid, _rid: "CREATING",
    )
    assert summary.creating == 1
    assert summary.running == 1
    assert occ.count_running(summary) == 1
    assert summary.leftover_active == 0
    line = occ.format_occupancy_line(summary)
    assert "running=1" in line
    assert "creating=1" in line


def test_leftover_active_finished_is_not_a_worker() -> None:
    occ = _load(OCCUPANCY_PY, "gcs_occupancy_listruns")
    catalog = _catalog(
        [
            {
                "id": "bc-leftover",
                "status": "ACTIVE",
                "latestRunId": "run-done",
                "repos": [{"url": GCS_REPO}],
            },
            {
                "id": "bc-live",
                "status": "ACTIVE",
                "latestRunId": "run-live",
                "repos": [{"url": GCS_REPO}],
            },
        ],
    )
    runs = {"run-done": "FINISHED", "run-live": "RUNNING"}
    summary = occ.occupancy_from_catalog(
        catalog,
        lambda _aid, rid: runs.get(rid, "none"),
    )
    assert summary.running == 1
    assert summary.leftover_active == 1
    assert summary.creating == 0
    assert summary.gcs == 1
    assert summary.palemon == 0


def test_listruns_picks_newer_creating_over_stale_latest_run_id() -> None:
    occ = _load(OCCUPANCY_PY, "gcs_occupancy_listruns")
    catalog = _catalog(
        [
            {
                "id": "bc-stale",
                "status": "ACTIVE",
                "latestRunId": "run-old",
                "repos": [{"url": PALEMON_REPO}],
            },
        ],
    )
    listed = [
        {"id": "run-old", "status": "FINISHED", "createdAt": 1_000},
        {
            "id": "run-new",
            "status": "CREATING",
            "createdAt": 2_000,
            "git": {"branches": [{"repoUrl": PALEMON_REPO}]},
        },
    ]
    summary = occ.occupancy_from_catalog(
        catalog,
        lambda _aid, _rid: "FINISHED",
        fetch_runs=lambda _aid: listed,
    )
    assert summary.running == 1
    assert summary.creating == 1
    assert summary.leftover_active == 0
    assert summary.palemon == 1
    assert summary.gcs == 0
    assert summary.palemon_must == 1
    assert summary.gcs_must == 1
    assert summary.cap == FLOOR


def test_palemon_vs_gcs_split_toward_floor_eight() -> None:
    occ = _load(OCCUPANCY_PY, "gcs_occupancy_listruns")
    catalog = _catalog(
        [
            {
                "id": "bc-game",
                "status": "ACTIVE",
                "latestRunId": "run-game",
                "repos": [{"url": PALEMON_REPO}],
            },
            {
                "id": "bc-studio",
                "status": "ACTIVE",
                "latestRunId": "run-studio",
                "repos": [{"url": GCS_REPO}],
            },
            {
                "id": "bc-studio-2",
                "status": "ACTIVE",
                "latestRunId": "run-studio-2",
                "repos": [{"url": GCS_REPO}],
            },
            {
                "id": "bc-done",
                "status": "ACTIVE",
                "latestRunId": "run-done",
                "repos": [{"url": GCS_REPO}],
            },
        ],
    )
    by_agent = {
        "bc-game": [
            {
                "id": "run-game",
                "status": "RUNNING",
                "createdAt": 3,
                "git": {"branches": [{"repoUrl": PALEMON_REPO}]},
            },
        ],
        "bc-studio": [
            {
                "id": "run-studio",
                "status": "CREATING",
                "createdAt": 4,
                "git": {"branches": [{"repoUrl": GCS_REPO}]},
            },
        ],
        "bc-studio-2": [
            {
                "id": "run-studio-2",
                "status": "RUNNING",
                "createdAt": 5,
                "git": {"branches": [{"repoUrl": GCS_REPO}]},
            },
        ],
        "bc-done": [
            {
                "id": "run-done",
                "status": "FINISHED",
                "createdAt": 1,
                "git": {"branches": [{"repoUrl": GCS_REPO}]},
            },
        ],
    }
    summary = occ.occupancy_from_catalog(
        catalog,
        lambda _aid, _rid: "none",
        fetch_runs=lambda aid: by_agent.get(aid, []),
    )
    assert summary.running == 3
    assert summary.creating == 1
    assert summary.leftover_active == 1
    assert summary.palemon == 1
    assert summary.gcs == 2
    assert summary.cap == FLOOR
    assert summary.palemon_must == 1
    assert summary.gcs_must == 1
    line = occ.format_occupancy_line(summary)
    assert line.startswith("CLOUD_OCCUPANCY ")
    assert "palemon=1" in line
    assert "gcs=2" in line
    assert "cap=8" in line
    assert "palemon_must=1" in line
    assert "gcs_must=1" in line
    gcs_full = occ.OccupancySummary(
        running=8,
        leftover_active=0,
        creating=0,
        listed=8,
        pages=1,
        palemon=8,
        gcs=8,
        cap=8,
        palemon_must=0,
        gcs_must=0,
    )
    full_line = occ.format_occupancy_line(gcs_full)
    assert "palemon_must=0" in full_line
    assert "gcs_must=0" in full_line
    assert "running=8" in full_line


def test_cli_counts_listruns_latest_not_pinned_leftover(tmp_path: Path) -> None:
    items = [
        {
            "id": "bc-stale",
            "name": "stale-grunt",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-stale",
            "latestRunId": "run-old",
            "repos": [{"url": PALEMON_REPO}],
        },
        {
            "id": "bc-studio",
            "name": "studio-grunt",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-studio",
            "latestRunId": "run-studio",
            "repos": [{"url": GCS_REPO}],
        },
        {
            "id": "bc-leftover",
            "name": "done-grunt",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-leftover",
            "latestRunId": "run-done",
            "repos": [{"url": GCS_REPO}],
        },
    ]
    runs = {
        "bc-stale": [
            {"id": "run-old", "status": "FINISHED", "createdAt": 1_000},
            {
                "id": "run-boot",
                "status": "CREATING",
                "createdAt": 2_000,
                "git": {"branches": [{"repoUrl": PALEMON_REPO}]},
            },
        ],
        "bc-studio": [
            {
                "id": "run-studio",
                "status": "RUNNING",
                "createdAt": 3_000,
                "git": {"branches": [{"repoUrl": GCS_REPO}]},
            },
        ],
        "bc-leftover": [
            {
                "id": "run-done",
                "status": "FINISHED",
                "createdAt": 900,
                "git": {"branches": [{"repoUrl": GCS_REPO}]},
            },
        ],
    }
    with OccupancyListRunsAPI(list_items=items, runs_by_agent=runs) as api:
        env = _script_env(tmp_path, api.base)
        listed = _run_occupancy(env)
    blob = listed.stdout + listed.stderr
    assert listed.returncode == 0, blob
    line = listed.stdout.strip().splitlines()[-1]
    assert line.startswith("CLOUD_OCCUPANCY ")
    assert "running=2" in line
    assert "creating=1" in line
    assert "leftover_active=1" in line
    assert "palemon=1" in line
    assert "gcs=1" in line
    assert "cap=8" in line
    assert "palemon_must=1" in line
    assert "gcs_must=1" in line
    collections = [p for p in api.gets if p.rstrip("/").endswith("/runs")]
    pinned = [p for p in api.gets if "/runs/" in p and not p.rstrip("/").endswith("/runs")]
    assert collections, api.gets
    assert "/v1/agents/bc-stale/runs" in collections
    assert "/v1/agents/bc-studio/runs" in collections
    assert not pinned, f"occupancy must use listRuns collection, not leftover GET: {pinned}"
    assert FAKE_KEY not in blob
    assert all(user == FAKE_KEY for user in api.auth_users)


def test_cli_runs_collection_error_fail_closed(tmp_path: Path) -> None:
    items = [
        {
            "id": "bc-live",
            "status": "ACTIVE",
            "latestRunId": "run-live",
            "repos": [{"url": GCS_REPO}],
        },
    ]
    with OccupancyListRunsAPI(list_items=items, runs_http=500) as api:
        env = _script_env(tmp_path, api.base)
        listed = _run_occupancy(env)
    blob = listed.stdout + listed.stderr
    assert listed.returncode != 0
    assert "CLOUD_OCCUPANCY_ERR" in blob
    assert "CLOUD_OCCUPANCY running=" not in listed.stdout
    assert FAKE_KEY not in blob


def test_source_contract_listruns_not_132_concurrency_or_142_only() -> None:
    occupancy_py = OCCUPANCY_PY.read_text(encoding="utf-8")
    occupancy_ts = OCCUPANCY_TS.read_text(encoding="utf-8")
    occupancy_sh = OCCUPANCY_SH.read_text(encoding="utf-8")
    latest_py = LATEST_PY.read_text(encoding="utf-8")
    footer = FOOTER.read_text(encoding="utf-8")
    cloud = CLOUD_DOC.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    blob = "\n".join([occupancy_py, occupancy_ts, occupancy_sh, footer, cloud, readme])
    low = blob.lower()
    assert "/v1/agents/{agent_id}/runs" in occupancy_py or '/runs"' in occupancy_py
    assert "listRuns" in occupancy_ts
    assert "pick_latest_run" in occupancy_py or "unwrap_runs" in occupancy_py
    assert "createdAt" in latest_py or "created_at" in latest_py
    assert "CREATING" in occupancy_py and "RUNNING" in occupancy_py
    assert "palemon=" in occupancy_py or "palemon" in occupancy_py.lower()
    assert "gcs=" in occupancy_py or "gcs" in occupancy_ts.lower()
    assert "palemon" in occupancy_ts.lower()
    assert "grok-cloud-studio" in occupancy_py or "grok-cloud-studio" in occupancy_ts
    assert "mapWithConcurrency" not in occupancy_ts
    assert not (CLOUD / "sdk" / "occupancy_lib.ts").is_file()
    assert "nextCursor" in occupancy_py or "list_catalog" in occupancy_py
    assert "occupancy-count.sh" in footer
    assert "listRuns" in cloud or "listRuns" in readme or "list runs" in low
    assert "floor" in low or "cap=8" in blob or "GCS_CLOUD_MIN_RUNNING" in blob
    assert "132" in occupancy_py or "HOLD" in occupancy_py or "concurrency" in occupancy_py.lower()
    banned = "Bot " + "CloudAgent"
    assert banned in blob or "never grok bot" in low
    assert "atebites-hub/" + GAME not in occupancy_py
    assert "atebites-hub/" + GAME not in occupancy_ts
