"""wait-notify FLEET_DONE: draft/CONFLICTING flags plus get_agent_run 429 backoff.

GCS #41 (LIV-67) draft is not MERGE_REQUEST-ready. Sibling product PRs
#301/#304 are mergeable_state=dirty: QA HOLD squash.
GCS #35: Extra High waiters backoff on get_agent_run HTTP 429 and resume
until the run is terminal. Do not remint occupancy.
Never Bot CloudAgent. Occupancy HOLD. Living Sky LIV-41 / LIV-67.
"""
from __future__ import annotations

import json
import os
import shutil
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
WAIT_TS = CLOUD / "sdk" / "wait-notify.ts"
WAIT_NOTIFY = CLOUD / "sdk" / "run.sh"
SPAWN_WAITER = CLOUD / "spawn-waiter.sh"
PR_MERGEABLE_TS = CLOUD / "sdk" / "pr-mergeable.ts"
PR_DRAFT_TS = CLOUD / "sdk" / "pr-draft.ts"
FAKE_KEY = "test-cursor-api-key-waiter-mergeable"

sys.path.insert(0, str(CLOUD))
from fleet_ledger import is_orphan, load_entries  # noqa: E402
PR301 = "https://github.com/atebites-hub/grok-cloud-studio/pull/301"
GCS41 = "https://github.com/atebites-hub/grok-cloud-studio/pull/41"
MERGE_READY = "ping QA (odd→qa-a, even→qa-b) MERGE_REQUEST"
HEAD_SHA = "abc123deadbeefmergeable"
_PASTE = (
    ".venv/bin/pytest -q\n"
    "3 passed in 0.01s\n"
    "python3 scripts/secret_scan.py\n"
    "secret_scan=clean\n"
)
_SDK_NODE = Path.home() / ".cache" / "gcs-node" / "v22.14.0" / "bin" / "node"


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


def test_wait_notify_source_flags_github_mergeable() -> None:
    src = WAIT_TS.read_text(encoding="utf-8")
    helper = PR_MERGEABLE_TS.read_text(encoding="utf-8") if PR_MERGEABLE_TS.is_file() else ""
    blob = src + "\n" + helper
    assert "githubPrMergeable" in blob
    assert "CONFLICTING" in blob
    assert "githubPrIsDraft" in src
    assert "pr-draft.ts" in src or PR_DRAFT_TS.is_file()
    assert "GITHUB_API_BASE" in blob
    assert "rateLimitBackoffMs" not in helper
    assert "CLOUD_WAITER_BACKOFF_MS" not in helper
    assert "occupancy-count" not in src
    assert "Bot CloudAgent" not in src
    assert "Grok Bot CloudAgent" not in src


def test_footer_and_qa_souls_hold_conflicting_squash() -> None:
    footer = (ROOT / "scripts" / "directors" / "common_footer.txt").read_text(encoding="utf-8")
    assert "mergeable=CONFLICTING" in footer
    assert "HOLD squash" in footer
    assert "draft=true" in footer
    for seat in ("qa-a", "qa-b"):
        soul = (ROOT / "docs" / "studio" / "directors" / "souls" / seat / "SOUL.md").read_text(
            encoding="utf-8"
        )
        assert "CONFLICTING" in soul
        assert "HOLD squash" in soul
        assert "draft" in soul.lower()
        assert "Bot CloudAgent" not in soul
    for name in (
        "qa_a.txt",
        "qa_b.txt",
        "qa_a_director_prompt.txt",
        "qa_b_director_prompt.txt",
    ):
        text = (ROOT / "prompts" / name).read_text(encoding="utf-8")
        assert "HOLD squash" in text
        assert "CONFLICTING" in text
        assert "draft" in text.lower()


def _script_env(
    home: Path,
    *,
    api_base: str = "",
    github_base: str = "",
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
        "CLOUD_WAITER_BACKOFF_MS": "50",
        "CLOUD_WAITER_BACKOFF_CAP_MS": "200",
        "CLOUD_WAITER_RESTART_MS": "50",
        "CLOUD_WAITER_RESTART_CAP_MS": "200",
        "LC_ALL": "C",
        "CLOUD_FORCE_REST": "1",
        "NODE_NO_WARNINGS": "1",
        "REPORT_TO": "ops",
        "GCS_SPAWN_WAITER": "1",
        "CLOUD_SPAWN_WAITER": "1",
    }
    env.pop("GH_TOKEN", None)
    env.pop("GITHUB_TOKEN", None)
    if node_bin:
        env["GCS_NODE"] = node_bin
    if api_base:
        env["CURSOR_API_BASE"] = api_base
    if github_base:
        env["GITHUB_API_BASE"] = github_base
    if hub:
        env["GCS_A2A_HUB"] = hub
    env.update(extra)
    return env


@dataclass
class MockCursorFinishedPR:
    pr_url: str = PR301
    run_status: str = "FINISHED"
    agent_status: str = "ACTIVE"
    run_id: str = "run-mock"
    result: str = _PASTE
    paths: list[str] = field(default_factory=list)
    _httpd: ThreadingHTTPServer | None = None
    _thread: threading.Thread | None = None
    base: str = ""

    def __enter__(self) -> "MockCursorFinishedPR":
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

            def _run(self, run_id: str, agent_id: str) -> dict[str, Any]:
                return {
                    "id": run_id,
                    "agentId": agent_id,
                    "status": api.run_status,
                    "createdAt": 1_000,
                    "result": api.result,
                    "git": {"branches": [{"branch": "cursor/liv-41", "prUrl": api.pr_url}]},
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
                            "name": "gcs-liv41",
                            "status": api.agent_status,
                            "url": f"https://cursor.com/agents/{parts[2]}",
                            "latestRunId": api.run_id,
                        },
                    )
                    return
                if len(parts) == 4 and parts[:2] == ["v1", "agents"] and parts[3] == "runs":
                    self._send(200, {"items": [self._run(api.run_id, parts[2])]})
                    return
                if len(parts) == 5 and parts[:2] == ["v1", "agents"] and parts[3] == "runs":
                    self._send(200, self._run(parts[4], parts[2]))
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
class MockGitHubPulls:
    mergeable_state: str = "dirty"
    mergeable: bool | None = False
    draft: bool = False
    ship_gate_ok: bool = True
    paths: list[str] = field(default_factory=list)
    _httpd: ThreadingHTTPServer | None = None
    _thread: threading.Thread | None = None
    base: str = ""

    def __enter__(self) -> "MockGitHubPulls":
        api = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: Any) -> None:
                return

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                api.paths.append(parsed.path)
                if parsed.path.endswith("/check-runs"):
                    runs = []
                    if api.ship_gate_ok:
                        runs = [
                            {
                                "name": "pytest -q and secret_scan",
                                "conclusion": "success",
                                "status": "completed",
                            }
                        ]
                    body = json.dumps({"total_count": len(runs), "check_runs": runs}).encode("utf-8")
                elif parsed.path.endswith("/status"):
                    body = json.dumps({"state": "success", "total_count": 1, "statuses": []}).encode(
                        "utf-8"
                    )
                else:
                    body = json.dumps(
                        {
                            "draft": api.draft,
                            "number": 301,
                            "html_url": PR301,
                            "state": "open",
                            "mergeable": api.mergeable,
                            "mergeable_state": api.mergeable_state,
                            "head": {"sha": HEAD_SHA},
                        }
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
                            "id": "task-waiter-mergeable",
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


def _run_wait_notify(
    env: dict[str, str],
    agent_id: str = "bc-liv41",
    run_id: str = "run-mock",
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(WAIT_NOTIFY), "wait-notify", "--id", agent_id, "--run", run_id],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=env,
        timeout=180,
    )


def test_wait_notify_ping_includes_mergeable_conflicting_hold(tmp_path: Path) -> None:
    with (
        MockCursorFinishedPR(pr_url=PR301) as cursor,
        MockGitHubPulls(mergeable_state="dirty", mergeable=False) as github,
        FakeA2AHub() as hub,
    ):
        env = _script_env(tmp_path, api_base=cursor.base, github_base=github.base, hub=hub.base)
        proc = _run_wait_notify(env)
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, combined
    assert "CLOUD_WAITER_DONE" in combined
    assert "mergeable=CONFLICTING" in combined
    assert FAKE_KEY not in combined
    assert github.paths, "waiter must query GitHub for mergeable status"
    assert hub.texts, "waiter must A2A-ping the owning seat"
    for ping in hub.texts:
        assert "mergeable=CONFLICTING" in ping
        assert "HOLD squash" in ping
        assert MERGE_READY not in ping
        assert ping.startswith("FLEET_DONE / PR_READY:")


def test_wait_notify_mergeable_pr_still_merge_request(tmp_path: Path) -> None:
    with (
        MockCursorFinishedPR(pr_url=PR301) as cursor,
        MockGitHubPulls(mergeable_state="clean", mergeable=True) as github,
        FakeA2AHub() as hub,
    ):
        env = _script_env(tmp_path, api_base=cursor.base, github_base=github.base, hub=hub.base)
        proc = _run_wait_notify(env)
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, combined
    assert "CLOUD_WAITER_DONE" in combined
    assert FAKE_KEY not in combined
    assert hub.texts
    for ping in hub.texts:
        assert "mergeable=CONFLICTING" not in ping
        assert MERGE_READY in ping
        assert "HOLD squash" not in ping
        assert "draft=true" not in ping


def test_wait_notify_source_flags_github_draft() -> None:
    src = WAIT_TS.read_text(encoding="utf-8")
    helper = PR_DRAFT_TS.read_text(encoding="utf-8") if PR_DRAFT_TS.is_file() else ""
    blob = src + "\n" + helper
    assert "githubPrIsDraft" in blob
    assert "draft=true" in blob or "draft" in src
    assert "GITHUB_API_BASE" in blob
    assert "rateLimitBackoffMs" not in helper
    assert "CLOUD_WAITER_BACKOFF_MS" not in helper
    assert "Bot CloudAgent" not in src
    assert "vendor/hermes" not in blob


def test_wait_notify_ping_includes_draft_true_not_merge_ready(tmp_path: Path) -> None:
    with (
        MockCursorFinishedPR(pr_url=GCS41) as cursor,
        MockGitHubPulls(draft=True, mergeable_state="clean", mergeable=True, ship_gate_ok=False) as github,
        FakeA2AHub() as hub,
    ):
        env = _script_env(tmp_path, api_base=cursor.base, github_base=github.base, hub=hub.base)
        proc = _run_wait_notify(env)
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, combined
    assert "CLOUD_WAITER_DONE" in combined
    assert "draft=true" in combined
    assert FAKE_KEY not in combined
    assert github.paths, "waiter must query GitHub for draft status"
    assert hub.texts, "waiter must A2A-ping the owning seat"
    ping = hub.texts[0]
    assert "draft=true" in ping
    assert MERGE_READY not in ping
    assert ping.startswith("FLEET_DONE / PR_READY:")


@dataclass
class MockCursorWaiterAPI:
    """Cursor Cloud v1 mock. Agent stays ACTIVE; run GET can 429 then FINISHED."""

    run_http: list[int] = field(default_factory=lambda: [200])
    run_status: str = "FINISHED"
    agent_status: str = "ACTIVE"
    run_id: str = "run-mock"
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

            def _run(self, run_id: str, agent_id: str) -> dict[str, Any]:
                return {
                    "id": run_id,
                    "agentId": agent_id,
                    "status": api.run_status,
                    "createdAt": 1_000,
                }

            def _next_run_code(self) -> int:
                seq = api.run_http or [200]
                if api._run_i < len(seq):
                    code = seq[api._run_i]
                    api._run_i += 1
                    return code
                return seq[-1]

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                api.paths.append(parsed.path)
                parts = [p for p in parsed.path.split("/") if p]
                if len(parts) == 3 and parts[:2] == ["v1", "agents"]:
                    self._send(
                        200,
                        {
                            "id": parts[2],
                            "name": "leftover-grunt",
                            "status": api.agent_status,
                            "url": f"https://cursor.com/agents/{parts[2]}",
                            "latestRunId": api.run_id,
                        },
                    )
                    return
                if len(parts) == 4 and parts[:2] == ["v1", "agents"] and parts[3] == "runs":
                    code = self._next_run_code()
                    if code != 200:
                        self._send(code, {"error": "rate_limited", "message": "get_agent_run 429"})
                        return
                    self._send(200, {"items": [self._run(api.run_id, parts[2])]})
                    return
                if len(parts) == 5 and parts[:2] == ["v1", "agents"] and parts[3] == "runs":
                    code = self._next_run_code()
                    if code != 200:
                        self._send(code, {"error": "rate_limited", "message": "get_agent_run 429"})
                        return
                    self._send(200, self._run(parts[4], parts[2]))
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


def test_wait_notify_retries_get_agent_run_429_until_finished(tmp_path: Path) -> None:
    """First get_agent_run 429 must backoff and resume; leftover ACTIVE+FINISHED is terminal."""
    with MockCursorWaiterAPI(run_http=[429, 429, 200], run_status="FINISHED") as api, FakeA2AHub() as hub:
        env = _script_env(tmp_path, api_base=api.base, hub=hub.base, CLOUD_WATCH_TIMEOUT_SEC="0")
        proc = _run_wait_notify(env, agent_id="bc-wait", run_id="run-mock")
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, combined
    assert "CLOUD_WAITER_DONE" in combined
    assert "runStatus=FINISHED" in combined
    assert "CLOUD_WAITER_RETRY" in combined
    assert combined.count("CLOUD_WAITER_RETRY") >= 2
    run_gets = [p for p in api.paths if "/runs" in p]
    assert len(run_gets) >= 3
    assert FAKE_KEY not in combined
    assert api.agent_status == "ACTIVE"


def test_wait_notify_does_not_retry_401(tmp_path: Path) -> None:
    with MockCursorWaiterAPI(run_http=[401], run_status="FINISHED") as api, FakeA2AHub() as hub:
        env = _script_env(tmp_path, api_base=api.base, hub=hub.base, CLOUD_WATCH_TIMEOUT_SEC="8")
        proc = _run_wait_notify(env, agent_id="bc-wait", run_id="run-mock")
    combined = proc.stdout + proc.stderr
    assert proc.returncode != 0
    assert "CLOUD_WAITER_ERR" in combined
    assert "CLOUD_WAITER_DONE" not in combined
    assert "CLOUD_WAITER_RETRY" not in combined
    assert FAKE_KEY not in combined


def test_wait_notify_source_exponential_backoff_on_429() -> None:
    src = WAIT_TS.read_text(encoding="utf-8")
    common = (CLOUD / "sdk" / "common.ts").read_text(encoding="utf-8")
    blob = src + "\n" + common
    assert "CLOUD_WAITER_RETRY" in src
    assert "429" in blob
    assert "rateLimitBackoffMs" in blob
    assert "Bot CloudAgent" not in src
    assert "Grok Bot CloudAgent" not in src
    assert "occupancy-count" not in src


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
        if row is not None and calls >= 1 and calls < 2:
            assert is_orphan(row) is False, row
        time.sleep(0.05)

    assert calls >= 2, f"waiter not restarted after 429 death; calls={calls} log={log_text!r} out={combined}"
    assert "CLOUD_WAITER_RESTART" in log_text
    assert "CLOUD_WAITER_DONE" in log_text
    assert row is not None
    assert waiter_pid > 0
    assert FAKE_KEY not in combined
    assert FAKE_KEY not in log_text
