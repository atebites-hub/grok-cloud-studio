"""Occupancy counts: Agent.list + listRuns with bounded concurrency.

Capacity beats must not hang on leftover ACTIVE shells. Existence ACTIVE/IDLE
is not liveness. Fail-closed on listRuns ERR/timeout (do not report running=0).
Do not remint LIV-67 list.sh --running printers.

Palemon Linear is Living Sky (LIV). Never Bot CloudAgent. Never print keys.
"""
from __future__ import annotations

import base64
import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType
from typing import Any, Callable
from urllib.parse import urlparse

import pytest

REPO = Path(__file__).resolve().parents[1]
CLOUD = REPO / "scripts" / "cloud"
OCCUPANCY_PY = CLOUD / "occupancy_count.py"
OCCUPANCY_SH = CLOUD / "occupancy-count.sh"
LIST_SH = CLOUD / "list.sh"
LIST_TS = CLOUD / "sdk" / "list.ts"
OCCUPANCY_TS = CLOUD / "sdk" / "occupancy.ts"
OCCUPANCY_LIB_TS = CLOUD / "sdk" / "occupancy_lib.ts"
RUN_SH = CLOUD / "sdk" / "run.sh"
FOOTER = REPO / "scripts" / "directors" / "common_footer.txt"
CLOUD_DOC = REPO / "docs" / "CLOUD.md"
README = CLOUD / "README.md"
FAKE_KEY = "test-cursor-api-key-occupancy"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gcs_occupancy_count", OCCUPANCY_PY)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gcs_occupancy_count"] = mod
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


def _run(
    args: list[str],
    env: dict[str, str],
    *,
    timeout: float = 8,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(OCCUPANCY_SH), *args],
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


@dataclass
class MockOccupancyAPI:
    """REST stand-in for Agent.list + Agent.listRuns (collection, not getRun)."""

    list_items: list[dict[str, Any]] = field(default_factory=list)
    runs_by_agent: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    list_http: int = 200
    runs_http: int = 200
    delay_sec: float = 0.0
    hang_ids: set[str] = field(default_factory=set)
    gets: list[str] = field(default_factory=list)
    auth_users: list[str] = field(default_factory=list)
    inflight_runs: int = 0
    peak_runs: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _httpd: ThreadingHTTPServer | None = None
    _thread: threading.Thread | None = None
    base: str = ""

    def __enter__(self) -> "MockOccupancyAPI":
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
                with api._lock:
                    api.gets.append(parsed.path)
                parts = [p for p in parsed.path.split("/") if p]
                if parts == ["v1", "agents"]:
                    if api.list_http != 200:
                        self._send(api.list_http, {"error": "list_failed"})
                        return
                    self._send(200, {"items": api.list_items})
                    return
                if len(parts) == 4 and parts[:2] == ["v1", "agents"] and parts[3] == "runs":
                    agent_id = parts[2]
                    with api._lock:
                        api.inflight_runs += 1
                        api.peak_runs = max(api.peak_runs, api.inflight_runs)
                    try:
                        if agent_id in api.hang_ids:
                            time.sleep(30)
                        elif api.delay_sec > 0:
                            time.sleep(api.delay_sec)
                        if api.runs_http != 200:
                            self._send(api.runs_http, {"error": "runs_failed"})
                            return
                        items = api.runs_by_agent.get(agent_id, [])
                        self._send(200, {"items": items})
                    finally:
                        with api._lock:
                            api.inflight_runs -= 1
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


def _fetch_map(
    mapping: dict[str, list[dict[str, Any]]],
) -> Callable[[str], list[dict[str, Any]]]:
    def fetch(agent_id: str) -> list[dict[str, Any]]:
        if agent_id not in mapping:
            raise KeyError(agent_id)
        return mapping[agent_id]

    return fetch


def test_active_idle_existence_is_not_liveness() -> None:
    occ = _load()
    agents = [
        {"id": "bc-leftover", "status": "ACTIVE", "name": "done-grunt"},
        {"id": "bc-idle", "status": "IDLE", "name": "idle-shell"},
        {"id": "bc-live", "status": "ACTIVE", "name": "live-grunt"},
        {"id": "bc-boot", "status": "ACTIVE", "name": "booting"},
        {"id": "bc-arch", "status": "ARCHIVED", "name": "old"},
    ]
    runs = {
        "bc-leftover": [{"id": "run-done", "status": "FINISHED", "createdAt": 20}],
        "bc-idle": [{"id": "run-idle", "status": "FINISHED", "createdAt": 10}],
        "bc-live": [{"id": "run-live", "status": "RUNNING", "createdAt": 30}],
        "bc-boot": [{"id": "run-boot", "status": "CREATING", "createdAt": 5}],
        "bc-arch": [{"id": "run-arch", "status": "FINISHED", "createdAt": 1}],
    }
    summary = occ.occupancy_from_agents(agents, _fetch_map(runs), concurrency=8, timeout_sec=2, deadline_sec=5)
    assert summary.running == 1
    assert summary.creating == 1
    assert summary.leftover_active == 2
    assert summary.listed == 5
    line = occ.format_occupancy_line(summary)
    assert line.startswith("CLOUD_OCCUPANCY ")
    assert "running=1" in line
    assert "leftover_active=2" in line
    assert "creating=1" in line
    assert "listed=5" in line


def test_pick_latest_run_by_created_at_not_list_order() -> None:
    occ = _load()
    items = [
        {"id": "run-old", "status": "FINISHED", "createdAt": 1},
        {"id": "run-new", "status": "RUNNING", "createdAt": 9},
        {"id": "run-mid", "status": "ERROR", "createdAt": 4},
    ]
    latest = occ.pick_latest_run(items)
    assert latest is not None
    assert latest["id"] == "run-new"
    assert occ.normalize_run_status(latest.get("status")) == "RUNNING"


def test_occupancy_caps_inflight_list_runs() -> None:
    occ = _load()
    inflight = 0
    peak = 0
    lock = threading.Lock()

    def fetch(_agent_id: str) -> list[dict[str, Any]]:
        nonlocal inflight, peak
        with lock:
            inflight += 1
            peak = max(peak, inflight)
        time.sleep(0.06)
        with lock:
            inflight -= 1
        return [{"id": "run-x", "status": "FINISHED", "createdAt": 1}]

    agents = [{"id": f"bc-{i}", "status": "ACTIVE", "name": f"n{i}"} for i in range(16)]
    summary = occ.occupancy_from_agents(
        agents,
        fetch,
        concurrency=4,
        timeout_sec=2,
        deadline_sec=8,
    )
    assert peak <= 4
    assert peak >= 2
    assert summary.running == 0
    assert summary.leftover_active == 16
    assert occ.DEFAULT_CONCURRENCY == 8


def test_occupancy_timeout_fail_closed_does_not_hang() -> None:
    occ = _load()

    def fetch(_agent_id: str) -> list[dict[str, Any]]:
        time.sleep(8)
        return [{"id": "run-slow", "status": "RUNNING", "createdAt": 1}]

    t0 = time.monotonic()
    with pytest.raises(occ.OccupancyError) as caught:
        occ.occupancy_from_agents(
            [{"id": "bc-slow", "status": "ACTIVE", "name": "slow"}],
            fetch,
            concurrency=1,
            timeout_sec=0.2,
            deadline_sec=1,
        )
    elapsed = time.monotonic() - t0
    assert elapsed < 2.0
    assert caught.value.reason in {"timeout", "deadline"}


def test_occupancy_err_is_fail_closed_not_running_zero() -> None:
    occ = _load()

    def fetch(_agent_id: str) -> list[dict[str, Any]]:
        raise RuntimeError("http=500")

    with pytest.raises(occ.OccupancyError) as caught:
        occ.occupancy_from_agents(
            [{"id": "bc-err", "status": "ACTIVE", "name": "broken"}],
            fetch,
            concurrency=1,
            timeout_sec=1,
            deadline_sec=2,
        )
    assert caught.value.reason == "err"
    # Fail-closed: callers must not treat this as an empty floor.


def test_empty_fleet_is_zero_occupancy_not_err() -> None:
    occ = _load()
    summary = occ.occupancy_from_agents([], lambda _aid: [], concurrency=8, timeout_sec=1, deadline_sec=2)
    assert summary.running == 0
    assert summary.leftover_active == 0
    assert summary.creating == 0
    assert summary.listed == 0
    assert occ.format_occupancy_line(summary) == (
        "CLOUD_OCCUPANCY running=0 leftover_active=0 creating=0 listed=0"
    )


def test_bot_cloudagent_is_not_extra_high_occupancy() -> None:
    occ = _load()
    bot = "bc-bot-orchestrator"
    agents = [
        {"id": bot, "status": "ACTIVE", "name": "donald"},
        {"id": "bc-live", "status": "ACTIVE", "name": "grunt"},
    ]
    runs = {
        bot: [{"id": "run-bot", "status": "RUNNING", "createdAt": 2}],
        "bc-live": [{"id": "run-live", "status": "RUNNING", "createdAt": 2}],
    }
    summary = occ.occupancy_from_agents(
        agents,
        _fetch_map(runs),
        concurrency=2,
        timeout_sec=1,
        deadline_sec=2,
        bot_id=bot,
    )
    assert summary.running == 1
    assert summary.listed == 1


def test_cli_counts_running_via_list_runs_collection(tmp_path: Path) -> None:
    items = [
        {"id": "bc-leftover", "status": "ACTIVE", "name": "done-grunt"},
        {"id": "bc-idle", "status": "IDLE", "name": "idle-shell"},
        {"id": "bc-live", "status": "ACTIVE", "name": "live-grunt"},
        {"id": "bc-boot", "status": "ACTIVE", "name": "booting"},
    ]
    runs = {
        "bc-leftover": [{"id": "run-done", "status": "FINISHED", "createdAt": 2}],
        "bc-idle": [{"id": "run-idle", "status": "FINISHED", "createdAt": 1}],
        "bc-live": [{"id": "run-live", "status": "RUNNING", "createdAt": 9}],
        "bc-boot": [{"id": "run-boot", "status": "CREATING", "createdAt": 3}],
    }
    with MockOccupancyAPI(list_items=items, runs_by_agent=runs) as api:
        env = _script_env(tmp_path, api.base)
        listed = _run([], env)
    assert listed.returncode == 0, listed.stdout + listed.stderr
    line = listed.stdout.strip().splitlines()[-1]
    assert line.startswith("CLOUD_OCCUPANCY ")
    assert "running=1" in line
    assert "leftover_active=2" in line
    assert "creating=1" in line
    assert "listed=4" in line
    collection = [p for p in api.gets if p.endswith("/runs")]
    specific = [p for p in api.gets if "/runs/" in p]
    assert len(collection) == 4, api.gets
    assert specific == [], api.gets
    blob = listed.stdout + listed.stderr
    assert FAKE_KEY not in blob
    assert all(user == FAKE_KEY for user in api.auth_users)


def test_cli_list_runs_timeout_fail_closed_does_not_hang(tmp_path: Path) -> None:
    items = [{"id": "bc-hang", "status": "ACTIVE", "name": "hung"}]
    runs = {"bc-hang": [{"id": "run-hang", "status": "RUNNING", "createdAt": 1}]}
    with MockOccupancyAPI(list_items=items, runs_by_agent=runs, hang_ids={"bc-hang"}) as api:
        env = _script_env(
            tmp_path,
            api.base,
            CLOUD_LIST_RUNS_TIMEOUT_SEC="0.3",
            CLOUD_OCCUPANCY_DEADLINE_SEC="1",
            CLOUD_OCCUPANCY_CONCURRENCY="1",
        )
        t0 = time.monotonic()
        listed = _run([], env, timeout=5)
        elapsed = time.monotonic() - t0
    assert elapsed < 3.0
    assert listed.returncode != 0
    blob = listed.stdout + listed.stderr
    assert "CLOUD_OCCUPANCY_ERR" in blob
    assert "reason=timeout" in blob or "reason=deadline" in blob
    assert "CLOUD_OCCUPANCY running=" not in listed.stdout
    assert any(p.endswith("/runs") for p in api.gets), api.gets
    assert FAKE_KEY not in blob


def test_cli_list_runs_http_err_fail_closed(tmp_path: Path) -> None:
    items = [{"id": "bc-err", "status": "ACTIVE", "name": "broken"}]
    with MockOccupancyAPI(list_items=items, runs_http=500) as api:
        env = _script_env(tmp_path, api.base)
        listed = _run([], env)
    assert listed.returncode != 0
    blob = listed.stdout + listed.stderr
    assert "CLOUD_OCCUPANCY_ERR" in blob
    assert "CLOUD_OCCUPANCY running=" not in listed.stdout
    assert "reason=err" in blob
    assert any(p.endswith("/runs") for p in api.gets), api.gets
    assert FAKE_KEY not in blob


def test_cli_list_http_err_fail_closed(tmp_path: Path) -> None:
    with MockOccupancyAPI(list_http=500) as api:
        env = _script_env(tmp_path, api.base)
        listed = _run([], env)
    assert listed.returncode != 0
    blob = listed.stdout + listed.stderr
    assert "CLOUD_OCCUPANCY_ERR" in blob
    assert "CLOUD_OCCUPANCY running=" not in listed.stdout
    assert "/v1/agents" in "".join(api.gets)
    assert FAKE_KEY not in blob


def test_cli_bounded_concurrency_on_list_runs(tmp_path: Path) -> None:
    items = [{"id": f"bc-{i}", "status": "ACTIVE", "name": f"n{i}"} for i in range(12)]
    runs = {f"bc-{i}": [{"id": f"run-{i}", "status": "FINISHED", "createdAt": 1}] for i in range(12)}
    with MockOccupancyAPI(list_items=items, runs_by_agent=runs, delay_sec=0.08) as api:
        env = _script_env(tmp_path, api.base, CLOUD_OCCUPANCY_CONCURRENCY="3")
        listed = _run([], env, timeout=8)
    assert listed.returncode == 0, listed.stdout + listed.stderr
    assert api.peak_runs <= 3
    assert api.peak_runs >= 2
    assert "running=0" in listed.stdout
    assert "leftover_active=12" in listed.stdout


def test_does_not_remint_list_running_printer() -> None:
    """Occupancy helper is the count path. Do not clone list.sh --running (#78)."""
    list_sh = LIST_SH.read_text(encoding="utf-8")
    list_ts = LIST_TS.read_text(encoding="utf-8")
    occ_sh = OCCUPANCY_SH.read_text(encoding="utf-8")
    assert "--running" not in list_sh
    assert "--running" not in list_ts
    assert "occupancy" in occ_sh.lower() or "CLOUD_OCCUPANCY" in occ_sh


def test_sdk_list_uses_bounded_list_runs_timeout_fail_closed() -> None:
    list_ts = LIST_TS.read_text(encoding="utf-8")
    lib_ts = OCCUPANCY_LIB_TS.read_text(encoding="utf-8")
    occ_ts = OCCUPANCY_TS.read_text(encoding="utf-8")
    run_sh = RUN_SH.read_text(encoding="utf-8")
    assert "mapWithConcurrency" in list_ts
    assert "withTimeout" in list_ts
    assert "Promise.all(\n      items.map" not in list_ts
    assert "DEFAULT_CONCURRENCY = 8" in lib_ts
    assert "OccupancyError" in lib_ts
    assert "Agent.list" in occ_ts
    assert "listRuns" in occ_ts
    assert "CLOUD_OCCUPANCY" in occ_ts
    assert "occupancy" in run_sh
    # Fail-open catch that turned ERR into runStatus=none is the hang/undercount bug.
    assert "catch {\n    return { runStatus: \"none\"" not in list_ts


def test_docs_and_footer_point_capacity_beats_at_occupancy_count() -> None:
    footer = FOOTER.read_text(encoding="utf-8")
    cloud = CLOUD_DOC.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    assert "occupancy-count.sh" in footer
    assert "occupancy-count.sh" in cloud
    assert "occupancy-count.sh" in readme
    assert "ACTIVE/IDLE" in cloud or "ACTIVE/IDLE" in readme
    assert "fail-closed" in cloud.lower() or "fail-closed" in readme.lower()
    assert "Black Swan" not in footer
    assert "Living Sky" in cloud or "LIV" in cloud
