"""Paginated occupancy catalog: Agent.list / GET /v1/agents beyond limit=100.

Hive dump was 439 Extra Highs. A single page of 100 undercounts occupancy.
count-running / occupancy-count fail-closed if a catalog page errors —
never fake running=0 from a partial list.

Distinct from leftover occupancy GCS #132 (listRuns concurrency/timeout).
Do not rebase that PR. Palemon Linear is Living Sky (LIV). Never Bot CloudAgent.
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

import pytest

REPO = Path(__file__).resolve().parents[1]
CLOUD = REPO / "scripts" / "cloud"
CATALOG_PY = CLOUD / "list_catalog.py"
OCCUPANCY_PY = CLOUD / "occupancy_count.py"
OCCUPANCY_SH = CLOUD / "occupancy-count.sh"
LIST_SH = CLOUD / "list.sh"
LIST_ROWS_PY = CLOUD / "list_rows.py"
LIST_TS = CLOUD / "sdk" / "list.ts"
LIST_CATALOG_TS = CLOUD / "sdk" / "list_catalog.ts"
OCCUPANCY_TS = CLOUD / "sdk" / "occupancy.ts"
RUN_SH = CLOUD / "sdk" / "run.sh"
FOOTER = REPO / "scripts" / "directors" / "common_footer.txt"
CLOUD_DOC = REPO / "docs" / "CLOUD.md"
README = CLOUD / "README.md"
FAKE_KEY = "test-cursor-api-key-paginated-catalog"

HIVE_DUMP = 439
API_PAGE_MAX = 100


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
    }
    env.update(extra)
    return env


def _run_occupancy(
    env: dict[str, str],
    args: list[str] | None = None,
    *,
    timeout: float = 12,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(OCCUPANCY_SH), *(args or [])],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
    )


def _run_list(
    env: dict[str, str],
    args: list[str] | None = None,
    *,
    timeout: float = 20,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(LIST_SH), *(args or [])],
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


def _hive_items(n: int = HIVE_DUMP) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for i in range(n):
        run_id = f"run-{i}"
        items.append(
            {
                "id": f"bc-{i:04d}",
                "name": f"grunt-{i}",
                "status": "ACTIVE",
                "url": f"https://cursor.com/agents/bc-{i:04d}",
                "latestRunId": run_id,
            }
        )
    return items


@dataclass
class PaginatedListAPI:
    """REST stand-in for paginated GET /v1/agents (cursor + limit, max 100)."""

    list_items: list[dict[str, Any]] = field(default_factory=list)
    run_status_by_id: dict[str, str] = field(default_factory=dict)
    page_http: dict[str, int] = field(default_factory=dict)
    default_list_http: int = 200
    runs_http: int = 200
    page_size: int = API_PAGE_MAX
    gets: list[str] = field(default_factory=list)
    list_queries: list[dict[str, list[str]]] = field(default_factory=list)
    auth_users: list[str] = field(default_factory=list)
    _httpd: ThreadingHTTPServer | None = None
    _thread: threading.Thread | None = None
    base: str = ""

    def __enter__(self) -> "PaginatedListAPI":
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
                api.gets.append(self.path)
                parts = [p for p in parsed.path.split("/") if p]
                if parts == ["v1", "agents"]:
                    qs = parse_qs(parsed.query, keep_blank_values=True)
                    api.list_queries.append(qs)
                    cursor = (qs.get("cursor") or [""])[0]
                    page_code = api.page_http.get(cursor, api.default_list_http)
                    if page_code != 200:
                        self._send(page_code, {"error": "list_page_failed"})
                        return
                    try:
                        limit = int((qs.get("limit") or [str(api.page_size)])[0])
                    except ValueError:
                        limit = api.page_size
                    limit = min(max(limit, 1), API_PAGE_MAX)
                    start = 0
                    if cursor:
                        try:
                            start = int(cursor)
                        except ValueError:
                            self._send(400, {"error": "bad_cursor"})
                            return
                    chunk = api.list_items[start : start + limit]
                    payload: dict[str, Any] = {"items": chunk}
                    nxt = start + limit
                    if nxt < len(api.list_items):
                        payload["nextCursor"] = str(nxt)
                    self._send(200, payload)
                    return
                if len(parts) == 5 and parts[:2] == ["v1", "agents"] and parts[3] == "runs":
                    if api.runs_http != 200:
                        self._send(api.runs_http, {"error": "run_failed"})
                        return
                    run_id = parts[4]
                    status = api.run_status_by_id.get(run_id, "FINISHED")
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


def test_catalog_paginates_beyond_limit_100_hive_dump_scale() -> None:
    """GET /v1/agents max page is 100; hive dump 439 needs five pages."""
    cat = _load(CATALOG_PY, "gcs_list_catalog")
    assert cat.API_PAGE_MAX == API_PAGE_MAX
    requested: list[tuple[str | None, int]] = []

    def fetch_page(cursor: str | None, limit: int) -> dict[str, Any]:
        requested.append((cursor, limit))
        start = 0 if not cursor else int(cursor)
        end = min(start + limit, HIVE_DUMP)
        payload: dict[str, Any] = {
            "items": [{"id": f"bc-{i:04d}", "status": "ACTIVE"} for i in range(start, end)]
        }
        if end < HIVE_DUMP:
            payload["nextCursor"] = str(end)
        return payload

    catalog = cat.fetch_catalog(fetch_page, page_size=API_PAGE_MAX)
    assert catalog.listed == HIVE_DUMP
    assert len(catalog.items) == HIVE_DUMP
    assert catalog.pages == 5
    assert requested[0] == (None, API_PAGE_MAX)
    assert all(limit == API_PAGE_MAX for _cursor, limit in requested)
    assert len(requested) == 5
    assert catalog.items[0]["id"] == "bc-0000"
    assert catalog.items[-1]["id"] == "bc-0438"


def test_catalog_page_error_fail_closed_does_not_return_partial() -> None:
    cat = _load(CATALOG_PY, "gcs_list_catalog")

    def fetch_page(cursor: str | None, limit: int) -> dict[str, Any]:
        if cursor:
            raise cat.CatalogError("http=500", "page")
        return {
            "items": [{"id": f"bc-{i}", "status": "ACTIVE"} for i in range(limit)],
            "nextCursor": "100",
        }

    with pytest.raises(cat.CatalogError) as caught:
        cat.fetch_catalog(fetch_page, page_size=API_PAGE_MAX)
    assert caught.value.reason == "page"


def test_omitted_empty_or_null_next_cursor_stops_pagination() -> None:
    cat = _load(CATALOG_PY, "gcs_list_catalog")
    calls = {"n": 0}

    def fetch_page(cursor: str | None, limit: int) -> dict[str, Any]:
        calls["n"] += 1
        if calls["n"] == 1:
            return {"items": [{"id": "bc-a"}], "nextCursor": None}
        raise AssertionError("must not request another page")

    catalog = cat.fetch_catalog(fetch_page, page_size=API_PAGE_MAX)
    assert catalog.listed == 1
    assert catalog.pages == 1

    calls["n"] = 0

    def fetch_empty_cursor(cursor: str | None, limit: int) -> dict[str, Any]:
        calls["n"] += 1
        if calls["n"] == 1:
            return {"items": [{"id": "bc-b"}], "nextCursor": "  "}
        raise AssertionError("blank nextCursor is end of catalog")

    catalog = cat.fetch_catalog(fetch_empty_cursor, page_size=API_PAGE_MAX)
    assert catalog.listed == 1


def test_incomplete_catalog_hits_max_pages_fail_closed() -> None:
    cat = _load(CATALOG_PY, "gcs_list_catalog")

    def fetch_page(cursor: str | None, limit: int) -> dict[str, Any]:
        start = 0 if not cursor else int(cursor)
        return {
            "items": [{"id": f"bc-{start}"}],
            "nextCursor": str(start + 1),
        }

    with pytest.raises(cat.CatalogError) as caught:
        cat.fetch_catalog(fetch_page, page_size=1, max_pages=3)
    assert caught.value.reason == "page"


def test_occupancy_counts_running_on_later_catalog_pages() -> None:
    occ = _load(OCCUPANCY_PY, "gcs_occupancy_count")
    cat = _load(CATALOG_PY, "gcs_list_catalog")
    items = [
        {"id": "bc-0", "status": "ACTIVE", "latestRunId": "run-0"},
        {"id": "bc-1", "status": "ACTIVE", "latestRunId": "run-1"},
        {"id": "bc-live", "status": "ACTIVE", "latestRunId": "run-live"},
    ]
    runs = {"run-0": "FINISHED", "run-1": "FINISHED", "run-live": "RUNNING"}

    def fetch_page(cursor: str | None, limit: int) -> dict[str, Any]:
        start = 0 if not cursor else int(cursor)
        chunk = items[start : start + 1]
        payload: dict[str, Any] = {"items": chunk}
        if start + 1 < len(items):
            payload["nextCursor"] = str(start + 1)
        return payload

    catalog = cat.fetch_catalog(fetch_page, page_size=1)
    summary = occ.occupancy_from_catalog(
        catalog,
        lambda agent_id, run_id: runs.get(run_id, "none"),
    )
    assert catalog.pages == 3
    assert catalog.listed == 3
    assert summary.running == 1
    assert summary.creating == 0
    assert summary.leftover_active == 2
    assert summary.listed == 3
    assert summary.pages == 3
    line = occ.format_occupancy_line(summary)
    assert line.startswith("CLOUD_OCCUPANCY ")
    assert "running=1" in line
    assert "listed=3" in line
    assert "pages=3" in line


def test_occupancy_page_error_never_fakes_running_zero() -> None:
    occ = _load(OCCUPANCY_PY, "gcs_occupancy_count")
    cat = _load(CATALOG_PY, "gcs_list_catalog")

    def fetch_page(cursor: str | None, limit: int) -> dict[str, Any]:
        if cursor:
            raise cat.CatalogError("http=502", "page")
        return {"items": [{"id": "bc-only", "status": "ACTIVE"}], "nextCursor": "1"}

    with pytest.raises(cat.CatalogError) as caught:
        catalog = cat.fetch_catalog(fetch_page, page_size=1)
        occ.occupancy_from_catalog(catalog, lambda _aid, _rid: "RUNNING")
    assert caught.value.reason == "page"
    assert occ.format_occupancy_err("page") == "CLOUD_OCCUPANCY_ERR reason=page"


def test_empty_catalog_is_zero_occupancy_not_err() -> None:
    occ = _load(OCCUPANCY_PY, "gcs_occupancy_count")
    cat = _load(CATALOG_PY, "gcs_list_catalog")
    catalog = cat.fetch_catalog(lambda _c, _n: {"items": []}, page_size=API_PAGE_MAX)
    summary = occ.occupancy_from_catalog(catalog, lambda _aid, _rid: "none")
    assert summary.running == 0
    assert summary.listed == 0
    assert summary.pages == 1
    assert occ.format_occupancy_line(summary) == (
        "CLOUD_OCCUPANCY running=0 leftover_active=0 creating=0 listed=0 pages=1"
    )


def test_count_running_skips_bot_cloudagent() -> None:
    occ = _load(OCCUPANCY_PY, "gcs_occupancy_count")
    cat = _load(CATALOG_PY, "gcs_list_catalog")
    bot = "bc-bot-orchestrator"
    items = [
        {"id": bot, "status": "ACTIVE", "latestRunId": "run-bot"},
        {"id": "bc-live", "status": "ACTIVE", "latestRunId": "run-live"},
    ]
    catalog = cat.CatalogResult(items=items, pages=1)
    runs = {"run-bot": "RUNNING", "run-live": "RUNNING"}
    summary = occ.occupancy_from_catalog(
        catalog,
        lambda agent_id, run_id: runs.get(run_id, "none"),
        bot_id=bot,
    )
    assert summary.running == 1
    assert summary.listed == 1


def test_cli_paginates_hive_dump_and_counts_running_on_last_page(tmp_path: Path) -> None:
    items = _hive_items(HIVE_DUMP)
    runs = {f"run-{i}": "FINISHED" for i in range(HIVE_DUMP)}
    runs["run-438"] = "RUNNING"
    runs["run-0"] = "CREATING"
    with PaginatedListAPI(list_items=items, run_status_by_id=runs) as api:
        env = _script_env(tmp_path, api.base)
        listed = _run_occupancy(env, timeout=60)
    assert listed.returncode == 0, listed.stdout + listed.stderr
    line = listed.stdout.strip().splitlines()[-1]
    assert line.startswith("CLOUD_OCCUPANCY ")
    assert "running=1" in line
    assert "creating=1" in line
    assert "listed=439" in line
    assert "pages=5" in line
    list_gets = [q for q in api.list_queries]
    assert len(list_gets) == 5, api.gets
    assert list_gets[0].get("limit") == [str(API_PAGE_MAX)]
    assert "cursor" not in list_gets[0] or list_gets[0].get("cursor") == [""]
    assert list_gets[1].get("cursor") == ["100"]
    assert list_gets[4].get("cursor") == ["400"]
    blob = listed.stdout + listed.stderr
    assert FAKE_KEY not in blob
    assert all(user == FAKE_KEY for user in api.auth_users)


def test_cli_page_error_fail_closed_never_prints_running_zero(tmp_path: Path) -> None:
    items = _hive_items(150)
    with PaginatedListAPI(
        list_items=items,
        run_status_by_id={f"run-{i}": "FINISHED" for i in range(150)},
        page_http={"100": 500},
    ) as api:
        env = _script_env(tmp_path, api.base)
        listed = _run_occupancy(env)
    assert listed.returncode != 0
    blob = listed.stdout + listed.stderr
    assert "CLOUD_OCCUPANCY_ERR" in blob
    assert "reason=page" in blob
    assert "CLOUD_OCCUPANCY running=" not in listed.stdout
    assert FAKE_KEY not in blob
    assert len(api.list_queries) >= 2


def test_cli_first_page_http_err_fail_closed(tmp_path: Path) -> None:
    with PaginatedListAPI(default_list_http=500) as api:
        env = _script_env(tmp_path, api.base)
        listed = _run_occupancy(env)
    assert listed.returncode != 0
    blob = listed.stdout + listed.stderr
    assert "CLOUD_OCCUPANCY_ERR" in blob
    assert "CLOUD_OCCUPANCY running=" not in listed.stdout
    assert FAKE_KEY not in blob


def test_fetch_catalog_stops_at_max_items_without_fail_closed() -> None:
    """list.sh --limit N must stop after N rows; occupancy still walks the hive."""
    cat = _load(CATALOG_PY, "gcs_list_catalog")
    requested: list[tuple[str | None, int]] = []

    def fetch_page(cursor: str | None, limit: int) -> dict[str, Any]:
        requested.append((cursor, limit))
        start = 0 if not cursor else int(cursor)
        end = min(start + limit, 250)
        payload: dict[str, Any] = {
            "items": [{"id": f"bc-{i:04d}", "status": "ACTIVE"} for i in range(start, end)]
        }
        if end < 250:
            payload["nextCursor"] = str(end)
        return payload

    catalog = cat.fetch_catalog(fetch_page, page_size=API_PAGE_MAX, max_items=150)
    assert catalog.listed == 150
    assert catalog.pages == 2
    assert len(requested) == 2
    assert catalog.items[-1]["id"] == "bc-0149"


def test_list_sh_pages_next_cursor_beyond_100_and_sees_running(
    tmp_path: Path,
) -> None:
    """REST list.sh must walk nextCursor so Directors can count RUNNING past 100.

    Occupancy-count already paginates. SDK list.ts paginates when --limit exceeds
    one page. REST list.sh still did a single GET /v1/agents?limit=N (API caps at
    100), so a live worker on page 3 looked like running=0.
    """
    n = 201
    items = _hive_items(n)
    runs = {f"run-{i}": "FINISHED" for i in range(n)}
    runs["run-200"] = "RUNNING"
    with PaginatedListAPI(list_items=items, run_status_by_id=runs) as api:
        env = _script_env(tmp_path, api.base)
        listed = _run_list(env, ["--limit", "201"], timeout=45)
    assert listed.returncode == 0, listed.stdout + listed.stderr
    rows = [line for line in listed.stdout.splitlines() if line.startswith("id=")]
    assert len(rows) == 201, listed.stdout
    live = [line for line in rows if "runStatus=RUNNING" in line]
    assert len(live) == 1, listed.stdout
    assert "id=bc-0200" in live[0]
    assert "runStatus=FINISHED" in rows[0]
    assert len(api.list_queries) == 3, api.gets
    assert api.list_queries[0].get("limit") == [str(API_PAGE_MAX)]
    assert "cursor" not in api.list_queries[0] or api.list_queries[0].get("cursor") == [""]
    assert api.list_queries[1].get("cursor") == ["100"]
    assert api.list_queries[2].get("cursor") == ["200"]
    blob = listed.stdout + listed.stderr
    assert FAKE_KEY not in blob
    assert all(user == FAKE_KEY for user in api.auth_users)


def test_list_sh_page_error_fail_closed_does_not_print_partial(tmp_path: Path) -> None:
    """A later catalog page error must not look like a complete list (never fake 0 RUNNING)."""
    items = _hive_items(150)
    runs = {f"run-{i}": "FINISHED" for i in range(150)}
    runs["run-120"] = "RUNNING"
    with PaginatedListAPI(
        list_items=items,
        run_status_by_id=runs,
        page_http={"100": 500},
    ) as api:
        env = _script_env(tmp_path, api.base)
        listed = _run_list(env, ["--limit", "150"])
    assert listed.returncode != 0
    blob = listed.stdout + listed.stderr
    assert "error:" in blob.lower() or "CLOUD_LIST" in blob
    assert "id=bc-0120" not in listed.stdout
    assert "runStatus=RUNNING" not in listed.stdout
    assert FAKE_KEY not in blob
    assert len(api.list_queries) >= 2


def test_sdk_and_docs_paginate_agent_list_not_cap_at_100() -> None:
    """Occupancy catalog follows nextCursor. Do not twin GCS #132 occupancy_lib."""
    list_catalog_ts = LIST_CATALOG_TS.read_text(encoding="utf-8")
    occupancy_ts = OCCUPANCY_TS.read_text(encoding="utf-8")
    occupancy_py = OCCUPANCY_PY.read_text(encoding="utf-8")
    catalog_py = CATALOG_PY.read_text(encoding="utf-8")
    run_sh = RUN_SH.read_text(encoding="utf-8")
    list_ts = LIST_TS.read_text(encoding="utf-8")
    list_sh = LIST_SH.read_text(encoding="utf-8")
    list_rows = LIST_ROWS_PY.read_text(encoding="utf-8")
    assert "nextCursor" in list_catalog_ts
    assert "Agent.list" in list_catalog_ts
    assert "cursor" in list_catalog_ts
    assert "listAllCloudAgents" in occupancy_ts or "listCatalog" in occupancy_ts
    assert "nextCursor" in catalog_py
    assert "API_PAGE_MAX" in catalog_py
    assert "100" in catalog_py
    assert "occupancy" in run_sh
    assert "CLOUD_OCCUPANCY" in occupancy_ts
    assert "reason=page" in occupancy_py or "reason" in occupancy_py
    # Distinct from leftover occupancy #132: no listRuns concurrency helper.
    assert not (CLOUD / "sdk" / "occupancy_lib.ts").is_file()
    assert "mapWithConcurrency" not in occupancy_ts
    assert "Promise.all(\n      items.map" not in list_ts or "listAllCloudAgents" in list_ts
    footer = FOOTER.read_text(encoding="utf-8")
    cloud = CLOUD_DOC.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    assert "occupancy-count.sh" in footer
    assert "occupancy-count.sh" in cloud
    assert "occupancy-count.sh" in readme
    assert "nextCursor" in cloud or "paginat" in cloud.lower()
    assert "100" in cloud or "439" in cloud
    assert "fail-closed" in cloud.lower() or "fail closed" in cloud.lower()
    assert "Living Sky" in cloud or "LIV" in cloud
    assert "Black Swan" not in footer
    # REST list.sh remaining slice: page nextCursor (not a single GET ?limit=).
    assert "list_catalog" in list_rows
    assert "max_items" in catalog_py
    assert 'GET "/v1/agents?limit=${limit}"' not in list_sh
    assert "--limit" in list_sh
    banned = "Bot " + "CloudAgent"
    for path in (
        OCCUPANCY_PY,
        CATALOG_PY,
        OCCUPANCY_SH,
        OCCUPANCY_TS,
        LIST_CATALOG_TS,
        LIST_SH,
        LIST_ROWS_PY,
    ):
        text = path.read_text(encoding="utf-8")
        assert banned not in text, path
