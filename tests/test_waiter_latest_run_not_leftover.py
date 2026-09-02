"""wait-notify / FLEET_DONE must GET latest runStatus.

Leftover FINISHED is not done while a newer run is CREATING or RUNNING.
Distinct from occupancy #132 and paginated-catalog beat1849.
Do not clone LIV-67 / LIV-41 / LIV-85. Never Bot CloudAgent.
"""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cloud"))

import latest_run as lr  # noqa: E402

FEATURE = ROOT / "tests" / "features" / "waiter_latest_run_not_leftover.feature"
WAIT_NOTIFY = ROOT / "scripts" / "cloud" / "sdk" / "wait-notify.ts"
LATEST_TS = ROOT / "scripts" / "cloud" / "sdk" / "latest_run.ts"
RUN_SH = ROOT / "scripts" / "cloud" / "sdk" / "run.sh"
LEDGER = ROOT / "scripts" / "cloud" / "fleet_ledger.py"
CLOUD_README = ROOT / "scripts" / "cloud" / "README.md"
ARCH = ROOT / "docs" / "ARCHITECTURE.md"
FAKE_KEY = "test-cursor-api-key-waiter-latest"
LIV67 = ROOT / "tests" / "test_liv67_leftover_finished_not_live.py"
OCCUPANCY = ROOT / "scripts" / "cloud" / "occupancy-count.sh"


def leftover_finished() -> dict[str, Any]:
    return {"id": "run-leftover", "status": "FINISHED", "createdAt": 1_000}


def newer_running() -> dict[str, Any]:
    return {"id": "run-new", "status": "RUNNING", "createdAt": 2_000}


def newer_creating() -> dict[str, Any]:
    return {"id": "run-new", "status": "CREATING", "createdAt": 2_000}


def test_feature_binds_waiter_latest_not_occupancy_or_catalog() -> None:
    text = FEATURE.read_text(encoding="utf-8")
    fold = " ".join(text.lower().split())
    assert FEATURE.is_file()
    assert "wait-notify" in fold
    assert "fleet_done" in fold or "fleet-done" in fold
    assert "latest" in fold
    assert "leftover" in fold
    assert "creating" in fold and "running" in fold
    assert "occupancy" in fold
    assert "#132" in text or "132" in text
    assert "paginated-catalog" in fold or "paginated catalog" in fold
    assert "liv-67" in fold or "do not clone liv-67" in fold
    assert WAIT_NOTIFY.is_file()
    assert not OCCUPANCY.is_file(), "this beat is not occupancy #132"


def test_does_not_clone_liv67_list_printers() -> None:
    helper = (ROOT / "scripts" / "cloud" / "latest_run.py").read_text(encoding="utf-8")
    wait = WAIT_NOTIFY.read_text(encoding="utf-8")
    assert "list.sh" not in helper
    assert "list-cloud-agents.sh" not in helper
    assert "list.sh" not in wait
    assert LIV67.is_file()
    assert Path(__file__).resolve() != LIV67.resolve()


def test_leftover_finished_plus_newer_running_is_not_fleet_done() -> None:
    leftover = leftover_finished()
    newer = newer_running()
    obs = lr.waiter_observe([leftover, newer], pinned=leftover)
    assert obs is not None
    assert obs["id"] == "run-new"
    assert lr.run_status(obs) == "RUNNING"
    assert lr.may_fleet_done(obs) is False


def test_leftover_finished_plus_newer_creating_is_not_fleet_done() -> None:
    leftover = leftover_finished()
    newer = newer_creating()
    obs = lr.waiter_observe([leftover, newer], pinned=leftover)
    assert obs is not None
    assert obs["id"] == "run-new"
    assert lr.run_status(obs) == "CREATING"
    assert lr.may_fleet_done(obs) is False


def test_pinned_leftover_is_ignored_when_collection_has_newer_running() -> None:
    leftover = leftover_finished()
    newer = newer_running()
    obs = lr.waiter_observe([newer], pinned=leftover)
    assert obs is not None
    assert obs["id"] == "run-new"
    assert lr.may_fleet_done(obs) is False


def test_pinned_creating_wins_when_collection_still_shows_leftover() -> None:
    leftover = leftover_finished()
    pinned = newer_creating()
    obs = lr.waiter_observe([leftover], pinned=pinned)
    assert obs is not None
    assert obs["id"] == "run-new"
    assert lr.run_status(obs) == "CREATING"
    assert lr.may_fleet_done(obs) is False


def test_only_leftover_finished_may_fleet_done() -> None:
    leftover = leftover_finished()
    obs = lr.waiter_observe([leftover], pinned=leftover)
    assert obs is not None
    assert obs["id"] == "run-leftover"
    assert lr.may_fleet_done(obs) is True


def test_newer_terminal_is_fleet_done_not_leftover_id() -> None:
    leftover = leftover_finished()
    newer = {"id": "run-new", "status": "FINISHED", "createdAt": 2_000}
    obs = lr.waiter_observe([leftover, newer], pinned=leftover)
    assert obs is not None
    assert obs["id"] == "run-new"
    assert lr.may_fleet_done(obs) is True


def test_unwrap_runs_collection_payload() -> None:
    leftover = leftover_finished()
    newer = newer_running()
    items = lr.unwrap_runs({"items": [leftover, newer]})
    assert [row["id"] for row in items] == ["run-leftover", "run-new"]


def test_wait_notify_gets_runs_collection_not_only_pinned_id() -> None:
    src = WAIT_NOTIFY.read_text(encoding="utf-8")
    ts = LATEST_TS.read_text(encoding="utf-8")
    blob = src + "\n" + ts
    assert re.search(r"/v1/agents/\$\{agentId\}/runs(?!/)", blob), blob
    assert "waiterObserve" in blob or "waiter_observe" in blob
    assert "listRuns" in src
    assert "occupancy-count" not in blob
    assert "CLOUD_OCCUPANCY" not in blob
    assert "paginated-catalog" not in src.lower()
    readme = CLOUD_README.read_text(encoding="utf-8")
    assert "latest" in readme.lower()
    assert "wait-notify" in readme
    arch = ARCH.read_text(encoding="utf-8")
    assert "wait-notify" in arch
    assert LEDGER.is_file()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@dataclass
class WaiterMockAPI:
    leftover_status: str = "FINISHED"
    latest_status: str = "RUNNING"
    agent_latest_run_id: str = "run-leftover"
    leftover_created: int = 1_000
    latest_created: int = 2_000
    gets: list[str] = field(default_factory=list)
    _httpd: ThreadingHTTPServer | None = None
    _thread: threading.Thread | None = None
    base: str = ""

    def __enter__(self) -> "WaiterMockAPI":
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

            def _run(self, run_id: str, status: str, created: int) -> dict[str, Any]:
                return {
                    "id": run_id,
                    "agentId": "bc-wait",
                    "status": status,
                    "createdAt": created,
                }

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                api.gets.append(parsed.path)
                parts = [p for p in parsed.path.split("/") if p]
                if parts == ["v1", "agents", "bc-wait"]:
                    self._send(
                        200,
                        {
                            "id": "bc-wait",
                            "name": "waiter-grunt",
                            "status": "ACTIVE",
                            "url": "https://cursor.com/agents/bc-wait",
                            "latestRunId": api.agent_latest_run_id,
                        },
                    )
                    return
                if parts == ["v1", "agents", "bc-wait", "runs"]:
                    self._send(
                        200,
                        {
                            "items": [
                                self._run(
                                    "run-leftover",
                                    api.leftover_status,
                                    api.leftover_created,
                                ),
                                self._run(
                                    "run-new",
                                    api.latest_status,
                                    api.latest_created,
                                ),
                            ]
                        },
                    )
                    return
                if parts == ["v1", "agents", "bc-wait", "runs", "run-leftover"]:
                    self._send(
                        200,
                        self._run(
                            "run-leftover",
                            api.leftover_status,
                            api.leftover_created,
                        ),
                    )
                    return
                if parts == ["v1", "agents", "bc-wait", "runs", "run-new"]:
                    self._send(
                        200,
                        self._run("run-new", api.latest_status, api.latest_created),
                    )
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


@dataclass
class MockA2AHub:
    pings: list[str] = field(default_factory=list)
    _httpd: ThreadingHTTPServer | None = None
    _thread: threading.Thread | None = None
    base: str = ""

    def __enter__(self) -> "MockA2AHub":
        hub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: Any) -> None:
                return

            def do_POST(self) -> None:
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n).decode("utf-8") if n else ""
                hub.pings.append(raw)
                blob = json.dumps(
                    {
                        "task": {
                            "id": "task-wait",
                            "status": {"state": "TASK_STATE_SUBMITTED"},
                        }
                    }
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(blob)))
                self.end_headers()
                self.wfile.write(blob)

            def do_GET(self) -> None:
                blob = b'{"ok":true}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(blob)))
                self.end_headers()
                self.wfile.write(blob)

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


def _waiter_env(home: Path, api_base: str, hub: str) -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "TMPDIR": str(home),
        "CURSOR_API_BASE": api_base,
        "CURSOR_API_KEY": FAKE_KEY,
        "CLOUD_FORCE_REST": "1",
        "CLOUD_WATCH_INTERVAL": "5",
        "CLOUD_WATCH_TIMEOUT_SEC": "8",
        "GCS_ROOT": str(ROOT),
        "GCS_A2A_STATE": str(home / "a2a-state"),
        "GCS_DIRECTOR_SEAT": "ops",
        "GCS_A2A_HUB": hub,
        "LC_ALL": "C",
        "NODE_NO_WARNINGS": "1",
    }


def _run_wait_notify(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(RUN_SH), "wait-notify", *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=env,
        timeout=90,
    )


def test_wait_notify_rest_does_not_fleet_done_leftover_while_newer_running(
    tmp_path: Path,
) -> None:
    with WaiterMockAPI(latest_status="RUNNING") as api, MockA2AHub() as hub:
        env = _waiter_env(tmp_path, api.base, hub.base)
        proc = _run_wait_notify(env, "--id", "bc-wait", "--run", "run-leftover")
        collection = [g for g in api.gets if g.rstrip("/") == "/v1/agents/bc-wait/runs"]
        combined = proc.stdout + proc.stderr
        pings = "\n".join(hub.pings)

    assert collection, f"waiter must GET runs collection, gets={api.gets}"
    assert "FLEET_DONE" not in combined
    assert "FLEET_DONE" not in pings
    assert "CLOUD_WAITER_DONE" not in combined
    assert "runStatus=RUNNING" in combined or "CREATING" in combined
    assert FAKE_KEY not in combined


def test_wait_notify_rest_fleet_done_latest_finished_not_leftover_id(
    tmp_path: Path,
) -> None:
    with WaiterMockAPI(latest_status="FINISHED") as api, MockA2AHub() as hub:
        env = _waiter_env(tmp_path, api.base, hub.base)
        env["CLOUD_WATCH_TIMEOUT_SEC"] = "15"
        proc = _run_wait_notify(env, "--id", "bc-wait", "--run", "run-leftover")
        combined = proc.stdout + proc.stderr
        pings = "\n".join(hub.pings)
        collection = [g for g in api.gets if g.rstrip("/") == "/v1/agents/bc-wait/runs"]

    assert proc.returncode == 0, combined
    assert collection, api.gets
    assert "CLOUD_WAITER_DONE" in combined
    assert "runStatus=FINISHED" in combined
    assert "FLEET_DONE" in pings
    assert "run-new" in combined or "run-new" in pings
    assert FAKE_KEY not in combined
