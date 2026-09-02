"""LIV-82 remaining vs OPEN GitHub #109: stamp Living Sky AFTER a real Extra High launch.

#109 owns hive stamps after each mind turn (`linear_hive.py` + mind.py hook).
This slice must not twin that hook. Unique remaining:

- Stamp only after CLOUD_LAUNCH_OK or a dump that records it.
- Fail closed with LINEAR_STAMP_FAIL when LINEAR_API_KEY is unset.
- Still record local evidence. Do not fake Linear MCP save_comment.
- Living Sky (linear.app/livingsky, team LIV) only. NEVER Black Swan.
- Default issue LIV-69; optional LIV-63 / LIV-82 / LIV-96.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from test_cloud_launch import (
    FAKE_KEY,
    LAUNCH,
    MockCursorAPI,
    _run,
    _script_env,
)

REPO = Path(__file__).resolve().parents[1]
STAMP = REPO / "scripts" / "studio" / "linear_stamp_after_launch_beat1740.sh"
SPAWN_WAITER = REPO / "scripts" / "cloud" / "spawn-waiter.sh"
SDK_LAUNCH = REPO / "scripts" / "cloud" / "sdk" / "launch.ts"
SHIP_GATE_WF = REPO / ".github" / "workflows" / "liv82-stamp-after-launch-beat1740.yml"
MIND_PY = REPO / "scripts" / "directors" / "mind.py"
LINEAR_HIVE = REPO / "scripts" / "directors" / "linear_hive.py"
LIV_STAMP = REPO / "scripts" / "studio" / "linear" / "liv_stamp.py"

LIVING_SKY_HOST = "linear.app/livingsky"
LIVING_SKY_URL_KEY = "livingsky"
LIVING_SKY_TEAM = "LIV"
DEFAULT_ISSUE = "LIV-69"
OPTIONAL_ISSUES = ("LIV-63", "LIV-82", "LIV-96")
FAKE_LINEAR = "lin_" + "test" + ("0" * 24)


def _stamp_env(tmp_path: Path, **extra: str) -> dict[str, str]:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(tmp_path),
        "TMPDIR": str(tmp_path),
        "GCS_ROOT": str(REPO),
        "GCS_A2A_STATE": str(tmp_path / "a2a-state"),
        "LC_ALL": "C",
    }
    env.update(extra)
    return env


def _run_stamp(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(STAMP), *args],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env=env,
        timeout=20,
    )


def _evidence_rows(tmp_path: Path) -> list[dict[str, Any]]:
    root = tmp_path / "a2a-state" / "linear-stamps"
    rows: list[dict[str, Any]] = []
    if not root.is_dir():
        return rows
    for path in sorted(root.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


class FakeLinearHTTP:
    """In-process Linear GraphQL stand-in. Never the public network."""

    def __init__(
        self,
        *,
        url_key: str = LIVING_SKY_URL_KEY,
        org_name: str = "Living Sky",
        team_key: str = LIVING_SKY_TEAM,
        team_name: str = "Livingsky",
        issue_url_host: str = LIVING_SKY_HOST,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self.auth_headers: list[str] = []
        self.url_key = url_key
        self.org_name = org_name
        self.team_key = team_key
        self.team_name = team_name
        self.issue_url_host = issue_url_host
        self.comment_ids: list[str] = []
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.base = ""

    def __enter__(self) -> "FakeLinearHTTP":
        api = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: Any) -> None:
                return

            def do_POST(self) -> None:
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n).decode("utf-8") if n else "{}"
                api.auth_headers.append(self.headers.get("Authorization") or "")
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    payload = {"raw": raw}
                api.calls.append(payload)
                query = str(payload.get("query") or "")
                variables = payload.get("variables") if isinstance(payload.get("variables"), dict) else {}
                body: dict[str, Any] = {"data": {}}
                if "organization" in query:
                    body["data"]["organization"] = {
                        "id": "org-liv",
                        "name": api.org_name,
                        "urlKey": api.url_key,
                    }
                if "issue(" in query or "issue " in query:
                    ident = str(variables.get("id") or DEFAULT_ISSUE)
                    body["data"]["issue"] = {
                        "id": f"uuid-{ident}",
                        "identifier": ident,
                        "url": f"https://{api.issue_url_host}/issue/{ident}",
                        "title": ident,
                        "team": {
                            "id": "team-liv-uuid",
                            "key": api.team_key,
                            "name": api.team_name,
                        },
                    }
                if "commentCreate" in query:
                    ident = "comment-" + str(len(api.comment_ids) + 1)
                    api.comment_ids.append(ident)
                    input_body = variables.get("input") if isinstance(variables.get("input"), dict) else {}
                    body["data"]["commentCreate"] = {
                        "success": True,
                        "comment": {
                            "id": ident,
                            "url": f"https://{api.issue_url_host}/comment/{ident}",
                            "body": str(input_body.get("body") or ""),
                        },
                    }
                blob = json.dumps(body).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(blob)))
                self.end_headers()
                self.wfile.write(blob)

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self._httpd.server_address[1]}/graphql"
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)


def test_stamp_script_exists_and_is_executable() -> None:
    assert STAMP.is_file(), f"missing {STAMP.relative_to(REPO)}"
    mode = STAMP.stat().st_mode
    assert mode & stat.S_IXUSR, "stamp script must be executable"


def test_does_not_twin_pr109_mind_turn_hive() -> None:
    """Unique remaining: do not land #109's every-turn hive files or mind hook."""
    assert not LINEAR_HIVE.exists()
    assert not LIV_STAMP.exists()
    mind = MIND_PY.read_text(encoding="utf-8")
    assert "linear_hive" not in mind
    assert "linear_stamp_after_launch" not in mind
    assert "after_mind_turn" not in mind
    stamp = STAMP.read_text(encoding="utf-8")
    assert "CLOUD_LAUNCH_OK" in stamp
    assert "LIV-69" in stamp
    assert "livingsky" in stamp.lower() or "Living Sky" in stamp
    assert "black swan" in stamp.lower() or "Black Swan" in stamp


def test_spawn_waiter_wires_stamp_hook() -> None:
    waiter = SPAWN_WAITER.read_text(encoding="utf-8")
    launch = LAUNCH.read_text(encoding="utf-8")
    assert "linear_stamp_after_launch_beat1740.sh" in waiter
    assert "linear_stamp_after_launch_beat1740.sh" in launch or "LINEAR_STAMP" in launch or "stamp" in waiter.lower()
    assert "spawn-waiter" in waiter


def test_unique_github_ship_gate_is_not_empty_checks() -> None:
    """Donald HOLD: missing GitHub checks are not ship-gate. Unique vs LIV-94 twins."""
    assert SHIP_GATE_WF.is_file(), f"missing {SHIP_GATE_WF.relative_to(REPO)}"
    text = SHIP_GATE_WF.read_text(encoding="utf-8")
    assert "pytest -q" in text
    assert "secret_scan" in text
    assert "install.sh" in text
    assert "GCS_BOT_BIND_OPTIONAL" in text
    assert "submodules" in text
    assert "fetch-depth" in text
    assert "[1-9][0-9]* passed" in text or "N passed" in text
    assert "secret_scan=clean" in text
    assert "runs-on:" in text
    assert "echo skip" not in text.lower()
    # Do not remint #92/#121 ship-gate.yml or #109 ci.yml on this unique remaining slice.
    assert SHIP_GATE_WF.name != "ship-gate.yml"
    assert SHIP_GATE_WF.name != "ci.yml"


def test_bare_id_without_launch_evidence_is_fail(tmp_path: Path) -> None:
    proc = _run_stamp(["--id", "bc-chatter"], _stamp_env(tmp_path))
    blob = proc.stdout + proc.stderr
    assert proc.returncode != 0
    assert "LINEAR_STAMP_FAIL" in blob
    assert "LINEAR_STAMP_OK" not in blob
    rows = _evidence_rows(tmp_path)
    assert rows, "fail-closed must still record local evidence"
    assert rows[-1].get("save_comment") is False
    assert rows[-1].get("graphql") is False
    assert rows[-1].get("reason") in {"no-launch", "no-evidence", "chatter"}


def test_evidence_dump_without_cloud_launch_ok_is_fail(tmp_path: Path) -> None:
    dump = tmp_path / "not-a-launch.txt"
    dump.write_text("mind chatter LINEAR_STAMP pretend\nid=bc-nope\n", encoding="utf-8")
    proc = _run_stamp(["--evidence", str(dump)], _stamp_env(tmp_path))
    blob = proc.stdout + proc.stderr
    assert proc.returncode != 0
    assert "LINEAR_STAMP_FAIL" in blob
    assert "LINEAR_STAMP_OK" not in blob
    rows = _evidence_rows(tmp_path)
    assert rows
    assert rows[-1].get("save_comment") is False


def test_no_key_fail_closed_records_evidence_no_fake_save_comment(tmp_path: Path) -> None:
    dump = tmp_path / "launch.ok"
    dump.write_text("CLOUD_LAUNCH_OK\nid=bc-real\nrun=run-real\n", encoding="utf-8")
    env = _stamp_env(tmp_path)
    env.pop("LINEAR_API_KEY", None)
    proc = _run_stamp(["--evidence", str(dump)], env)
    blob = proc.stdout + proc.stderr
    assert "LINEAR_STAMP_ATTEMPT" in blob
    assert "LINEAR_STAMP_FAIL" in blob
    assert "LINEAR_STAMP_OK" not in blob
    assert proc.returncode != 0
    assert FAKE_LINEAR not in blob
    rows = _evidence_rows(tmp_path)
    assert rows
    rec = rows[-1]
    assert rec.get("save_comment") is False
    assert rec.get("graphql") is False
    assert rec.get("reason") == "no-key"
    assert rec.get("id") == "bc-real"
    assert DEFAULT_ISSUE in str(rec.get("issues") or rec.get("issue") or "")
    stamp_src = STAMP.read_text(encoding="utf-8")
    assert "save_comment" not in stamp_src or "do not fake" in stamp_src.lower() or "not fake" in stamp_src.lower()


def test_living_sky_comment_create_on_liv69(tmp_path: Path) -> None:
    dump = tmp_path / "launch.ok"
    dump.write_text("CLOUD_LAUNCH_OK id=bc-liv69 run=run-1\nid=bc-liv69\nrun=run-1\n", encoding="utf-8")
    with FakeLinearHTTP() as api:
        env = _stamp_env(
            tmp_path,
            GCS_LINEAR_API=api.base,
        )
        env["LINEAR_API_KEY"] = FAKE_LINEAR
        proc = _run_stamp(["--evidence", str(dump)], env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "LINEAR_STAMP_ATTEMPT" in blob
    assert "LINEAR_STAMP_OK" in blob
    assert "LINEAR_STAMP_FAIL" not in blob
    assert FAKE_LINEAR not in blob
    assert DEFAULT_ISSUE in blob
    assert any("commentCreate" in str(c.get("query") or "") for c in api.calls)
    assert any(
        DEFAULT_ISSUE in json.dumps(c)
        or str((c.get("variables") or {}).get("id") or "") == DEFAULT_ISSUE
        for c in api.calls
    )
    rows = _evidence_rows(tmp_path)
    assert rows
    rec = rows[-1]
    assert rec.get("graphql") is True
    assert rec.get("save_comment") is False
    assert rec.get("status") in {"ok", "success"}
    bodies = [
        str(((c.get("variables") or {}).get("input") or {}).get("body") or "")
        for c in api.calls
        if "commentCreate" in str(c.get("query") or "")
    ]
    assert bodies
    assert any("CLOUD_LAUNCH_OK" in b or "Extra High" in b or "launch" in b.lower() for b in bodies)
    assert all("mind turn" not in b.lower() for b in bodies)
    assert api.auth_headers, "GraphQL must send Authorization"
    for header in api.auth_headers:
        assert header == FAKE_LINEAR, header
        assert not header.lower().startswith("bearer ")


def test_optional_issues_liv63_82_96(tmp_path: Path) -> None:
    dump = tmp_path / "launch.ok"
    dump.write_text("CLOUD_LAUNCH_OK\nid=bc-opt\n", encoding="utf-8")
    issues = ",".join((DEFAULT_ISSUE,) + OPTIONAL_ISSUES)
    with FakeLinearHTTP() as api:
        env = _stamp_env(tmp_path, GCS_LINEAR_API=api.base, GCS_LINEAR_STAMP_ISSUES=issues)
        env["LINEAR_API_KEY"] = FAKE_LINEAR
        proc = _run_stamp(["--evidence", str(dump)], env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    queried = [
        str((c.get("variables") or {}).get("id") or "")
        for c in api.calls
        if "issue" in str(c.get("query") or "").lower()
    ]
    for ident in (DEFAULT_ISSUE,) + OPTIONAL_ISSUES:
        assert ident in queried or ident in blob
    assert len(api.comment_ids) >= 4


def test_refuses_black_swan_no_comment(tmp_path: Path) -> None:
    dump = tmp_path / "launch.ok"
    dump.write_text("CLOUD_LAUNCH_OK\nid=bc-bsm\n", encoding="utf-8")
    with FakeLinearHTTP(
        url_key="blackswanmoney",
        org_name="Black Swan Money",
        team_key="BSM",
        team_name="Black Swan",
        issue_url_host="linear.app/blackswanmoney",
    ) as api:
        env = _stamp_env(tmp_path, GCS_LINEAR_API=api.base)
        env["LINEAR_API_KEY"] = FAKE_LINEAR
        proc = _run_stamp(["--evidence", str(dump)], env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode != 0
    assert "LINEAR_STAMP_FAIL" in blob
    assert "LINEAR_STAMP_OK" not in blob
    assert not any("commentCreate" in str(c.get("query") or "") for c in api.calls)
    rows = _evidence_rows(tmp_path)
    assert rows
    assert rows[-1].get("save_comment") is False
    assert rows[-1].get("reason") in {"not-living-sky", "black-swan", "refused"}


def test_never_prints_linear_or_cursor_keys(tmp_path: Path) -> None:
    dump = tmp_path / "launch.ok"
    dump.write_text("CLOUD_LAUNCH_OK\nid=bc-key\n", encoding="utf-8")
    with FakeLinearHTTP() as api:
        env = _stamp_env(tmp_path, GCS_LINEAR_API=api.base)
        env["LINEAR_API_KEY"] = FAKE_LINEAR
        env["CURSOR_API_KEY"] = FAKE_KEY
        proc = _run_stamp(["--evidence", str(dump), "--source", "launch"], env)
    blob = proc.stdout + proc.stderr
    assert "LINEAR_STAMP_ATTEMPT" in blob
    assert "LINEAR_STAMP_OK" in blob or "LINEAR_STAMP_FAIL" in blob
    assert FAKE_LINEAR not in blob
    assert FAKE_KEY not in blob
    for rec in _evidence_rows(tmp_path):
        dumped = json.dumps(rec)
        assert FAKE_LINEAR not in dumped
        assert FAKE_KEY not in dumped


def test_launch_ok_prints_stamp_attempt(tmp_path: Path) -> None:
    with MockCursorAPI(create_http=201) as api:
        env = _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY)
        env["GCS_A2A_STATE"] = str(tmp_path / "a2a-state")
        env.pop("LINEAR_API_KEY", None)
        proc = _run(
            LAUNCH,
            ["--name", "gcs-liv82-stamp", "Implement LIV-82 remaining. Open a PR."],
            env,
        )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "CLOUD_LAUNCH_OK" in proc.stdout
    assert "LINEAR_STAMP_ATTEMPT" in blob
    assert "LINEAR_STAMP_FAIL" in blob
    assert FAKE_KEY not in blob
    rows = _evidence_rows(tmp_path)
    assert rows
    assert rows[-1].get("save_comment") is False
    assert rows[-1].get("reason") == "no-key"


def test_launch_err_does_not_stamp(tmp_path: Path) -> None:
    with MockCursorAPI() as api:
        env = _script_env(tmp_path, api.base)
        env["GCS_A2A_STATE"] = str(tmp_path / "a2a-state")
        proc = _run(LAUNCH, ["no-key"], env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode != 0
    assert "CLOUD_LAUNCH_ERR" in proc.stdout
    assert "LINEAR_STAMP_ATTEMPT" not in blob
    assert "LINEAR_STAMP_OK" not in blob
    assert _evidence_rows(tmp_path) == []


def test_sdk_launch_always_invokes_spawn_waiter_for_stamp() -> None:
    """Canonical SDK launch must still hit spawn-waiter (stamp) when waiter=0."""
    src = SDK_LAUNCH.read_text(encoding="utf-8")
    assert "spawn-waiter.sh" in src
    assert "spawnSync" in src
    assert "stdio: \"ignore\"" not in src
    assert "if (raw === \"0\"" not in src
    assert "CLOUD_LAUNCH_OK" in src


def test_loads_linear_key_from_studio_env(tmp_path: Path) -> None:
    dump = tmp_path / "launch.ok"
    dump.write_text("CLOUD_LAUNCH_OK\nid=bc-env\n", encoding="utf-8")
    state = tmp_path / "a2a-state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "studio.env").write_text("LINEAR_API_KEY=" + FAKE_LINEAR + "\n", encoding="utf-8")
    with FakeLinearHTTP() as api:
        env = _stamp_env(tmp_path, GCS_LINEAR_API=api.base)
        env.pop("LINEAR_API_KEY", None)
        proc = _run_stamp(["--evidence", str(dump)], env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "LINEAR_STAMP_OK" in blob
    assert FAKE_LINEAR not in blob
    assert api.auth_headers
    assert api.auth_headers[0] == FAKE_LINEAR


def test_spawn_waiter_skipped_still_attempts_stamp(tmp_path: Path) -> None:
    env = _stamp_env(tmp_path, GCS_SPAWN_WAITER="0")
    proc = subprocess.run(
        ["bash", str(SPAWN_WAITER), "--id", "bc-wait", "--run", "run-wait", "--name", "liv82"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env=env,
        timeout=20,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "CLOUD_WAITER_SKIPPED" in blob
    assert "LINEAR_STAMP_ATTEMPT" in blob
    assert "LINEAR_STAMP_FAIL" in blob
    rows = _evidence_rows(tmp_path)
    assert rows
    assert rows[-1].get("id") == "bc-wait"
