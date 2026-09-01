"""Fleet ledger orphan predicate + FLEET_DONE mergeable=CONFLICTING ping.

Sibling product PRs #301/#304 are GitHub mergeable_state=dirty (CONFLICTING).
QA must HOLD squash. Does not remint draft-flag GCS #52 or waiter 429 GCS #35.
Never Bot CloudAgent. Living Sky LIV-41.
"""
from __future__ import annotations

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cloud"))
sys.path.insert(0, str(ROOT / "scripts" / "a2a"))

from fleet_ledger import (  # noqa: E402
    github_pr_mergeable,
    is_orphan,
    map_github_mergeable,
    notify_owner,
    notify_text,
    parse_github_pull_url,
    register,
    resolve_mergeable,
    waiter_alive,
)


def test_orphan_when_no_waiter(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GCS_ROOT", str(ROOT))
    monkeypatch.setenv("GCS_A2A_STATE", str(tmp_path))
    monkeypatch.setenv("GCS_DIRECTOR_SEAT", "ops")
    row = register("bc-orphan", seat="ops", run_id="run-1", name="demo")
    assert is_orphan(row) is True
    assert waiter_alive(row) is False


def test_not_orphan_when_waiter_pid_alive(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GCS_ROOT", str(ROOT))
    monkeypatch.setenv("GCS_A2A_STATE", str(tmp_path))
    row = register("bc-live", seat="ops", waiter_pid=os.getpid())
    assert is_orphan(row) is False


def test_not_orphan_after_waiter_notify(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GCS_ROOT", str(ROOT))
    monkeypatch.setenv("GCS_A2A_STATE", str(tmp_path))
    row = {
        "bc_id": "bc-done",
        "status": "closed",
        "notified": True,
        "notified_by": "waiter",
        "waiter_pid": None,
    }
    assert is_orphan(row) is False


def test_not_orphan_after_webhook(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GCS_ROOT", str(ROOT))
    monkeypatch.setenv("GCS_A2A_STATE", str(tmp_path))
    row = {
        "bc_id": "bc-hook",
        "status": "open",
        "notified": False,
        "notified_by": "webhook",
        "waiter_pid": None,
    }
    assert is_orphan(row) is False


PR301 = "https://github.com/atebites-hub/grok-cloud-studio/pull/301"
PR304 = "https://github.com/atebites-hub/grok-cloud-studio/pull/304"
MERGE_READY = "ping QA (odd→qa-a, even→qa-b) MERGE_REQUEST"


def _finished_payload(**extra: object) -> dict:
    body: dict = {
        "runStatus": "FINISHED",
        "prUrl": PR301,
        "name": "LIV-41",
        "url": "https://cursor.com/agents/bc-liv41",
    }
    body.update(extra)
    return body


def test_parse_github_pull_url_301_and_304() -> None:
    assert parse_github_pull_url(PR301) == ("atebites-hub", "grok-cloud-studio", 301)
    assert parse_github_pull_url(PR304) == ("atebites-hub", "grok-cloud-studio", 304)
    assert parse_github_pull_url(PR301 + "/files") == ("atebites-hub", "grok-cloud-studio", 301)
    assert parse_github_pull_url("https://github.com/atebites-hub/grok-cloud-studio/issues/301") is None
    assert parse_github_pull_url("none") is None


def test_map_github_mergeable_dirty_is_conflicting() -> None:
    """REST mergeable_state=dirty is GraphQL mergeable=CONFLICTING (#301/#304)."""
    assert map_github_mergeable({"mergeable_state": "dirty", "mergeable": False}) == "CONFLICTING"
    assert map_github_mergeable({"mergeable": "CONFLICTING"}) == "CONFLICTING"
    assert map_github_mergeable({"mergeable_state": "clean", "mergeable": True}) == "MERGEABLE"
    assert map_github_mergeable({"mergeable": "MERGEABLE"}) == "MERGEABLE"
    assert map_github_mergeable({"mergeable_state": "unstable", "mergeable": True}) == "MERGEABLE"
    assert map_github_mergeable({"mergeable_state": "unknown", "mergeable": None}) == "UNKNOWN"


def test_notify_text_conflicting_holds_squash() -> None:
    text = notify_text("bc-liv41", _finished_payload(mergeable="CONFLICTING"))
    assert text.startswith("FLEET_DONE / PR_READY:")
    assert "mergeable=CONFLICTING" in text
    assert "HOLD squash" in text
    assert MERGE_READY not in text


def test_notify_text_mergeable_still_merge_request() -> None:
    text = notify_text("bc-ready", _finished_payload(mergeable="MERGEABLE"))
    assert text.startswith("FLEET_DONE / PR_READY:")
    assert "mergeable=MERGEABLE" in text
    assert MERGE_READY in text
    assert "HOLD squash" not in text


def test_notify_text_unknown_mergeable_does_not_hold() -> None:
    text = notify_text("bc-unk", _finished_payload(mergeable="UNKNOWN"))
    assert MERGE_READY in text
    assert "HOLD squash" not in text


class _GitHubMergeableAPI:
    def __init__(self, mergeable_state: str | None, status: int = 200) -> None:
        self.mergeable_state = mergeable_state
        self.status = status
        self.paths: list[str] = []
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.base = ""

    def __enter__(self) -> "_GitHubMergeableAPI":
        api = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: object) -> None:
                return

            def do_GET(self) -> None:
                api.paths.append(urlparse(self.path).path)
                if api.status != 200:
                    self.send_response(api.status)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                body = json.dumps(
                    {
                        "number": 301,
                        "html_url": PR301,
                        "state": "open",
                        "draft": False,
                        "mergeable": False,
                        "mergeable_state": api.mergeable_state,
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


def test_github_pr_mergeable_dirty_is_conflicting(monkeypatch) -> None:
    with _GitHubMergeableAPI(mergeable_state="dirty") as api:
        monkeypatch.setenv("GITHUB_API_BASE", api.base)
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        assert github_pr_mergeable(PR301) == "CONFLICTING"
        assert github_pr_mergeable(PR304) == "CONFLICTING"
    assert "/repos/atebites-hub/grok-cloud-studio/pulls/301" in api.paths
    assert "/repos/atebites-hub/grok-cloud-studio/pulls/304" in api.paths


def test_github_pr_mergeable_http_error_is_unknown(monkeypatch) -> None:
    with _GitHubMergeableAPI(mergeable_state="dirty", status=404) as api:
        monkeypatch.setenv("GITHUB_API_BASE", api.base)
        assert github_pr_mergeable(PR301) is None


def test_resolve_mergeable_fetches_when_payload_omits_flag(monkeypatch) -> None:
    with _GitHubMergeableAPI(mergeable_state="dirty") as api:
        monkeypatch.setenv("GITHUB_API_BASE", api.base)
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        payload = resolve_mergeable(_finished_payload())
    assert payload["mergeable"] == "CONFLICTING"


def test_resolve_mergeable_keeps_waiter_supplied_flag(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_API_BASE", "http://127.0.0.1:1")
    payload = resolve_mergeable(_finished_payload(mergeable="MERGEABLE"))
    assert payload["mergeable"] == "MERGEABLE"


def test_notify_owner_conflicting_ping_holds_squash(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GCS_ROOT", str(ROOT))
    monkeypatch.setenv("GCS_A2A_STATE", str(tmp_path))
    monkeypatch.setenv("GCS_DIRECTOR_SEAT", "ops")
    pings: list[tuple[str, str]] = []

    def _ping(seat: str, text: str) -> bool:
        pings.append((seat, text))
        return True

    monkeypatch.setattr("fleet_ledger.ping_seat", _ping)
    row = notify_owner(
        "bc-liv41",
        _finished_payload(mergeable="CONFLICTING"),
        notified_by="waiter",
        seat="ops",
    )
    assert pings, "expected A2A ping"
    assert pings[0][0] == "ops"
    text = pings[0][1]
    assert "mergeable=CONFLICTING" in text
    assert "HOLD squash" in text
    assert MERGE_READY not in text
    assert row.get("mergeable") == "CONFLICTING"
