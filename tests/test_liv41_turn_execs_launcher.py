"""BDD binding: director/mind turn execs the Extra High launcher (LIV-41).

Scenarios live in tests/bdd/liv41_turn_execs_launcher.feature.
A turn that finds latest-run runStatus RUNNING < 8 actually execs
scripts/launch-cloud-extra-high.sh. Not Donald cron. Not Bot CloudAgent.

Does not remint GCS #65 (Python capacity beat) or #75 (FAIL-without-spawn
judge / docs-only feature). Does not reuse --name gcs-liv41-mind-must-launch.
"""
from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import urlparse

import pytest

REPO = Path(__file__).resolve().parents[1]
FEATURE = REPO / "tests" / "bdd" / "liv41_turn_execs_launcher.feature"
HELPER_PY = REPO / "scripts" / "directors" / "liv41_turn_exec.py"
MIND_PY = REPO / "scripts" / "directors" / "mind.py"
LAUNCH_SH = REPO / "scripts" / "launch-cloud-extra-high.sh"
TICKER_PY = REPO / "scripts" / "a2a" / "host-ticker.py"
CLOCK_SH = REPO / "scripts" / "directors" / "host-clock-ticker.sh"
LAUNCH_REL = "scripts/launch-cloud-extra-high.sh"
RESERVED_NAME = "gcs-liv41-mind-must-launch"
TURN_NAME = "gcs-liv41-turn-exec"
PRIVATE_GAME = "atebites-hub/" + "palemon"
STUDIO_REPO = "https://github.com/atebites-hub/grok-cloud-studio"
OTHER_REPO = "https://github.com/example/other-remote"
FAKE_KEY = "test-cursor-api-key"
ACP_PING = (
    "ACP_PING STATUS/CONTINUE seat=floor token=tick-1. "
    "Keep-alive turn: do work, do not idle. Tools are allowed."
)

SCENARIO_BINDINGS = {
    "A director mind turn that finds RUNNING < 8 execs the launcher": (
        "test_mind_turn_under_floor_execs_real_launcher"
    ),
    "Leftover ACTIVE plus FINISHED is not a live worker": (
        "test_leftover_active_finished_and_creating_are_not_running"
    ),
    "At 8 RUNNING the turn does not exec the launcher": (
        "test_at_eight_running_does_not_exec_launcher"
    ),
    "Donald cron and Bot seats do not exec the launcher": (
        "test_donald_cron_and_bot_seats_do_not_exec_launcher"
    ),
}


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _write_exec(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def _append_inbox(state: Path, seat: str, task_id: str, text: str) -> None:
    seat_dir = state / seat
    seat_dir.mkdir(parents=True, exist_ok=True)
    inbox = seat_dir / "inbox.jsonl"
    rec = {
        "taskId": task_id,
        "contextId": "ctx-liv41-turn-exec",
        "parts": [{"kind": "text", "text": text}],
        "metadata": {"from": "ops"},
    }
    with inbox.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")


def feature_scenarios(path: Path) -> list[str]:
    names: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if raw.startswith("Scenario:"):
            names.append(raw[len("Scenario:") :].strip())
    return names


@dataclass
class MockCloudAPI:
    """List omits repos; GET agent binds repo; GET run is runStatus; POST create."""

    agents: list[dict[str, Any]] = field(default_factory=list)
    posts: list[dict[str, Any]] = field(default_factory=list)
    gets: list[str] = field(default_factory=list)
    create_http: int = 201
    _httpd: ThreadingHTTPServer | None = None
    _thread: threading.Thread | None = None
    base: str = ""

    def __enter__(self) -> "MockCloudAPI":
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

            def _agent(self, agent_id: str) -> dict[str, Any] | None:
                for item in api.agents:
                    if str(item.get("id") or "") == agent_id:
                        return item
                return None

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                api.gets.append(parsed.path)
                parts = [p for p in parsed.path.split("/") if p]
                if parts == ["v1", "agents"]:
                    items = []
                    for agent in api.agents:
                        items.append(
                            {
                                "id": agent["id"],
                                "status": agent.get("status") or "ACTIVE",
                                "name": agent.get("name") or "",
                                "url": f"https://cursor.com/agents/{agent['id']}",
                                "latestRunId": agent.get("latestRunId") or "run-1",
                            }
                        )
                    self._send(200, {"items": items})
                    return
                if len(parts) == 3 and parts[:2] == ["v1", "agents"]:
                    agent = self._agent(parts[2])
                    if agent is None:
                        self._send(404, {"error": "not_found"})
                        return
                    body: dict[str, Any] = {
                        "id": agent["id"],
                        "status": agent.get("status") or "ACTIVE",
                        "name": agent.get("name") or "",
                        "latestRunId": agent.get("latestRunId") or "run-1",
                    }
                    if not agent.get("unbound"):
                        repo = str(agent.get("repo") or STUDIO_REPO)
                        body["repos"] = [{"url": repo, "startingRef": "main"}]
                    self._send(200, body)
                    return
                if len(parts) == 5 and parts[:2] == ["v1", "agents"] and parts[3] == "runs":
                    agent = self._agent(parts[2])
                    if agent is None:
                        self._send(404, {"error": "not_found"})
                        return
                    status = str(agent.get("runStatus") or "FINISHED")
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
                parsed = urlparse(self.path)
                body = self._read_json()
                api.posts.append({"path": parsed.path, "body": body})
                parts = [p for p in parsed.path.split("/") if p]
                if parts == ["v1", "agents"]:
                    self._send(
                        api.create_http,
                        {
                            "agent": {
                                "id": "bc-liv41-turn-exec",
                                "name": (body or {}).get("name") or "mock-agent",
                                "status": "ACTIVE",
                                "url": "https://cursor.com/agents/bc-liv41-turn-exec",
                                "latestRunId": "run-new",
                            },
                            "run": {
                                "id": "run-new",
                                "agentId": "bc-liv41-turn-exec",
                                "status": "CREATING",
                            },
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


def _cloud_env(home: Path, base: str, **extra: str) -> dict[str, str]:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "TMPDIR": str(home),
        "CURSOR_API_BASE": base,
        "CURSOR_API_KEY": FAKE_KEY,
        "GCS_CLOUD_REPO": STUDIO_REPO,
        "GCS_CLOUD_REF": "main",
        "GCS_SPAWN_WAITER": "0",
        "CLOUD_SPAWN_WAITER": "0",
        "CLOUD_CURL_CONNECT_TIMEOUT": "2",
        "CLOUD_CURL_MAX_TIME": "5",
        "GCS_CLOUD_MIN_RUNNING": "8",
        "GCS_ROOT": str(REPO),
        "LC_ALL": "C",
    }
    env.update(extra)
    return env


def _apply_cloud_env(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> None:
    for key, value in env.items():
        monkeypatch.setenv(key, value)


def leftover_fleet() -> list[dict[str, Any]]:
    return [
        {
            "id": "bc-dead",
            "status": "ACTIVE",
            "name": "leftover",
            "latestRunId": "run-dead",
            "repo": STUDIO_REPO,
            "runStatus": "FINISHED",
        },
        {
            "id": "bc-create",
            "status": "ACTIVE",
            "name": "creating",
            "latestRunId": "run-c",
            "repo": STUDIO_REPO,
            "runStatus": "CREATING",
        },
        {
            "id": "bc-other",
            "status": "ACTIVE",
            "name": "other-remote",
            "latestRunId": "run-o",
            "repo": OTHER_REPO,
            "runStatus": "RUNNING",
        },
        {
            "id": "bc-unbound",
            "status": "ACTIVE",
            "name": "unbound",
            "latestRunId": "run-u",
            "runStatus": "RUNNING",
            "unbound": True,
        },
    ]


def eight_running_fleet() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i in range(8):
        rows.append(
            {
                "id": f"bc-live-{i}",
                "status": "ACTIVE",
                "name": f"live-{i}",
                "latestRunId": f"run-live-{i}",
                "repo": STUDIO_REPO,
                "runStatus": "RUNNING",
            }
        )
    return rows


def test_every_feature_scenario_has_an_executing_binding() -> None:
    assert FEATURE.is_file()
    names = feature_scenarios(FEATURE)
    assert names, "feature has no Scenario lines"
    assert names == list(SCENARIO_BINDINGS)
    this = sys.modules[__name__]
    for scenario, fn_name in SCENARIO_BINDINGS.items():
        fn = getattr(this, fn_name, None)
        assert callable(fn), f"unbound scenario {scenario!r} -> {fn_name}"
    text = FEATURE.read_text(encoding="utf-8")
    assert "LIV-41" in text
    assert LAUNCH_REL in text
    assert "runStatus" in text
    assert "RUNNING" in text
    assert "#65" in text and "#75" in text
    assert "Donald" in text or "donald" in text.lower()
    assert "Bot CloudAgent" in text
    assert "grok-4.6" in text
    assert "xhigh" in text
    assert "fast=false" in text
    assert PRIVATE_GAME not in text
    assert "docs/studio/bdd/liv41_directors_spawn.feature" not in text
    assert HELPER_PY.is_file()
    assert LAUNCH_SH.is_file()
    helper_src = HELPER_PY.read_text(encoding="utf-8")
    assert "cloud_capacity.py" not in helper_src
    assert "director_turn_spawn.py" not in helper_src
    assert "directors_spawn.py" not in helper_src
    assert PRIVATE_GAME not in helper_src


def test_leftover_active_finished_and_creating_are_not_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper = _load(HELPER_PY, "gcs_liv41_turn_exec_count")
    assert helper.DEFAULT_MIN_RUNNING == 8
    assert helper.is_running_status("RUNNING") is True
    assert helper.is_running_status("running") is True
    assert helper.is_running_status("FINISHED") is False
    assert helper.is_running_status("CREATING") is False
    assert helper.is_running_status("ACTIVE") is False
    fleet = leftover_fleet()
    rows = [
        {
            "id": a["id"],
            "agentStatus": a.get("status") or "ACTIVE",
            "runStatus": a["runStatus"],
            "repos": [] if a.get("unbound") else [a.get("repo") or ""],
            "repo": "" if a.get("unbound") else a.get("repo") or "",
        }
        for a in fleet
    ]
    assert helper.count_running_for_repo(rows, STUDIO_REPO) == 0
    assert helper.count_running_for_repo(rows, OTHER_REPO) == 1
    launched: list[str] = []

    def fake_launch(repo: str, prompt: str, name: str = "") -> str:
        launched.append(repo)
        return "CLOUD_LAUNCH_OK id=bc-count\n"

    monkeypatch.setenv("GCS_CLOUD_REPO", STUDIO_REPO)
    monkeypatch.setenv("GCS_ROOT", str(REPO))
    monkeypatch.setenv("GCS_A2A_STATE", str(tmp_path / "a2a-state"))
    out = helper.director_mind_turn(
        seat="floor",
        mail=ACP_PING,
        rows=rows,
        launch=fake_launch,
    )
    assert out["running"] == 0
    assert out["execd"] is True
    assert launched == [STUDIO_REPO]
    assert LAUNCH_REL in str(out.get("script") or helper.LAUNCH_REL)


def test_at_eight_running_does_not_exec_launcher(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper = _load(HELPER_PY, "gcs_liv41_turn_exec_floor")
    launched: list[str] = []

    def fake_launch(repo: str, prompt: str, name: str = "") -> str:
        launched.append(repo)
        return "CLOUD_LAUNCH_OK id=bc-should-not\n"

    rows = [
        {
            "id": a["id"],
            "agentStatus": "ACTIVE",
            "runStatus": "RUNNING",
            "repos": [STUDIO_REPO],
            "repo": STUDIO_REPO,
        }
        for a in eight_running_fleet()
    ]
    monkeypatch.setenv("GCS_CLOUD_REPO", STUDIO_REPO)
    monkeypatch.setenv("GCS_ROOT", str(REPO))
    monkeypatch.setenv("GCS_A2A_STATE", str(tmp_path / "a2a-state"))
    out = helper.director_mind_turn(
        seat="floor",
        mail=ACP_PING,
        rows=rows,
        launch=fake_launch,
    )
    assert out["running"] == 8
    assert out["execd"] is False
    assert out["reason"] == "at-floor"
    assert launched == []


def test_mind_turn_under_floor_execs_real_launcher(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """process_once → grok turn → helper finds RUNNING < 8 → real launch script."""
    mind = _load(MIND_PY, "gcs_mind_liv41_turn_exec")
    state = tmp_path / "a2a-state"
    state.mkdir(parents=True, exist_ok=True)
    home = tmp_path / "home"
    home.mkdir()
    grok_log = tmp_path / "grok.argv.json"
    grok = _write_exec(
        tmp_path / "fake-bin" / "grok",
        "#!/usr/bin/env python3\n"
        "import json, os, subprocess, sys\n"
        "from pathlib import Path\n"
        f"log = Path({str(grok_log)!r})\n"
        "rows = json.loads(log.read_text()) if log.is_file() else []\n"
        "mail_file = sys.argv[sys.argv.index('--prompt-file') + 1]\n"
        "mail = Path(mail_file).read_text()\n"
        "root = Path(os.environ['GCS_ROOT'])\n"
        "helper = root / 'scripts' / 'directors' / 'liv41_turn_exec.py'\n"
        "seat = os.environ.get('GCS_DIRECTOR_SEAT', 'floor')\n"
        "proc = subprocess.run(\n"
        "    [sys.executable, str(helper), '--seat', seat, '--mail-file', mail_file],\n"
        "    cwd=str(root),\n"
        "    env=os.environ.copy(),\n"
        "    capture_output=True,\n"
        "    text=True,\n"
        "    timeout=30,\n"
        ")\n"
        "rows.append({\n"
        "    'argv': sys.argv[1:],\n"
        "    'mail': mail,\n"
        "    'helper_stdout': proc.stdout,\n"
        "    'helper_stderr': proc.stderr,\n"
        "    'helper_rc': proc.returncode,\n"
        "})\n"
        "log.write_text(json.dumps(rows))\n"
        "sys.stdout.write(proc.stdout or json.dumps({'ok': True}))\n"
        "raise SystemExit(0 if proc.returncode == 0 else proc.returncode)\n",
    )
    with MockCloudAPI(agents=leftover_fleet()) as api:
        env = _cloud_env(home, api.base, GCS_A2A_STATE=str(state), GCS_DIRECTOR_SEAT="floor")
        _apply_cloud_env(monkeypatch, env)
        monkeypatch.setenv("GROK_BIN", str(grok))
        monkeypatch.setenv("GCS_MIND_TURN_TIMEOUT", "40")
        monkeypatch.setattr(mind, "STATE_DIR", state)
        monkeypatch.setattr(mind, "ROOT", REPO)
        _append_inbox(state, "floor", "task-liv41-turn-exec", ACP_PING)
        result = mind.process_once("floor")
        posts = list(api.posts)
        gets = list(api.gets)
    assert result["consumed"] == 1, result
    grok_rows = json.loads(grok_log.read_text(encoding="utf-8"))
    helper_out = grok_rows[0]["helper_stdout"]
    helper_err = grok_rows[0]["helper_stderr"]
    blob = helper_out + helper_err
    assert grok_rows[0]["helper_rc"] == 0, blob
    assert "CLOUD_LAUNCH_OK" in blob, blob
    assert "bc-liv41-turn-exec" in blob or "execd" in blob.lower() or '"execd": true' in blob.lower()
    creates = [p for p in posts if p["path"] == "/v1/agents"]
    assert len(creates) == 1, posts
    body = creates[0]["body"] or {}
    assert body["model"]["id"] == "grok-4.6"
    params = {(p["id"], p["value"]) for p in body["model"]["params"]}
    assert ("effort", "xhigh") in params
    assert ("fast", "false") in params
    assert body["repos"] == [{"url": STUDIO_REPO, "startingRef": "main"}]
    assert body.get("name") == TURN_NAME
    assert RESERVED_NAME not in json.dumps(body)
    assert "donald" not in str(body.get("name") or "").lower()
    assert "orchestrator" not in str(body.get("name") or "").lower()
    assert FAKE_KEY not in blob
    assert FAKE_KEY not in json.dumps(body)
    assert PRIVATE_GAME not in blob
    assert any(path == "/v1/agents" or path.startswith("/v1/agents?") for path in gets)
    assert any("/runs/" in path for path in gets)
    prompt = str(body.get("prompt") or body.get("prompt", {}))
    if isinstance(body.get("prompt"), dict):
        prompt = str(body["prompt"].get("text") or "")
    assert "Bot CloudAgent" in prompt or "Never Bot" in prompt
    assert "ACP_PING" not in prompt
    argv = grok_rows[0]["argv"]
    assert "--prompt-file" in argv
    assert "-p" not in argv
    assert "--model" in argv and "grok-4.6" in argv
    assert "--reasoning-effort" in argv and "xhigh" in argv


def test_donald_cron_and_bot_seats_do_not_exec_launcher(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper = _load(HELPER_PY, "gcs_liv41_turn_exec_donald")
    mind = _load(MIND_PY, "gcs_mind_liv41_donald")
    ticker = _load(TICKER_PY, "gcs_ticker_liv41")
    state = tmp_path / "a2a-state"
    state.mkdir(parents=True, exist_ok=True)
    home = tmp_path / "home"
    home.mkdir()
    launched: list[str] = []

    def fake_launch(repo: str, prompt: str, name: str = "") -> str:
        launched.append(name or repo)
        return "CLOUD_LAUNCH_OK id=bc-donald\n"

    monkeypatch.setenv("GCS_CLOUD_REPO", STUDIO_REPO)
    monkeypatch.setenv("GCS_ROOT", str(REPO))
    monkeypatch.setenv("GCS_A2A_STATE", str(state))
    monkeypatch.setattr(mind, "STATE_DIR", state)
    monkeypatch.setattr(mind, "ROOT", REPO)
    monkeypatch.setattr(ticker, "STATE_DIR", state)
    monkeypatch.setattr(ticker, "ROOT", REPO)

    donald = helper.director_mind_turn(
        seat="donald",
        mail=ACP_PING,
        rows=[],
        launch=fake_launch,
    )
    orch = helper.director_mind_turn(
        seat="orchestrator",
        mail=ACP_PING,
        rows=[],
        launch=fake_launch,
    )
    assert donald["execd"] is False
    assert "skip" in str(donald.get("reason") or "").lower()
    assert orch["execd"] is False
    assert launched == []

    bot = helper.director_mind_turn(
        seat="floor",
        mail=ACP_PING,
        rows=[],
        launch=fake_launch,
        name="donald",
    )
    reserved = helper.director_mind_turn(
        seat="floor",
        mail=ACP_PING,
        rows=[],
        launch=fake_launch,
        name=RESERVED_NAME,
    )
    assert bot["execd"] is False
    assert reserved["execd"] is False
    assert launched == []
    assert helper.is_bot_cloudagent_name("donald") is True
    assert helper.is_bot_cloudagent_name("orchestrator") is True
    assert helper.is_forbidden_spawn_name(RESERVED_NAME) is True
    assert helper.is_forbidden_spawn_name(TURN_NAME) is False

    _append_inbox(state, "donald", "task-donald", ACP_PING)
    result = mind.process_once("donald")
    assert result["consumed"] == 0
    assert "skip" in str(result.get("reason") or "").lower()

    with MockCloudAPI(agents=leftover_fleet()) as api:
        env = _cloud_env(home, api.base, GCS_A2A_STATE=str(state))
        _apply_cloud_env(monkeypatch, env)
        n = ticker.tick_once(seats=("floor", "ops"))
        posts = list(api.posts)
    assert n == 2
    assert posts == []
    inbox = (state / "floor" / "inbox.jsonl").read_text(encoding="utf-8")
    assert "ACP_PING" in inbox
    clock = CLOCK_SH.read_text(encoding="utf-8")
    ticker_src = TICKER_PY.read_text(encoding="utf-8")
    assert "enqueue_continue" in clock
    subprocess_lines = [line for line in ticker_src.splitlines() if "subprocess" in line]
    assert all(LAUNCH_REL not in line for line in subprocess_lines)
    assert PRIVATE_GAME not in helper.FILL_PROMPT
    assert "Bot CloudAgent" in helper.FILL_PROMPT
    assert "grok-4.6" in helper.FILL_PROMPT
    assert "xhigh" in helper.FILL_PROMPT
    assert "fast=false" in helper.FILL_PROMPT.replace(" ", "")
