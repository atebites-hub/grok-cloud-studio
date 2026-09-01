"""Fleet ledger orphan predicate + FLEET_DONE draft PR ping."""
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
    github_pr_is_draft,
    is_orphan,
    notify_owner,
    notify_text,
    parse_github_pull_url,
    register,
    resolve_draft,
    waiter_alive,
)

GCS41 = "https://github.com/atebites-hub/grok-cloud-studio/pull/41"
MERGE_READY = "ping QA (odd→qa-a, even→qa-b) MERGE_REQUEST"


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


def _finished_payload(**extra: object) -> dict:
    body: dict = {
        "runStatus": "FINISHED",
        "prUrl": GCS41,
        "name": "LIV-67",
        "url": "https://cursor.com/agents/bc-liv67",
    }
    body.update(extra)
    return body


def test_parse_github_pull_url_gcs_41() -> None:
    assert parse_github_pull_url(GCS41) == ("atebites-hub", "grok-cloud-studio", 41)
    assert parse_github_pull_url(GCS41 + "/files") == ("atebites-hub", "grok-cloud-studio", 41)
    assert parse_github_pull_url("https://github.com/atebites-hub/grok-cloud-studio/issues/41") is None
    assert parse_github_pull_url("https://cursor.com/agents/bc-x") is None
    assert parse_github_pull_url("none") is None


def test_notify_text_ready_pr_asks_qa_merge_request() -> None:
    text = notify_text("bc-ready", _finished_payload(draft=False))
    assert text.startswith("FLEET_DONE / PR_READY:")
    assert MERGE_READY in text
    assert "draft=true" not in text


def test_notify_text_draft_pr_is_not_merge_request_ready() -> None:
    """GCS #41 LIV-67 was draft — waiter must not tell Directors to ping QA squash."""
    text = notify_text("bc-liv67", _finished_payload(draft=True))
    assert text.startswith("FLEET_DONE / PR_READY:")
    assert "draft=true" in text
    assert MERGE_READY not in text
    assert "do not squash" in text.lower()


def test_notify_text_draft_string_true() -> None:
    text = notify_text("bc-liv67", _finished_payload(draft="true"))
    assert "draft=true" in text
    assert MERGE_READY not in text


class _GitHubDraftAPI:
    def __init__(self, draft: bool | None, status: int = 200) -> None:
        self.draft = draft
        self.status = status
        self.paths: list[str] = []
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.base = ""

    def __enter__(self) -> "_GitHubDraftAPI":
        api = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: object) -> None:
                return

            def do_GET(self) -> None:
                api.paths.append(urlparse(self.path).path)
                if api.status != 200:
                    self.send_response(api.status)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"message":"error"}')
                    return
                body = {"number": 41, "html_url": GCS41}
                if api.draft is not None:
                    body["draft"] = api.draft
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


def test_github_pr_is_draft_true(monkeypatch) -> None:
    with _GitHubDraftAPI(draft=True) as api:
        monkeypatch.setenv("GITHUB_API_BASE", api.base)
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        assert github_pr_is_draft(GCS41) is True
    assert any(p.endswith("/repos/atebites-hub/grok-cloud-studio/pulls/41") for p in api.paths)


def test_github_pr_is_draft_false(monkeypatch) -> None:
    with _GitHubDraftAPI(draft=False) as api:
        monkeypatch.setenv("GITHUB_API_BASE", api.base)
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        assert github_pr_is_draft(GCS41) is False


def test_github_pr_is_draft_http_error_is_unknown(monkeypatch) -> None:
    with _GitHubDraftAPI(draft=True, status=404) as api:
        monkeypatch.setenv("GITHUB_API_BASE", api.base)
        assert github_pr_is_draft(GCS41) is None


def test_resolve_draft_fetches_when_payload_omits_flag(monkeypatch) -> None:
    with _GitHubDraftAPI(draft=True) as api:
        monkeypatch.setenv("GITHUB_API_BASE", api.base)
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        payload = resolve_draft(_finished_payload())
    assert payload["draft"] is True


def test_resolve_draft_keeps_waiter_supplied_flag(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_API_BASE", "http://127.0.0.1:1")
    payload = resolve_draft(_finished_payload(draft=False))
    assert payload["draft"] is False


def test_notify_owner_draft_ping_skips_merge_request(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GCS_ROOT", str(ROOT))
    monkeypatch.setenv("GCS_A2A_STATE", str(tmp_path))
    monkeypatch.setenv("GCS_DIRECTOR_SEAT", "ops")
    pings: list[tuple[str, str]] = []

    def _ping(seat: str, text: str) -> bool:
        pings.append((seat, text))
        return True

    monkeypatch.setattr("fleet_ledger.ping_seat", _ping)
    row = notify_owner("bc-liv67", _finished_payload(draft=True), notified_by="waiter", seat="ops")
    assert pings, "expected A2A ping"
    assert pings[0][0] == "ops"
    text = pings[0][1]
    assert "draft=true" in text
    assert MERGE_READY not in text
    assert row.get("draft") is True
