"""Extra High launch: mock REST, require GCS_CLOUD_REPO, never print keys."""
from __future__ import annotations

import base64
import json
import os
import re
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
FOLLOWUP = CLOUD / "followup.sh"
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
    run_status_by_id: dict[str, str] = field(default_factory=dict)
    run_model_by_id: dict[str, Any] = field(default_factory=dict)
    followup_http: int = 201
    followup_body: dict[str, Any] | None = None
    posts: list[dict[str, Any]] = field(default_factory=list)
    gets: list[str] = field(default_factory=list)
    run_not_found_ids: set[str] = field(default_factory=set)
    auth_users: list[str] = field(default_factory=list)
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
                    self._send(200, {"items": api.list_items})
                    return
                if len(parts) == 3 and parts[:2] == ["v1", "agents"]:
                    agent_id = parts[2]
                    listed = next(
                        (item for item in api.list_items if str(item.get("id") or "") == agent_id),
                        None,
                    )
                    payload: dict[str, Any] = {
                        "id": agent_id,
                        "name": (listed or {}).get("name") or "mock-agent",
                        "status": (listed or {}).get("status") or "ACTIVE",
                        "url": (listed or {}).get("url")
                        or f"https://cursor.com/agents/{agent_id}",
                        "latestRunId": (listed or {}).get("latestRunId") or "run-mock",
                    }
                    if listed and listed.get("repos"):
                        payload["repos"] = listed["repos"]
                    self._send(200, payload)
                    return
                if len(parts) == 5 and parts[:2] == ["v1", "agents"] and parts[3] == "runs":
                    run_id = parts[4]
                    if run_id in api.run_not_found_ids:
                        self._send(404, {"error": "not_found"})
                        return
                    if run_id in api.run_status_by_id:
                        status = api.run_status_by_id[run_id]
                    else:
                        seq = api.run_statuses or ["RUNNING"]
                        if api._run_i < len(seq):
                            status = seq[api._run_i]
                            api._run_i += 1
                        else:
                            status = seq[-1]
                    body: dict[str, Any] = {
                        "id": run_id,
                        "agentId": parts[2],
                        "status": status,
                    }
                    if run_id in api.run_model_by_id:
                        body["model"] = api.run_model_by_id[run_id]
                    self._send(200, body)
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
                    payload = api.followup_body or {
                        "run": {
                            "id": "run-followup",
                            "agentId": parts[2],
                            "status": "CREATING",
                        }
                    }
                    self._send(api.followup_http, payload)
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


# Env values that must not create or send. Unset and exact grok-4.6 remain OK.
NON_GROK_CURSOR_CLOUD_MODELS = (
    "auto",
    "auto-smart",
    "claude-opus-5",
    "claude-opus-4.6",
    "opus",
    "claude-4-sonnet",
    "sonnet",
    "gemini-2.5-pro",
    "gemini",
    "composer",
    "composer-2",
    "gpt-5",
    "cursor-grok-4.6-xhigh",
    "claude-4.5-sonnet",
    "gemini-3.1-pro",
)


def _ts_fn_body(src: str, name: str) -> str:
    start = -1
    token = ""
    for candidate in (f"export function {name}", f"export async function {name}"):
        found = src.find(candidate)
        if found != -1 and (start == -1 or found < start):
            start = found
            token = candidate
    if start == -1:
        raise ValueError(f"export function {name} not found")
    rest = src[start + len(token) :]
    nxt_rel: int | None = None
    for marker in ("\nexport function ", "\nexport async function "):
        found = rest.find(marker)
        if found != -1 and (nxt_rel is None or found < nxt_rel):
            nxt_rel = found
    end = None if nxt_rel is None else start + len(token) + nxt_rel
    return src[start:end]


def test_extra_high_model_is_hard_pinned_not_env_overridable() -> None:
    common = (CLOUD / "sdk" / "common.ts").read_text(encoding="utf-8")
    launch = (CLOUD / "sdk" / "launch.ts").read_text(encoding="utf-8")
    followup = (CLOUD / "sdk" / "followup.ts").read_text(encoding="utf-8")
    body = _ts_fn_body(common, "extraHighModel")
    send_body = _ts_fn_body(common, "sendPinned")
    assert "function extraHighModel" in common
    assert 'id: "grok-4.6"' in common or "id: EXTRA_HIGH_MODEL_ID" in common
    assert "CURSOR_CLOUD_MODEL" not in body
    assert "CURSOR_CLOUD_EFFORT" not in body
    assert "CURSOR_CLOUD_EFFORT" not in common
    assert "process.env" not in body
    assert "envFirst" not in body
    assert "xhigh" in body
    assert '"false"' in body or "value: \"false\"" in body
    assert "extraHighModel()" in launch
    assert "isExtraHighModelId" in common or "createModelRejected" in common
    assert "createModelRejected" in launch or "isExtraHighModelId" in launch
    assert "requirePinnedCloudModelEnv" in common
    assert "requirePinnedCloudModelEnv" in send_body
    assert "requirePinnedCloudModelEnv" in launch
    assert "requirePinnedCloudModelEnv" in followup


def test_sdk_send_pins_extra_high_model_on_first_run_and_followup() -> None:
    """Unpinned agent.send(prompt) lets Auto pick Claude/Gemini (Jay LIV-67)."""
    launch = (CLOUD / "sdk" / "launch.ts").read_text(encoding="utf-8")
    followup = (CLOUD / "sdk" / "followup.ts").read_text(encoding="utf-8")
    common = (CLOUD / "sdk" / "common.ts").read_text(encoding="utf-8")
    assert "await agent.send(prompt);" not in launch
    assert "await agent.send(prompt);" not in followup
    assert "sendPinned(" in launch
    assert "sendPinned(" in followup
    assert "sendPinned" in common
    assert "return agent.send(prompt, { model });" in common
    assert "extraHighModel()" in common
    assert "agent.send.length < 2" not in common
    assert "createModelRejected(run.model)" in launch
    assert "createModelRejected(run.model)" in followup
    extra = _ts_fn_body(common, "extraHighModel")
    assert "CURSOR_CLOUD_MODEL" not in extra
    assert "CURSOR_CLOUD_EFFORT" not in extra
    assert "CURSOR_CLOUD_EFFORT" not in common
    assert "requirePinnedCloudModelEnv()" in common
    assert "requirePinnedCloudModelEnv()" in launch
    assert "requirePinnedCloudModelEnv()" in followup


def _pin_cli(
    monkeypatch: pytest.MonkeyPatch, *argv: str, **env: str
) -> subprocess.CompletedProcess[str]:
    monkeypatch.setenv("CLOUD_PROMPT_TEXT", "keep going")
    monkeypatch.setenv("CLOUD_AGENT_NAME", "pin-test")
    monkeypatch.setenv("GCS_CLOUD_REPO", EXAMPLE_REPO)
    monkeypatch.setenv("GCS_CLOUD_REF", "main")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return subprocess.run(
        ["python3", str(CLOUD / "extra_high_model.py"), *argv],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_extra_high_pin_cli_rejects_non_grok_env_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail closed: non-grok CURSOR_CLOUD_MODEL must not emit a create/send body."""
    monkeypatch.setenv("CURSOR_CLOUD_EFFORT", "low")
    for cmd in ("launch-body", "followup-body", "assert-env"):
        proc = _pin_cli(monkeypatch, cmd, CURSOR_CLOUD_MODEL="claude-4-sonnet")
        assert proc.returncode != 0, cmd + proc.stdout + proc.stderr
        assert "CURSOR_CLOUD_MODEL" in proc.stderr or "claude-4-sonnet" in proc.stderr
        if proc.stdout.strip():
            with pytest.raises(json.JSONDecodeError):
                json.loads(proc.stdout)


def test_extra_high_pin_cli_allows_unset_or_grok_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CURSOR_CLOUD_MODEL", raising=False)
    monkeypatch.setenv("CURSOR_CLOUD_EFFORT", "low")
    unset_launch = _pin_cli(monkeypatch, "launch-body")
    assert unset_launch.returncode == 0, unset_launch.stderr
    unset_body = json.loads(unset_launch.stdout)
    assert unset_body["model"]["id"] == "grok-4.6"
    params = {(p["id"], p["value"]) for p in unset_body["model"]["params"]}
    assert ("effort", "xhigh") in params
    assert ("fast", "false") in params
    grok = _pin_cli(monkeypatch, "followup-body", CURSOR_CLOUD_MODEL="grok-4.6")
    assert grok.returncode == 0, grok.stderr
    follow_body = json.loads(grok.stdout)
    assert follow_body["model"]["id"] == "grok-4.6"
    assert _pin_cli(monkeypatch, "assert-env").returncode == 0
    assert _pin_cli(monkeypatch, "assert-env", CURSOR_CLOUD_MODEL="grok-4.6").returncode == 0


def test_launch_fail_closed_when_create_returns_non_grok_model(tmp_path: Path) -> None:
    wrong = {
        "agent": {
            "id": "bc-sonnet",
            "name": "wrong-model",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-sonnet",
            "latestRunId": "run-sonnet",
            "model": {"id": "claude-4-sonnet"},
        },
        "run": {
            "id": "run-sonnet",
            "agentId": "bc-sonnet",
            "status": "CREATING",
            "model": {"id": "claude-4-sonnet"},
        },
        "model": {"id": "claude-4-sonnet"},
    }
    with MockCursorAPI(create_http=201, create_body=wrong) as api:
        proc = _run(
            LAUNCH,
            ["--name", "should-reject", "Implement X. Open a PR."],
            _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY),
        )
    assert proc.returncode != 0
    assert "CLOUD_LAUNCH_ERR" in proc.stdout
    assert "CLOUD_LAUNCH_OK" not in proc.stdout
    assert FAKE_KEY not in proc.stdout + proc.stderr
    assert api.posts, "create still happens; fail-closed is on the response model"


def test_launch_fail_closed_when_create_returns_auto_or_gemini(tmp_path: Path) -> None:
    for model_id in ("auto", "auto-smart", "gemini-2.5-pro"):
        body = {
            "agent": {
                "id": "bc-auto",
                "name": "auto-pick",
                "status": "ACTIVE",
                "url": "https://cursor.com/agents/bc-auto",
                "latestRunId": "run-auto",
            },
            "run": {"id": "run-auto", "agentId": "bc-auto", "status": "CREATING"},
            "model": {"id": model_id},
        }
        with MockCursorAPI(create_http=201, create_body=body) as api:
            proc = _run(
                LAUNCH,
                ["should-reject-auto"],
                _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY),
            )
        assert proc.returncode != 0, model_id
        assert "CLOUD_LAUNCH_ERR" in proc.stdout, model_id
        assert "CLOUD_LAUNCH_OK" not in proc.stdout, model_id


def test_launch_ok_when_create_returns_grok_46_or_dashboard_alias(tmp_path: Path) -> None:
    for model_id in ("grok-4.6", "cursor-grok-4.6-xhigh"):
        body = {
            "agent": {
                "id": "bc-grok",
                "name": "ok-model",
                "status": "ACTIVE",
                "url": "https://cursor.com/agents/bc-grok",
                "latestRunId": "run-grok",
                "model": {"id": model_id},
            },
            "run": {
                "id": "run-grok",
                "agentId": "bc-grok",
                "status": "CREATING",
                "model": {"id": model_id},
            },
        }
        with MockCursorAPI(create_http=201, create_body=body) as api:
            proc = _run(
                LAUNCH,
                ["--name", "ok-model", "Implement X. Open a PR."],
                _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY),
            )
        assert proc.returncode == 0, proc.stdout + proc.stderr + model_id
        assert "CLOUD_LAUNCH_OK" in proc.stdout
        assert "CLOUD_LAUNCH_ERR" not in proc.stdout


def test_launch_ok_when_create_omits_model(tmp_path: Path) -> None:
    """API v1 agent/run objects often omit model; request pin is still grok-4.6."""
    with MockCursorAPI(create_http=201) as api:
        proc = _run(
            LAUNCH,
            ["Implement the assigned outcome. Open a PR."],
            _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY),
        )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "CLOUD_LAUNCH_OK" in proc.stdout
    body = api.posts[0]["body"]
    assert body["model"]["id"] == "grok-4.6"


def test_followup_posts_pinned_extra_high_model(tmp_path: Path) -> None:
    with MockCursorAPI() as api:
        proc = _run(
            FOLLOWUP,
            ["bc-mock", "Keep the PR; fix the failing check."],
            _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY),
        )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "CLOUD_FOLLOWUP_OK" in proc.stdout
    runs = [p for p in api.posts if str(p.get("path") or "").endswith("/runs")]
    assert runs, api.posts
    body = runs[0]["body"]
    assert body["model"]["id"] == "grok-4.6"
    params = {(p["id"], p["value"]) for p in body["model"]["params"]}
    assert ("effort", "xhigh") in params
    assert ("fast", "false") in params
    assert FAKE_KEY not in proc.stdout + proc.stderr


def test_followup_fail_closed_when_run_returns_non_grok_model(tmp_path: Path) -> None:
    wrong = {
        "run": {
            "id": "run-followup",
            "agentId": "bc-mock",
            "status": "CREATING",
            "model": {"id": "claude-4-sonnet"},
        }
    }
    with MockCursorAPI(followup_http=201, followup_body=wrong) as api:
        proc = _run(
            FOLLOWUP,
            ["bc-mock", "continue"],
            _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY),
        )
    assert proc.returncode != 0
    assert "CLOUD_FOLLOWUP_ERR" in proc.stdout
    assert "CLOUD_FOLLOWUP_OK" not in proc.stdout
    assert FAKE_KEY not in proc.stdout + proc.stderr


# Real CloudAgent leaks (Donald LIV-67): unpinned send → Auto picked these.
LEAK_MODEL_IDS = ("auto", "claude-4.5-sonnet", "gemini-3.1-pro")
_UNPINNED_SEND_RE = re.compile(r"agent\.send\(\s*prompt\s*\)\s*(?!,)")
_CREATE_SEND_FOLLOWUP_PATHS = (
    CLOUD / "sdk" / "launch.ts",
    CLOUD / "sdk" / "followup.ts",
    CLOUD / "sdk" / "common.ts",
    CLOUD / "sdk" / "result.ts",
    CLOUD / "sdk" / "watch.ts",
    CLOUD / "sdk" / "collect.ts",
    CLOUD / "followup.sh",
    CLOUD / "followup-cloud-agent.sh",
    REPO / "scripts" / "launch-cloud-extra-high.sh",
)


def test_create_send_followup_path_has_no_unpinned_agent_send() -> None:
    """Unpinned agent.send(prompt) lets Auto pick claude-4.5-sonnet / gemini-3.1-pro."""
    common = (CLOUD / "sdk" / "common.ts").read_text(encoding="utf-8")
    launch = (CLOUD / "sdk" / "launch.ts").read_text(encoding="utf-8")
    followup = (CLOUD / "sdk" / "followup.ts").read_text(encoding="utf-8")
    followup_sh = FOLLOWUP.read_text(encoding="utf-8")
    extra = _ts_fn_body(common, "extraHighModel")
    for path in _CREATE_SEND_FOLLOWUP_PATHS:
        src = path.read_text(encoding="utf-8")
        hit = _UNPINNED_SEND_RE.search(src)
        assert hit is None, f"unpinned send in {path}: {hit.group(0) if hit else ''}"
    assert "sendPinned(" in launch
    assert "sendPinned(" in followup
    assert "return agent.send(prompt, { model });" in common
    assert "extraHighModel()" in launch
    assert "extraHighModel()" in followup
    assert "followup-body" in followup_sh
    assert "CURSOR_CLOUD_MODEL" not in extra
    assert "requirePinnedCloudModelEnv()" in common


def test_rest_followup_body_is_not_prompt_only(tmp_path: Path) -> None:
    """REST POST /runs must include extraHighModel, not {prompt} only."""
    script = CLOUD / "extra_high_model.py"
    proc = subprocess.run(
        ["python3", str(script), "followup-body"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=10,
        env={**os.environ, "CLOUD_PROMPT_TEXT": "continue the PR"},
    )
    assert proc.returncode == 0, proc.stderr
    body = json.loads(proc.stdout)
    assert "prompt" in body
    assert "model" in body, f"prompt-only followup body: {body}"
    assert set(body.keys()) != {"prompt"}
    assert body["model"]["id"] == "grok-4.6"
    with MockCursorAPI() as api:
        posted = _run(
            FOLLOWUP,
            ["bc-mock", "continue the PR"],
            _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY),
        )
    assert posted.returncode == 0, posted.stdout + posted.stderr
    runs = [p for p in api.posts if str(p.get("path") or "").endswith("/runs")]
    assert runs, api.posts
    rest_body = runs[0]["body"]
    assert "model" in rest_body
    assert set(rest_body.keys()) != {"prompt"}
    assert rest_body["model"]["id"] == "grok-4.6"


@pytest.mark.parametrize("model_id", LEAK_MODEL_IDS)
def test_launch_rejects_auto_sonnet_gemini_leak_ids(tmp_path: Path, model_id: str) -> None:
    body = {
        "agent": {
            "id": "bc-leak",
            "name": "leak",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-leak",
            "latestRunId": "run-leak",
            "model": {"id": model_id},
        },
        "run": {
            "id": "run-leak",
            "agentId": "bc-leak",
            "status": "CREATING",
            "model": {"id": model_id},
        },
        "model": {"id": model_id},
    }
    with MockCursorAPI(create_http=201, create_body=body) as api:
        proc = _run(
            LAUNCH,
            ["should-reject-leak"],
            _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY),
        )
    assert proc.returncode != 0, model_id
    assert "CLOUD_LAUNCH_ERR" in proc.stdout, model_id
    assert "CLOUD_LAUNCH_OK" not in proc.stdout, model_id


@pytest.mark.parametrize("model_id", LEAK_MODEL_IDS)
def test_followup_rejects_auto_sonnet_gemini_leak_ids(tmp_path: Path, model_id: str) -> None:
    wrong = {
        "run": {
            "id": "run-followup",
            "agentId": "bc-mock",
            "status": "CREATING",
            "model": {"id": model_id},
        }
    }
    with MockCursorAPI(followup_http=201, followup_body=wrong) as api:
        proc = _run(
            FOLLOWUP,
            ["bc-mock", "continue"],
            _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY),
        )
    assert proc.returncode != 0, model_id
    assert "CLOUD_FOLLOWUP_ERR" in proc.stdout, model_id
    assert "CLOUD_FOLLOWUP_OK" not in proc.stdout, model_id


@pytest.mark.parametrize("model_id", NON_GROK_CURSOR_CLOUD_MODELS)
def test_non_grok_cursor_cloud_model_cannot_create(tmp_path: Path, model_id: str) -> None:
    """Opus/Auto/Sonnet/Gemini/Composer env must not POST create."""
    with MockCursorAPI(create_http=201) as api:
        proc = _run(
            LAUNCH,
            ["--name", "must-not-launch", "Implement the assigned outcome. Open a PR."],
            _script_env(
                tmp_path,
                api.base,
                CURSOR_API_KEY=FAKE_KEY,
                CURSOR_CLOUD_MODEL=model_id,
            ),
        )
    assert proc.returncode != 0, model_id + proc.stdout + proc.stderr
    assert "CLOUD_LAUNCH_ERR" in proc.stdout, model_id
    assert "CLOUD_LAUNCH_OK" not in proc.stdout, model_id
    assert not api.posts, f"{model_id} still posted create: {api.posts}"
    assert FAKE_KEY not in proc.stdout + proc.stderr


@pytest.mark.parametrize(
    "model_id",
    ("auto", "claude-opus-5", "claude-4-sonnet", "claude-4.5-sonnet", "gemini-3.1-pro", "composer"),
)
def test_non_grok_cursor_cloud_model_cannot_send_followup(
    tmp_path: Path, model_id: str
) -> None:
    """Non-grok env must not POST follow-up /runs."""
    with MockCursorAPI() as api:
        proc = _run(
            FOLLOWUP,
            ["bc-mock", "Keep the PR; fix the failing check."],
            _script_env(
                tmp_path,
                api.base,
                CURSOR_API_KEY=FAKE_KEY,
                CURSOR_CLOUD_MODEL=model_id,
            ),
        )
    assert proc.returncode != 0, model_id + proc.stdout + proc.stderr
    assert "CLOUD_FOLLOWUP_ERR" in proc.stdout, model_id
    assert "CLOUD_FOLLOWUP_OK" not in proc.stdout, model_id
    assert not api.posts, f"{model_id} still posted send: {api.posts}"
    assert FAKE_KEY not in proc.stdout + proc.stderr


def test_cursor_cloud_model_grok_46_still_creates_and_sends(tmp_path: Path) -> None:
    with MockCursorAPI(create_http=201) as api:
        launched = _run(
            LAUNCH,
            ["--name", "grok-env-ok", "Implement the assigned outcome. Open a PR."],
            _script_env(
                tmp_path,
                api.base,
                CURSOR_API_KEY=FAKE_KEY,
                CURSOR_CLOUD_MODEL="grok-4.6",
            ),
        )
        followed = _run(
            FOLLOWUP,
            ["bc-mock", "Keep going."],
            _script_env(
                tmp_path,
                api.base,
                CURSOR_API_KEY=FAKE_KEY,
                CURSOR_CLOUD_MODEL="grok-4.6",
            ),
        )
    assert launched.returncode == 0, launched.stdout + launched.stderr
    assert "CLOUD_LAUNCH_OK" in launched.stdout
    assert followed.returncode == 0, followed.stdout + followed.stderr
    assert "CLOUD_FOLLOWUP_OK" in followed.stdout
    assert api.posts
    for item in api.posts:
        assert item["body"]["model"]["id"] == "grok-4.6"


def test_launch_and_followup_scripts_assert_cloud_model_env() -> None:
    launch = LAUNCH.read_text(encoding="utf-8")
    followup = FOLLOWUP.read_text(encoding="utf-8")
    assert "assert-env" in launch
    assert "assert-env" in followup
    assert "extra_high_model.py" in launch
    assert "extra_high_model.py" in followup
