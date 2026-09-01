"""LIV-94: empty GitHub checks are not ship-gate evidence.

GCS #41 / #47 / #27 are MERGEABLE (mergeable_state=clean) with
check_runs=[]. That is not pytest -q + secret_scan. GCS #62 already
added the pull_request Actions job and it ran; do not remint it.

Never Bot CloudAgent. Never print GH_TOKEN / GITHUB_TOKEN / CURSOR_API_KEY.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cloud"))
sys.path.insert(0, str(ROOT / "scripts" / "a2a"))

from fleet_ledger import notify_owner, notify_text  # noqa: E402
from ship_gate_evidence import (  # noqa: E402
    SHIP_GATE_EXAMPLE,
    ShipGateSnapshot,
    github_pr_ship_gate,
    is_ship_gate_check,
    is_ship_gate_evidence,
    parse_github_pull_url,
    resolve_ship_gate,
)

GCS41 = "https://github.com/atebites-hub/grok-cloud-studio/pull/41"
GCS47 = "https://github.com/atebites-hub/grok-cloud-studio/pull/47"
GCS27 = "https://github.com/atebites-hub/grok-cloud-studio/pull/27"
GCS62 = "https://github.com/atebites-hub/grok-cloud-studio/pull/62"
MERGE_READY = "ping QA (odd→qa-a, even→qa-b) MERGE_REQUEST"
FEATURE = ROOT / "tests" / "features" / "liv94_empty_checks_not_evidence.feature"
WAIT_TS = ROOT / "scripts" / "cloud" / "sdk" / "wait-notify.ts"
PR_CHECKS_TS = ROOT / "scripts" / "cloud" / "sdk" / "pr-checks.ts"
COLLECT_TS = ROOT / "scripts" / "cloud" / "sdk" / "collect.ts"
RESULT_TS = ROOT / "scripts" / "cloud" / "sdk" / "result.ts"
RESULT_SH = ROOT / "scripts" / "cloud" / "result-cloud-agent.sh"
LIST_TS = ROOT / "scripts" / "cloud" / "sdk" / "list.ts"
FAKE_TOKEN = "ghs_liv94_must_never_print_this_token"
FAKE_CURSOR_KEY = "test-cursor-api-key-liv94"


def _empty_mergeable(*, pr: str = GCS41) -> ShipGateSnapshot:
    """Observed shape of GCS #41 / #47 / #27: MERGEABLE, no checks."""
    return ShipGateSnapshot(
        pr_url=pr,
        mergeable_state="clean",
        head_sha="deadbeef",
        check_runs=(),
        statuses_total=0,
    )


def _ship_gate_ok_snapshot() -> ShipGateSnapshot:
    """Observed shape of GCS #62 after Actions ran."""
    return ShipGateSnapshot(
        pr_url=GCS62,
        mergeable_state="clean",
        head_sha="a03267939d6b4e68f66240b52a24d31419484ff1",
        check_runs=(
            {
                "name": "pytest -q and secret_scan",
                "status": "completed",
                "conclusion": "success",
            },
        ),
        statuses_total=0,
    )


def test_feature_file_states_liv94_law() -> None:
    text = FEATURE.read_text(encoding="utf-8")
    assert "empty GitHub checks are not ship-gate evidence" in text
    assert "mergeable_state=clean" in text
    assert "check_runs" in text
    assert ".venv/bin/pytest -q" in text
    assert "python3 scripts/secret_scan.py" in text
    assert "pull_request" in text
    assert "do not remint" in text or "must not clone" in text
    assert "MERGE_REQUEST" in text
    assert "Bot CloudAgent" not in text or "Never Bot CloudAgent" in text


def test_parse_github_pull_url_gcs_prs() -> None:
    assert parse_github_pull_url(GCS41) == ("atebites-hub", "grok-cloud-studio", 41)
    assert parse_github_pull_url(GCS47) == ("atebites-hub", "grok-cloud-studio", 47)
    assert parse_github_pull_url(GCS27) == ("atebites-hub", "grok-cloud-studio", 27)
    assert parse_github_pull_url("https://cursor.com/agents/bc-x") is None
    assert parse_github_pull_url("none") is None


def test_mergeable_empty_checks_are_not_evidence() -> None:
    for pr in (GCS41, GCS47, GCS27):
        snap = _empty_mergeable(pr=pr)
        assert snap.empty_checks is True
        assert snap.mergeable_state == "clean"
        assert is_ship_gate_evidence(snap) is False


def test_ship_gate_success_check_is_evidence() -> None:
    snap = _ship_gate_ok_snapshot()
    assert snap.empty_checks is False
    assert is_ship_gate_evidence(snap) is True
    assert is_ship_gate_check(snap.check_runs[0]) is True


def test_unrelated_success_check_is_not_ship_gate() -> None:
    snap = ShipGateSnapshot(
        pr_url=GCS41,
        mergeable_state="clean",
        head_sha="abc",
        check_runs=({"name": "Codex Security Review", "conclusion": "success"},),
        statuses_total=0,
    )
    assert snap.empty_checks is False
    assert is_ship_gate_evidence(snap) is False


def test_ship_gate_example_is_pull_request_pytest_and_secret_scan() -> None:
    """The example MERGEABLE PRs need — owned by GCS #62, not reminted here."""
    assert SHIP_GATE_EXAMPLE["on"] == "pull_request"
    assert SHIP_GATE_EXAMPLE["repo"] == "atebites-hub/grok-cloud-studio"
    assert SHIP_GATE_EXAMPLE["pytest"] == ".venv/bin/pytest -q"
    assert SHIP_GATE_EXAMPLE["secret_scan"] == "python3 scripts/secret_scan.py"
    assert SHIP_GATE_EXAMPLE["check_name"] == "pytest -q and secret_scan"
    assert "clone" not in SHIP_GATE_EXAMPLE["pytest"]


def test_this_change_does_not_clone_gcs_62_workflow() -> None:
    """GCS #62 already added ship-gate.yml and the job succeeded. Do not remint."""
    wf_dir = ROOT / ".github" / "workflows"
    names: list[str] = []
    if wf_dir.is_dir():
        names = sorted(p.name for p in wf_dir.iterdir() if p.suffix in {".yml", ".yaml"})
    extras = [n for n in names if n != "ship-gate.yml"]
    assert extras == [], extras


def test_notify_text_empty_checks_is_not_merge_request() -> None:
    text = notify_text(
        "bc-liv94",
        {
            "runStatus": "FINISHED",
            "prUrl": GCS41,
            "name": "LIV-67",
            "url": "https://cursor.com/agents/bc-liv94",
            "emptyChecks": True,
            "checkRuns": 0,
            "mergeableState": "clean",
            "shipGateOk": False,
        },
    )
    assert text.startswith("FLEET_DONE / PR_READY:")
    assert "check_runs=0" in text
    assert "empty" in text.lower()
    assert MERGE_READY not in text
    assert "not evidence" in text.lower()
    assert FAKE_TOKEN not in text


def test_notify_text_ship_gate_ok_may_merge_request() -> None:
    text = notify_text(
        "bc-62",
        {
            "runStatus": "FINISHED",
            "prUrl": GCS62,
            "name": "ship-gate",
            "url": "https://cursor.com/agents/bc-62",
            "emptyChecks": False,
            "checkRuns": 1,
            "mergeableState": "clean",
            "shipGateOk": True,
        },
    )
    assert MERGE_READY in text
    assert "check_runs=0" not in text


def test_resolve_ship_gate_keeps_waiter_flags(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_API_BASE", "http://127.0.0.1:1")
    payload = resolve_ship_gate(
        {
            "prUrl": GCS41,
            "emptyChecks": True,
            "checkRuns": 0,
            "shipGateOk": False,
            "mergeableState": "clean",
        }
    )
    assert payload["emptyChecks"] is True
    assert payload["shipGateOk"] is False


class _GitHubChecksAPI:
    def __init__(
        self,
        *,
        mergeable_state: str = "clean",
        check_runs: list[dict] | None = None,
        statuses_total: int = 0,
        head_sha: str = "deadbeef",
        token_seen: list[str] | None = None,
    ) -> None:
        self.mergeable_state = mergeable_state
        self.check_runs = check_runs if check_runs is not None else []
        self.statuses_total = statuses_total
        self.head_sha = head_sha
        self.paths: list[str] = []
        self.token_seen = token_seen if token_seen is not None else []
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.base = ""

    def __enter__(self) -> "_GitHubChecksAPI":
        api = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: object) -> None:
                return

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                api.paths.append(parsed.path)
                auth = self.headers.get("Authorization") or ""
                if auth:
                    api.token_seen.append(auth)
                if "/pulls/" in parsed.path:
                    body = {
                        "number": 41,
                        "html_url": GCS41,
                        "mergeable_state": api.mergeable_state,
                        "head": {"sha": api.head_sha},
                        "draft": False,
                    }
                elif parsed.path.endswith("/status"):
                    body = {"state": "pending", "total_count": api.statuses_total, "statuses": []}
                elif parsed.path.endswith("/check-runs"):
                    body = {
                        "total_count": len(api.check_runs),
                        "check_runs": api.check_runs,
                    }
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
                blob = json.dumps(body).encode("utf-8")
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


def test_github_pr_ship_gate_empty_mergeable(monkeypatch) -> None:
    with _GitHubChecksAPI(mergeable_state="clean", check_runs=[], statuses_total=0) as api:
        monkeypatch.setenv("GITHUB_API_BASE", api.base)
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        snap = github_pr_ship_gate(GCS41)
    assert snap is not None
    assert snap.mergeable_state == "clean"
    assert snap.empty_checks is True
    assert is_ship_gate_evidence(snap) is False
    assert any("/pulls/41" in p for p in api.paths)
    assert any(p.endswith("/check-runs") for p in api.paths)


def test_github_pr_ship_gate_never_prints_token(monkeypatch, capsys) -> None:
    with _GitHubChecksAPI() as api:
        monkeypatch.setenv("GITHUB_API_BASE", api.base)
        monkeypatch.setenv("GH_TOKEN", FAKE_TOKEN)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        snap = github_pr_ship_gate(GCS41)
    captured = capsys.readouterr()
    assert FAKE_TOKEN not in captured.out
    assert FAKE_TOKEN not in captured.err
    assert snap is not None
    assert api.token_seen
    assert all(FAKE_TOKEN not in line for line in api.token_seen) or api.token_seen[0].startswith(
        "Bearer "
    )


def test_notify_owner_empty_checks_skips_merge_request(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GCS_ROOT", str(ROOT))
    monkeypatch.setenv("GCS_A2A_STATE", str(tmp_path))
    monkeypatch.setenv("GCS_DIRECTOR_SEAT", "ops")
    pings: list[tuple[str, str]] = []

    def _ping(seat: str, text: str) -> bool:
        pings.append((seat, text))
        return True

    monkeypatch.setattr("fleet_ledger.ping_seat", _ping)
    row = notify_owner(
        "bc-liv94",
        {
            "runStatus": "FINISHED",
            "prUrl": GCS41,
            "name": "LIV-67",
            "url": "https://cursor.com/agents/bc-liv94",
            "emptyChecks": True,
            "checkRuns": 0,
            "mergeableState": "clean",
            "shipGateOk": False,
        },
        notified_by="waiter",
        seat="ops",
    )
    assert pings
    text = pings[0][1]
    assert MERGE_READY not in text
    assert "check_runs=0" in text
    assert row.get("empty_checks") is True or row.get("emptyChecks") is True
    assert FAKE_TOKEN not in text


def test_resolve_ship_gate_fetches_when_flags_omitted(monkeypatch) -> None:
    with _GitHubChecksAPI(mergeable_state="clean", check_runs=[]) as api:
        monkeypatch.setenv("GITHUB_API_BASE", api.base)
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        payload = resolve_ship_gate({"prUrl": GCS41, "runStatus": "FINISHED"})
    assert payload["emptyChecks"] is True
    assert payload["shipGateOk"] is False
    assert payload["mergeableState"] == "clean"
    assert payload["checkRuns"] == 0


def test_waiter_source_flags_empty_github_checks() -> None:
    src = WAIT_TS.read_text(encoding="utf-8")
    helper = PR_CHECKS_TS.read_text(encoding="utf-8") if PR_CHECKS_TS.is_file() else ""
    blob = src + "\n" + helper
    assert "githubPrShipGate" in blob or "emptyChecks" in src
    assert "check_runs" in blob or "checkRuns" in blob
    assert "GITHUB_API_BASE" in blob
    assert "Bot CloudAgent" not in src
    assert FAKE_TOKEN not in blob
    assert "rateLimitBackoffMs" not in helper


def test_qa_and_footer_empty_checks_are_not_merge_evidence() -> None:
    footer = (ROOT / "scripts" / "directors" / "common_footer.txt").read_text(encoding="utf-8")
    assert "check_runs=0" in footer or "empty GitHub checks" in footer.lower()
    assert "MERGE_REQUEST" in footer
    assert "result-cloud-agent.sh" in footer
    for seat in ("qa-a", "qa-b"):
        soul = (ROOT / "docs" / "studio" / "directors" / "souls" / seat / "SOUL.md").read_text(
            encoding="utf-8"
        )
        assert "empty" in soul.lower() or "check_runs" in soul
        assert "Bot CloudAgent" not in soul


class _CursorResultAPI:
    """Minimal Cursor Agents API for result-cloud-agent.sh REST."""

    def __init__(self, *, pr_url: str, agent_id: str = "bc-liv94", run_id: str = "run-liv94") -> None:
        self.pr_url = pr_url
        self.agent_id = agent_id
        self.run_id = run_id
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.base = ""

    def __enter__(self) -> "_CursorResultAPI":
        api = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: object) -> None:
                return

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                parts = [p for p in parsed.path.split("/") if p]
                if parts == ["v1", "agents", api.agent_id]:
                    body = {
                        "id": api.agent_id,
                        "name": "liv94-empty-checks",
                        "status": "ACTIVE",
                        "url": f"https://cursor.com/agents/{api.agent_id}",
                        "latestRunId": api.run_id,
                    }
                elif parts == ["v1", "agents", api.agent_id, "runs", api.run_id]:
                    body = {
                        "id": api.run_id,
                        "agentId": api.agent_id,
                        "status": "FINISHED",
                        "git": {
                            "branches": [
                                {"branch": "cursor/liv-94-empty-checks-30f8", "prUrl": api.pr_url}
                            ]
                        },
                        "result": "opened a PR",
                    }
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
                blob = json.dumps(body).encode("utf-8")
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


def test_feature_file_states_collect_json_is_evidence_path() -> None:
    text = FEATURE.read_text(encoding="utf-8")
    assert "result-cloud-agent.sh" in text
    assert "emptyChecks" in text
    assert "collect.ts" in text


def test_collect_and_result_source_attach_ship_gate() -> None:
    """LIV-96 remaining mechanic: collect JSON, not only waiter A2A ping."""
    collect = COLLECT_TS.read_text(encoding="utf-8")
    result_ts = RESULT_TS.read_text(encoding="utf-8")
    result_sh = RESULT_SH.read_text(encoding="utf-8")
    helper = PR_CHECKS_TS.read_text(encoding="utf-8")
    waiter = WAIT_TS.read_text(encoding="utf-8")
    assert "attachShipGate" in collect or "githubPrShipGate" in collect
    assert "attachShipGate" in helper
    assert "collectResult" in result_ts
    assert "resolve_ship_gate" in result_sh
    assert "attachShipGate" in waiter
    assert "Bot CloudAgent" not in collect
    list_ts = LIST_TS.read_text(encoding="utf-8")
    assert "RUNNING per repo" not in list_ts
    assert "leftover ACTIVE+FINISHED" not in collect


def test_result_cloud_agent_rest_flags_empty_github_checks(
    tmp_path: Path, monkeypatch
) -> None:
    """Director collect on MERGEABLE+#41 shape must print emptyChecks, not a bare prUrl."""
    monkeypatch.setenv("GCS_ROOT", str(ROOT))
    with _GitHubChecksAPI(mergeable_state="clean", check_runs=[], statuses_total=0) as github:
        with _CursorResultAPI(pr_url=GCS41) as cursor:
            env = {
                **os.environ,
                "HOME": str(tmp_path),
                "CURSOR_API_BASE": cursor.base,
                "CURSOR_API_KEY": FAKE_CURSOR_KEY,
                "GITHUB_API_BASE": github.base,
                "CLOUD_FORCE_REST": "1",
                "GCS_CLOUD_BACKEND": "rest",
            }
            env.pop("GH_TOKEN", None)
            env.pop("GITHUB_TOKEN", None)
            proc = subprocess.run(
                ["bash", str(RESULT_SH), "bc-liv94"],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                env=env,
                timeout=20,
            )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert payload.get("prUrl") == GCS41
    assert payload.get("runStatus") == "FINISHED" or payload.get("status") == "FINISHED"
    assert payload.get("emptyChecks") is True
    assert payload.get("shipGateOk") is False
    assert payload.get("checkRuns") == 0
    assert payload.get("mergeableState") == "clean"
    assert FAKE_TOKEN not in proc.stdout
    assert FAKE_CURSOR_KEY not in proc.stdout
    assert FAKE_CURSOR_KEY not in proc.stderr
    assert MERGE_READY not in proc.stdout
