"""Extra High launch: mock REST, require GCS_CLOUD_REPO, never print keys.

--name REFUSE when a live runStatus=RUNNING agent already has that name
(prevent twin remint). ACTIVE+FINISHED leftovers do not block. Never Bot
CloudAgent. Model grok-4.6 effort=xhigh fast=false. Does not remint GCS
#49 followup-refuse.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest

REPO = Path(__file__).resolve().parents[1]
LAUNCH = REPO / "scripts" / "launch-cloud-extra-high.sh"
CLOUD = REPO / "scripts" / "cloud"
FAKE_KEY = "test-cursor-api-key"
EXAMPLE_REPO = "https://github.com/atebites-hub/grok-cloud-studio"


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
        "CLOUD_WATCH_INTERVAL": "0.05",
        "CLOUD_WATCH_TIMEOUT_SEC": "4",
        "CLOUD_CURL_CONNECT_TIMEOUT": "2",
        "CLOUD_CURL_MAX_TIME": "5",
        "LC_ALL": "C",
        "GCS_ROOT": str(REPO),
    }
    env.update(extra)
    return env


def _run(path: Path, args: list[str], env: dict[str, str], stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(path), *args],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env=env,
        input=stdin,
        timeout=20,
    )


def _basic_user(header: str | None) -> str:
    if not header or not header.startswith("Basic "):
        return ""
    raw = base64.b64decode(header.split(" ", 1)[1]).decode("utf-8")
    return raw.split(":", 1)[0]


@dataclass
class MockCursorAPI:
    create_http: int = 201
    create_body: dict[str, Any] | None = None
    list_items: list[dict[str, Any]] = field(default_factory=list)
    run_statuses: list[str] = field(default_factory=lambda: ["FINISHED"])
    followup_http: int = 201
    posts: list[dict[str, Any]] = field(default_factory=list)
    gets: list[str] = field(default_factory=list)
    auth_users: list[str] = field(default_factory=list)
    agents: dict[str, dict[str, Any]] = field(default_factory=dict)
    _run_i: int = 0
    _httpd: ThreadingHTTPServer | None = None
    _thread: threading.Thread | None = None
    base: str = ""

    def __enter__(self) -> "MockCursorAPI":
        api = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: Any) -> None:
                return

            def _read_json(self) -> dict[str, Any] | None:
                n = int(self.headers.get("Content-Length") or 0)
                if n <= 0:
                    return None
                return json.loads(self.rfile.read(n).decode("utf-8"))

            def _send(self, code: int, payload: dict[str, Any] | list[Any] | None = None) -> None:
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
                    items = list(api.list_items)
                    seen = {str(item.get("id") or "") for item in items}
                    for agent_id, cfg in api.agents.items():
                        if agent_id in seen:
                            continue
                        items.append(
                            {
                                "id": agent_id,
                                "name": cfg.get("name") or "mock-agent",
                                "status": cfg.get("status") or "ACTIVE",
                                "url": cfg.get("url") or f"https://cursor.com/agents/{agent_id}",
                                "latestRunId": cfg["latestRunId"] if "latestRunId" in cfg else "run-mock",
                            }
                        )
                    self._send(200, {"items": items})
                    return
                if len(parts) == 3 and parts[:2] == ["v1", "agents"]:
                    agent_id = parts[2]
                    cfg = api.agents.get(agent_id) or {}
                    latest = cfg["latestRunId"] if "latestRunId" in cfg else "run-mock"
                    self._send(
                        200,
                        {
                            "id": agent_id,
                            "name": cfg.get("name") or "mock-agent",
                            "status": cfg.get("status") or "ACTIVE",
                            "url": cfg.get("url") or f"https://cursor.com/agents/{agent_id}",
                            "latestRunId": latest,
                        },
                    )
                    return
                if len(parts) == 5 and parts[:2] == ["v1", "agents"] and parts[3] == "runs":
                    cfg = api.agents.get(parts[2]) or {}
                    if "runStatus" in cfg:
                        status = str(cfg["runStatus"])
                    else:
                        seq = api.run_statuses or ["RUNNING"]
                        if api._run_i < len(seq):
                            status = seq[api._run_i]
                            api._run_i += 1
                        else:
                            status = seq[-1]
                    self._send(
                        200,
                        {
                            "id": parts[4],
                            "agentId": parts[2],
                            "status": status,
                        },
                    )
                    return
                self._send(404, {"error": "not_found"})

            def do_POST(self) -> None:
                api.auth_users.append(_basic_user(self.headers.get("Authorization")))
                parsed = urlparse(self.path)
                parts = [p for p in parsed.path.split("/") if p]
                body = self._read_json()
                api.posts.append({"path": parsed.path, "body": body})
                if parts == ["v1", "agents"]:
                    payload = api.create_body or {
                        "agent": {
                            "id": "bc-mock",
                            "name": "mock-agent",
                            "status": "ACTIVE",
                            "url": "https://cursor.com/agents/bc-mock",
                            "latestRunId": "run-mock",
                        },
                        "run": {"id": "run-mock", "agentId": "bc-mock", "status": "CREATING"},
                    }
                    self._send(api.create_http, payload)
                    return
                if len(parts) == 4 and parts[:2] == ["v1", "agents"] and parts[3] == "runs":
                    self._send(
                        api.followup_http,
                        {
                            "run": {
                                "id": "run-followup",
                                "agentId": parts[2],
                                "status": "CREATING",
                            }
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


def test_launch_posts_parameterized_repo(tmp_path: Path) -> None:
    with MockCursorAPI(create_http=201) as api:
        proc = _run(
            LAUNCH,
            ["--name", "gcs-eh-test", "Implement the assigned outcome. Open a PR."],
            _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY),
        )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "CLOUD_LAUNCH_OK" in proc.stdout
    assert "CLOUD_LAUNCH_ERR" not in proc.stdout
    assert FAKE_KEY not in proc.stdout
    assert FAKE_KEY not in proc.stderr
    body = api.posts[0]["body"]
    assert body["model"]["id"] == "grok-4.6"
    params = {(p["id"], p["value"]) for p in body["model"]["params"]}
    assert ("effort", "xhigh") in params
    assert ("fast", "false") in params
    assert body["repos"] == [{"url": EXAMPLE_REPO, "startingRef": "main"}]
    assert body["autoCreatePR"] is True
    assert body["name"] == "gcs-eh-test"


def test_launch_fail_closed_without_cloud_repo(tmp_path: Path) -> None:
    with MockCursorAPI() as api:
        env = _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY)
        env.pop("GCS_CLOUD_REPO", None)
        env.pop("CLOUD_REPO_URL", None)
        env.pop("CURSOR_CLOUD_REPO", None)
        proc = _run(LAUNCH, ["should-fail"], env)
    assert proc.returncode != 0
    assert "CLOUD_LAUNCH_ERR" in proc.stdout
    assert "CLOUD_LAUNCH_OK" not in proc.stdout
    assert not api.posts


def test_launch_missing_auth_is_err(tmp_path: Path) -> None:
    with MockCursorAPI() as api:
        proc = _run(LAUNCH, ["no-key"], _script_env(tmp_path, api.base))
    assert proc.returncode != 0
    assert "CLOUD_LAUNCH_ERR" in proc.stdout
    assert not api.posts


@pytest.mark.parametrize("code", [202, 400, 401, 500])
def test_launch_fail_closed_when_not_200_or_201(tmp_path: Path, code: int) -> None:
    with MockCursorAPI(create_http=code, create_body={"error": "nope"}) as api:
        proc = _run(LAUNCH, ["should-fail"], _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY))
    assert proc.returncode != 0
    assert "CLOUD_LAUNCH_ERR" in proc.stdout
    assert "CLOUD_LAUNCH_OK" not in proc.stdout
    assert FAKE_KEY not in proc.stdout + proc.stderr


def test_list_status_do_not_print_keys(tmp_path: Path) -> None:
    items = [
        {
            "id": "bc-1",
            "name": "one",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-1",
            "latestRunId": "run-1",
        }
    ]
    with MockCursorAPI(list_items=items) as api:
        env = _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY)
        listed = _run(CLOUD / "list.sh", [], env)
        status = _run(CLOUD / "status.sh", ["bc-1"], env)
    assert listed.returncode == 0, listed.stdout + listed.stderr
    assert "bc-1" in listed.stdout
    assert status.returncode == 0, status.stdout + status.stderr
    assert FAKE_KEY not in listed.stdout + listed.stderr + status.stdout + status.stderr


def test_sdk_launch_does_not_hardcode_private_repo() -> None:
    src = (CLOUD / "sdk" / "launch.ts").read_text(encoding="utf-8")
    common = (CLOUD / "sdk" / "common.ts").read_text(encoding="utf-8")
    banned = "atebites-hub/" + "palemon"
    assert banned not in src
    assert banned not in common
    assert "cloudRepo()" in common
    assert "GCS_CLOUD_REPO" in common


def _create_posts(api: MockCursorAPI) -> list[dict[str, Any]]:
    return [p for p in api.posts if str(p.get("path") or "").rstrip("/") == "/v1/agents"]


LIVE_NAME = "floor-iac"
LAUNCH_NAME_ARGS = (
    ["--name", LIVE_NAME, "Implement the assigned outcome. Open a PR."],
    ["Implement the assigned outcome. Open a PR.", LIVE_NAME],
)


@pytest.mark.parametrize("args", LAUNCH_NAME_ARGS, ids=["flag", "positional"])
def test_launch_refuses_same_name_when_runstatus_running(tmp_path: Path, args: list[str]) -> None:
    """Live runStatus=RUNNING with the same --name must not remint a twin."""
    with MockCursorAPI(
        agents={
            "bc-live": {
                "status": "ACTIVE",
                "latestRunId": "run-live",
                "runStatus": "RUNNING",
                "name": LIVE_NAME,
            }
        }
    ) as api:
        proc = _run(LAUNCH, args, _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY))
    combined = proc.stdout + proc.stderr
    assert proc.returncode != 0, combined
    assert "CLOUD_LAUNCH_OK" not in proc.stdout
    err_lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("CLOUD_LAUNCH_ERR")]
    assert err_lines, combined
    refuse = err_lines[0]
    assert "runStatus=RUNNING" in refuse, refuse
    assert not _create_posts(api), api.posts
    assert any("/runs/run-live" in path for path in api.gets), api.gets
    assert FAKE_KEY not in combined


def test_launch_allows_active_finished_leftover_same_name(tmp_path: Path) -> None:
    """ACTIVE+FINISHED leftover with the same name is idle, not a live twin."""
    with MockCursorAPI(
        agents={
            "bc-leftover": {
                "status": "ACTIVE",
                "latestRunId": "run-done",
                "runStatus": "FINISHED",
                "name": LIVE_NAME,
            }
        }
    ) as api:
        proc = _run(
            LAUNCH,
            ["--name", LIVE_NAME, "Implement the assigned outcome. Open a PR."],
            _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY),
        )
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, combined
    assert "CLOUD_LAUNCH_OK" in proc.stdout
    assert "CLOUD_LAUNCH_ERR" not in proc.stdout
    posts = _create_posts(api)
    assert len(posts) == 1, api.posts
    body = posts[0]["body"]
    assert body["name"] == LIVE_NAME
    assert body["model"]["id"] == "grok-4.6"
    params = {(p["id"], p["value"]) for p in body["model"]["params"]}
    assert ("effort", "xhigh") in params
    assert ("fast", "false") in params
    assert any("/runs/run-done" in path for path in api.gets), api.gets
    assert FAKE_KEY not in combined


def test_launch_refuses_lowercase_running_same_name(tmp_path: Path) -> None:
    with MockCursorAPI(
        agents={
            "bc-running-lc": {
                "status": "ACTIVE",
                "latestRunId": "run-live",
                "runStatus": "running",
                "name": LIVE_NAME,
            }
        }
    ) as api:
        proc = _run(
            LAUNCH,
            ["--name", LIVE_NAME, "Do not remint a twin."],
            _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY),
        )
    assert proc.returncode != 0
    refuse = [ln for ln in proc.stdout.splitlines() if ln.startswith("CLOUD_LAUNCH_ERR")][0]
    assert "runStatus=RUNNING" in refuse
    assert not _create_posts(api)


def test_launch_allows_running_agent_with_different_name(tmp_path: Path) -> None:
    """A live worker under another name is not a same-name twin."""
    with MockCursorAPI(
        agents={
            "bc-other": {
                "status": "ACTIVE",
                "latestRunId": "run-other",
                "runStatus": "RUNNING",
                "name": "ops-other",
            }
        }
    ) as api:
        proc = _run(
            LAUNCH,
            ["--name", LIVE_NAME, "Implement the assigned outcome. Open a PR."],
            _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY),
        )
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, combined
    assert "CLOUD_LAUNCH_OK" in proc.stdout
    assert len(_create_posts(api)) == 1
    assert FAKE_KEY not in combined


def test_launch_unnamed_does_not_collide_on_running_name(tmp_path: Path) -> None:
    """No --name means no same-name twin check."""
    with MockCursorAPI(
        agents={
            "bc-live": {
                "status": "ACTIVE",
                "latestRunId": "run-live",
                "runStatus": "RUNNING",
                "name": LIVE_NAME,
            }
        }
    ) as api:
        proc = _run(
            LAUNCH,
            ["Implement the assigned outcome. Open a PR."],
            _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY),
        )
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, combined
    assert "CLOUD_LAUNCH_OK" in proc.stdout
    assert len(_create_posts(api)) == 1
    posts = _create_posts(api)
    assert "name" not in (posts[0]["body"] or {})


def test_launch_refuses_bot_cloudagent_name(tmp_path: Path) -> None:
    """Grok Bot orchestrator id is never an Extra High --name / CloudAgent."""
    bot_id = "bot-orchestrator-not-a-cloud-agent"
    with MockCursorAPI() as api:
        proc = _run(
            LAUNCH,
            ["--name", bot_id, "Do not treat Bot as Extra High."],
            _script_env(
                tmp_path,
                api.base,
                CURSOR_API_KEY=FAKE_KEY,
                GCS_BOT_AGENT_ID=bot_id,
            ),
        )
    combined = proc.stdout + proc.stderr
    assert proc.returncode != 0, combined
    assert "CLOUD_LAUNCH_ERR" in proc.stdout
    assert "CLOUD_LAUNCH_OK" not in proc.stdout
    assert "Bot CloudAgent" in combined or "never Bot" in combined.lower()
    assert not _create_posts(api), api.posts
    assert FAKE_KEY not in combined


def test_sdk_launch_refuses_running_same_name_before_create() -> None:
    """Direct sdk/run.sh launch must check latest runStatus before Agent.create."""
    src = (CLOUD / "sdk" / "launch.ts").read_text(encoding="utf-8")
    running_at = src.find("RUNNING")
    create_at = src.find("Agent.create")
    assert running_at != -1
    assert create_at != -1
    assert running_at < create_at
    assert "CLOUD_LAUNCH_ERR" in src
    assert "runStatus" in src
    assert "GCS_BOT_AGENT_ID" in src or "Bot CloudAgent" in src
    assert "grok-4.6" in src or "extraHighModel" in src
