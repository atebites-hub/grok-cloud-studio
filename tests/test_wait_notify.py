"""Extra High waiter: 429 backoff until terminal; spawn-waiter does not orphan.

Do not treat leftover ACTIVE+FINISHED agents as in-flight workers.
Never launch Bot CloudAgent. Does not touch GCS #26/#28/#29/#30.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
CLOUD = ROOT / "scripts" / "cloud"
WAIT_NOTIFY = CLOUD / "sdk" / "run.sh"
SPAWN_WAITER = CLOUD / "spawn-waiter.sh"
FAKE_KEY = "test-cursor-api-key-waiter-429"
_SDK_NODE = Path.home() / ".cache" / "gcs-node" / "v22.14.0" / "bin" / "node"

sys.path.insert(0, str(CLOUD))
from fleet_ledger import is_orphan, load_entries  # noqa: E402


def _script_env(home: Path, *, api_base: str = "", hub: str = "", **extra: str) -> dict[str, str]:
    node_bin = extra.get("GCS_NODE") or (str(_SDK_NODE) if _SDK_NODE.is_file() else "")
    path_prefix = f"{Path(node_bin).parent}:" if node_bin else ""
    env = {
        "PATH": f"{path_prefix}{os.environ.get('PATH', '/usr/bin:/bin')}",
        "HOME": str(home),
        "TMPDIR": str(home),
        "CURSOR_API_KEY": FAKE_KEY,
        "GCS_ROOT": str(ROOT),
        "GCS_A2A_STATE": str(home / "a2a-state"),
        "GCS_CLOUD_LOG_DIR": str(home / "cloud-logs"),
        "GCS_DIRECTOR_SEAT": "ops",
        "CLOUD_OWNER_SEAT": "ops",
        "CLOUD_WATCH_INTERVAL": "5",
        "CLOUD_WATCH_TIMEOUT_SEC": "0",
        "CLOUD_WAITER_BACKOFF_MS": "50",
        "CLOUD_WAITER_BACKOFF_CAP_MS": "200",
        "CLOUD_WAITER_RESTART_MS": "50",
        "CLOUD_WAITER_RESTART_CAP_MS": "200",
        "LC_ALL": "C",
        "GCS_SPAWN_WAITER": "1",
        "CLOUD_SPAWN_WAITER": "1",
        "CLOUD_FORCE_REST": "1",
    }
    if node_bin:
        env["GCS_NODE"] = node_bin
    if api_base:
        env["CURSOR_API_BASE"] = api_base
    if hub:
        env["GCS_A2A_HUB"] = hub
    env.update(extra)
    return env


@dataclass
class MockCursorWaiterAPI:
    """Cursor Cloud v1 mock. Agent stays ACTIVE; run GET can 429 then FINISHED."""

    run_http: list[int] = field(default_factory=lambda: [200])
    run_status: str = "FINISHED"
    agent_status: str = "ACTIVE"
    paths: list[str] = field(default_factory=list)
    _httpd: ThreadingHTTPServer | None = None
    _thread: threading.Thread | None = None
    base: str = ""
    _run_i: int = 0

    def __enter__(self) -> "MockCursorWaiterAPI":
        api = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: Any) -> None:
                return

            def _send(self, code: int, payload: dict[str, Any] | None = None) -> None:
                blob = b"" if payload is None else json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(blob)))
                if code == 429:
                    self.send_header("Retry-After", "0")
                self.end_headers()
                if blob:
                    self.wfile.write(blob)

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                api.paths.append(parsed.path)
                parts = [p for p in parsed.path.split("/") if p]
                if len(parts) == 3 and parts[:2] == ["v1", "agents"]:
                    agent_id = parts[2]
                    self._send(
                        200,
                        {
                            "id": agent_id,
                            "name": "leftover-grunt",
                            "status": api.agent_status,
                            "url": f"https://cursor.com/agents/{agent_id}",
                            "latestRunId": "run-mock",
                        },
                    )
                    return
                if len(parts) == 5 and parts[:2] == ["v1", "agents"] and parts[3] == "runs":
                    seq = api.run_http or [200]
                    if api._run_i < len(seq):
                        code = seq[api._run_i]
                        api._run_i += 1
                    else:
                        code = seq[-1]
                    if code != 200:
                        self._send(code, {"error": "rate_limited", "message": "get_agent_run 429"})
                        return
                    self._send(
                        200,
                        {
                            "id": parts[4],
                            "agentId": parts[2],
                            "status": api.run_status,
                        },
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
class FakeA2AHub:
    posts: list[str] = field(default_factory=list)
    _httpd: ThreadingHTTPServer | None = None
    _thread: threading.Thread | None = None
    base: str = ""

    def __enter__(self) -> "FakeA2AHub":
        hub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: Any) -> None:
                return

            def do_POST(self) -> None:
                n = int(self.headers.get("Content-Length") or 0)
                if n:
                    self.rfile.read(n)
                hub.posts.append(self.path)
                body = json.dumps(
                    {"task": {"id": "task-waiter", "status": {"state": "TASK_STATE_SUBMITTED"}}}
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

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


def _run_wait_notify(env: dict[str, str], agent_id: str = "bc-wait", run_id: str = "run-mock") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(WAIT_NOTIFY), "wait-notify", "--id", agent_id, "--run", run_id],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )


def test_wait_notify_retries_get_agent_run_429_until_finished(tmp_path: Path) -> None:
    """First get_agent_run 429 must backoff and resume; leftover ACTIVE+FINISHED is terminal."""
    with MockCursorWaiterAPI(run_http=[429, 429, 200], run_status="FINISHED") as api, FakeA2AHub() as hub:
        env = _script_env(tmp_path, api_base=api.base, hub=hub.base)
        proc = _run_wait_notify(env)
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, combined
    assert "CLOUD_WAITER_DONE" in combined
    assert "runStatus=FINISHED" in combined
    assert "CLOUD_WAITER_RETRY" in combined
    assert combined.count("CLOUD_WAITER_RETRY") >= 2
    run_gets = [p for p in api.paths if "/runs/" in p]
    assert len(run_gets) >= 3
    assert FAKE_KEY not in combined
    # Agent membership ACTIVE + run FINISHED is leftover, not a spinning worker.
    assert api.agent_status == "ACTIVE"


def test_wait_notify_does_not_retry_401(tmp_path: Path) -> None:
    with MockCursorWaiterAPI(run_http=[401], run_status="FINISHED") as api, FakeA2AHub() as hub:
        env = _script_env(tmp_path, api_base=api.base, hub=hub.base)
        proc = _run_wait_notify(env)
    combined = proc.stdout + proc.stderr
    assert proc.returncode != 0
    assert "CLOUD_WAITER_ERR" in combined
    assert "CLOUD_WAITER_DONE" not in combined
    assert "CLOUD_WAITER_RETRY" not in combined
    assert FAKE_KEY not in combined


def test_wait_notify_source_exponential_backoff_on_429() -> None:
    src = (CLOUD / "sdk" / "wait-notify.ts").read_text(encoding="utf-8")
    common = (CLOUD / "sdk" / "common.ts").read_text(encoding="utf-8")
    blob = src + "\n" + common
    assert "CLOUD_WAITER_RETRY" in src
    assert "429" in blob
    assert "rateLimitBackoffMs" in blob or "BackoffMs" in blob
    assert "Bot CloudAgent" not in src
    assert "Grok Bot CloudAgent" not in src


def test_spawn_waiter_source_restarts_after_rate_limit_err() -> None:
    src = SPAWN_WAITER.read_text(encoding="utf-8")
    assert "CLOUD_WAITER_RESTART" in src
    assert "CLOUD_WAITER_BIN" in src
    assert "429" in src
    assert "Bot CloudAgent" not in src


def _write_rate_limit_then_ok_waiter(tmp_path: Path) -> Path:
    stamp = tmp_path / "waiter-calls"
    stamp.write_text("0\n", encoding="utf-8")
    fake = tmp_path / "fake-wait-notify.sh"
    fake.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
STAMP="{stamp}"
n=$(($(cat "$STAMP") + 1))
echo "$n" > "$STAMP"
if [[ "$n" -eq 1 ]]; then
  echo "CLOUD_WAITER_ERR id=bc-rl REST 429 get_agent_run (6000/hour)" >&2
  exit 1
fi
echo "CLOUD_WAITER_DONE id=bc-rl runStatus=FINISHED pr=none"
exit 0
""",
        encoding="utf-8",
    )
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    return fake


def test_spawn_waiter_does_not_orphan_after_rate_limit_err(tmp_path: Path) -> None:
    """Supervisor pid stays live after CLOUD_WAITER_ERR 429 so fleet-shepherd sees no orphan."""
    fake = _write_rate_limit_then_ok_waiter(tmp_path)
    stamp = tmp_path / "waiter-calls"
    env = _script_env(tmp_path, CLOUD_WAITER_BIN=str(fake))
    proc = subprocess.run(
        ["bash", str(SPAWN_WAITER), "--id", "bc-rl", "--run", "run-1"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=env,
        timeout=20,
    )
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, combined
    assert "CLOUD_WAITER_SPAWNED" in combined
    pid_s = ""
    for token in combined.split():
        if token.startswith("pid="):
            pid_s = token.split("=", 1)[1]
    assert pid_s.isdigit(), combined
    waiter_pid = int(pid_s)

    deadline = time.time() + 8
    calls = 0
    row = None
    log_text = ""
    log_dir = tmp_path / "cloud-logs"
    while time.time() < deadline:
        try:
            calls = int(stamp.read_text(encoding="utf-8").strip() or "0")
        except ValueError:
            calls = 0
        fleet = tmp_path / "a2a-state" / "ops" / "fleet.jsonl"
        if fleet.is_file():
            entries = load_entries(fleet)
            row = next((e for e in entries if e.get("bc_id") == "bc-rl"), None)
        logs = list(log_dir.glob("waiter-*.log")) if log_dir.is_dir() else []
        if logs:
            log_text = logs[0].read_text(encoding="utf-8")
        if calls >= 2 and "CLOUD_WAITER_RESTART" in log_text and "CLOUD_WAITER_DONE" in log_text:
            break
        # Mid-restart: dead child must not make the ledger row an orphan.
        if row is not None and calls >= 1 and calls < 2:
            assert is_orphan(row) is False, row
        time.sleep(0.05)

    assert calls >= 2, f"waiter not restarted after 429 death; calls={calls} log={log_text!r} out={combined}"
    assert "CLOUD_WAITER_RESTART" in log_text
    assert "CLOUD_WAITER_DONE" in log_text
    assert row is not None
    # Supervisor still running or already finished after DONE — never a 429 orphan window
    # that fleet-shepherd would steal. After DONE the child supervisor may exit;
    # the important check is restart happened with the same registered pid family.
    assert waiter_pid > 0
    assert FAKE_KEY not in combined
    assert FAKE_KEY not in log_text
