"""Waiter ping: latest run CANCELLED + prUrl is INSPECT, not PR_READY.

When Extra High already opened a PR and the latest run is CANCELLED,
the owning-seat ping must say INSPECT follow-up-or-close. QA must not
squash on MERGE_REQUEST.

Does not remint GCS #52 (draft) or #58 (mergeable=CONFLICTING).
Never Bot CloudAgent. Extra High stays grok-4.6 xhigh fast=false.
Living Sky Linear (LIV).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cloud"))
sys.path.insert(0, str(ROOT / "scripts" / "a2a"))

from fleet_ledger import notify_owner, notify_text  # noqa: E402

CLOUD = ROOT / "scripts" / "cloud"
WAIT_TS = CLOUD / "sdk" / "wait-notify.ts"
WAIT_NOTIFY = CLOUD / "sdk" / "run.sh"
LAUNCH_SH = ROOT / "scripts" / "launch-cloud-extra-high.sh"
FAKE_KEY = "test-cursor-api-key-waiter-cancelled"
GCS_PR = "https://github.com/atebites-hub/grok-cloud-studio/pull/41"
MERGE_READY = "ping QA (odd→qa-a, even→qa-b) MERGE_REQUEST"
_SDK_NODE = Path.home() / ".cache" / "gcs-node" / "v22.14.0" / "bin" / "node"


def _cancelled_payload(**extra: object) -> dict:
    body: dict = {
        "runStatus": "CANCELLED",
        "prUrl": GCS_PR,
        "name": "LIV-cancelled",
        "url": "https://cursor.com/agents/bc-cancelled",
    }
    body.update(extra)
    return body


def test_notify_text_cancelled_with_prurl_is_inspect_not_merge_request() -> None:
    text = notify_text("bc-cancelled", _cancelled_payload())
    assert "INSPECT" in text
    assert "follow-up-or-close" in text
    assert "PR_READY" not in text
    assert "MERGE_REQUEST" not in text
    assert MERGE_READY not in text
    assert "runStatus=CANCELLED" in text
    assert GCS_PR in text


def test_notify_text_canceled_us_spelling_is_inspect() -> None:
    text = notify_text("bc-canceled", _cancelled_payload(runStatus="CANCELED"))
    assert "INSPECT" in text
    assert "follow-up-or-close" in text
    assert "PR_READY" not in text
    assert "MERGE_REQUEST" not in text
    assert "runStatus=CANCELLED" in text


def test_notify_text_finished_with_pr_is_not_cancelled_inspect() -> None:
    """FINISHED+prUrl stays PR_READY (ship-gate HOLD may apply). Not INSPECT."""
    text = notify_text(
        "bc-ready",
        {
            "runStatus": "FINISHED",
            "prUrl": GCS_PR,
            "name": "LIV-ready",
            "url": "https://cursor.com/agents/bc-ready",
        },
    )
    assert "FLEET_DONE / PR_READY:" in text
    assert "INSPECT" not in text
    assert "follow-up-or-close" not in text


def test_notify_owner_cancelled_ping_is_inspect(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GCS_ROOT", str(ROOT))
    monkeypatch.setenv("GCS_A2A_STATE", str(tmp_path))
    monkeypatch.setenv("GCS_DIRECTOR_SEAT", "ops")
    pings: list[tuple[str, str]] = []

    def _ping(seat: str, text: str) -> bool:
        pings.append((seat, text))
        return True

    monkeypatch.setattr("fleet_ledger.ping_seat", _ping)
    row = notify_owner(
        "bc-cancelled",
        _cancelled_payload(),
        notified_by="waiter",
        seat="ops",
    )
    assert pings, "expected A2A ping"
    assert pings[0][0] == "ops"
    for _seat, text in pings:
        assert "INSPECT" in text
        assert "follow-up-or-close" in text
        assert "PR_READY" not in text
        assert MERGE_READY not in text
        assert "MERGE_REQUEST" not in text
    assert row.get("run_status") == "CANCELLED"


def test_footer_cancelled_inspect_not_bot_cloudagent() -> None:
    footer = (ROOT / "scripts" / "directors" / "common_footer.txt").read_text(encoding="utf-8")
    assert "INSPECT" in footer
    assert "follow-up-or-close" in footer
    assert "CANCELLED" in footer
    assert "Never Bot CloudAgent" in footer
    src = WAIT_TS.read_text(encoding="utf-8")
    launch = LAUNCH_SH.read_text(encoding="utf-8")
    latest_ts = (CLOUD / "sdk" / "latest_run.ts").read_text(encoding="utf-8")
    blob = src + "\n" + latest_ts
    assert "waiterObserve" in src
    assert "listRuns" in src
    assert "occupancy-count" not in blob
    assert "grok-4.6" in launch
    assert "xhigh" in launch
    assert "fast" in launch and "false" in launch
    # Do not remint GCS #52 / #58; not occupancy; not leftover Palemon.
    assert "githubPrIsDraft" not in src
    assert "githubPrMergeable" not in src
    assert "pr-draft.ts" not in src
    assert "pr-mergeable.ts" not in src


def _node_with_npm() -> str:
    """Prefer a Node >= 22.13 whose sibling npm exists (official tarball / nvm)."""
    candidates: list[Path] = []
    env_node = (os.environ.get("GCS_NODE") or "").strip()
    if env_node:
        candidates.append(Path(env_node))
    candidates.append(_SDK_NODE)
    nvm_root = Path.home() / ".nvm" / "versions" / "node"
    if nvm_root.is_dir():
        candidates.extend(sorted(nvm_root.glob("v22.*/bin/node"), reverse=True))
    which = shutil.which("node")
    if which:
        candidates.append(Path(which))
    seen: set[str] = set()
    with_npm: list[str] = []
    any_ok: list[str] = []
    for cand in candidates:
        path = str(cand)
        if path in seen or not cand.is_file():
            continue
        seen.add(path)
        any_ok.append(path)
        if (cand.parent / "npm").is_file():
            with_npm.append(path)
    return (with_npm or any_ok or [""])[0]


def _script_env(
    home: Path,
    *,
    api_base: str = "",
    hub: str = "",
    **extra: str,
) -> dict[str, str]:
    node_bin = extra.get("GCS_NODE") or _node_with_npm()
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
        "CLOUD_WATCH_TIMEOUT_SEC": "15",
        "GITHUB_API_BASE": "http://127.0.0.1:1",
        "LC_ALL": "C",
        "CLOUD_FORCE_REST": "1",
        "NODE_NO_WARNINGS": "1",
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
class MockCursorLatestCancelled:
    """Spawn-time run is FINISHED with prUrl; agent's latest run is CANCELLED."""

    pr_url: str = GCS_PR
    latest_run_id: str = "run-cancelled"
    spawn_run_id: str = "run-finished"
    paths: list[str] = field(default_factory=list)
    _httpd: ThreadingHTTPServer | None = None
    _thread: threading.Thread | None = None
    base: str = ""

    def __enter__(self) -> "MockCursorLatestCancelled":
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

            def _run(self, run_id: str, status: str, created: int, agent_id: str) -> dict[str, Any]:
                return {
                    "id": run_id,
                    "agentId": agent_id,
                    "status": status,
                    "createdAt": created,
                    "git": {
                        "branches": [
                            {"branch": "cursor/liv-cancelled", "prUrl": api.pr_url}
                        ]
                    },
                }

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                api.paths.append(parsed.path)
                parts = [p for p in parsed.path.split("/") if p]
                if len(parts) == 3 and parts[:2] == ["v1", "agents"]:
                    self._send(
                        200,
                        {
                            "id": parts[2],
                            "name": "gcs-cancelled-inspect",
                            "status": "ERROR",
                            "url": f"https://cursor.com/agents/{parts[2]}",
                            "latestRunId": api.spawn_run_id,
                        },
                    )
                    return
                if len(parts) == 4 and parts[:2] == ["v1", "agents"] and parts[3] == "runs":
                    self._send(
                        200,
                        {
                            "items": [
                                self._run(api.spawn_run_id, "FINISHED", 1_000, parts[2]),
                                self._run(api.latest_run_id, "CANCELLED", 2_000, parts[2]),
                            ]
                        },
                    )
                    return
                if len(parts) == 5 and parts[:2] == ["v1", "agents"] and parts[3] == "runs":
                    run_id = parts[4]
                    status = "CANCELLED" if run_id == api.latest_run_id else "FINISHED"
                    created = 2_000 if run_id == api.latest_run_id else 1_000
                    self._send(200, self._run(run_id, status, created, parts[2]))
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
    texts: list[str] = field(default_factory=list)
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
                raw = self.rfile.read(n) if n else b"{}"
                try:
                    body = json.loads(raw.decode("utf-8"))
                except json.JSONDecodeError:
                    body = {}
                message = body.get("message") or {}
                for part in message.get("parts") or []:
                    if isinstance(part, dict) and part.get("text"):
                        hub.texts.append(str(part["text"]))
                reply = json.dumps(
                    {
                        "task": {
                            "id": "task-waiter-cancelled",
                            "status": {"state": "TASK_STATE_SUBMITTED"},
                        }
                    }
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(reply)))
                self.end_headers()
                self.wfile.write(reply)

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


def _run_wait_notify(env: dict[str, str], spawn_run: str = "run-finished") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(WAIT_NOTIFY), "wait-notify", "--id", "bc-cancelled", "--run", spawn_run],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=env,
        timeout=180,
    )


def test_wait_notify_latest_cancelled_with_prurl_is_inspect_not_merge_ready(
    tmp_path: Path,
) -> None:
    with MockCursorLatestCancelled(pr_url=GCS_PR) as cursor, FakeA2AHub() as hub:
        env = _script_env(tmp_path, api_base=cursor.base, hub=hub.base)
        proc = _run_wait_notify(env, spawn_run="run-finished")
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, combined
    assert "CLOUD_WAITER_DONE" in combined
    assert "runStatus=CANCELLED" in combined
    assert FAKE_KEY not in combined
    assert any(p.rstrip("/") == "/v1/agents/bc-cancelled/runs" for p in cursor.paths), (
        f"waiter must GET runs collection, paths={cursor.paths}"
    )
    assert any("/runs/run-cancelled" in p for p in cursor.paths), (
        "waiter must poll the latest CANCELLED run, not only spawn --run"
    )
    assert hub.texts, "waiter must A2A-ping the owning seat"
    for ping in hub.texts:
        assert "INSPECT" in ping
        assert "follow-up-or-close" in ping
        assert "PR_READY" not in ping
        assert MERGE_READY not in ping
        assert "MERGE_REQUEST" not in ping
        assert GCS_PR in ping
