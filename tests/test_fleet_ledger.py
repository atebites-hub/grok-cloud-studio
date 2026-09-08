"""Fleet ledger orphan predicate, leftover-shell skip, closed-leftover prune,
notify idempotency, FLEET_DONE mergeable=CONFLICTING HOLD squash, and
FLEET_DONE draft PR ping.
"""
from __future__ import annotations

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cloud"))
sys.path.insert(0, str(ROOT / "scripts" / "a2a"))

import fleet_ledger  # noqa: E402
from fleet_ledger import (  # noqa: E402
    complete,
    fleet_path,
    github_pr_is_draft,
    github_pr_mergeable,
    is_closed_leftover,
    is_leftover_shell,
    is_orphan,
    load_entries,
    map_github_mergeable,
    notify_owner,
    notify_text,
    parse_github_pull_url,
    prune_closed_leftovers,
    register,
    resolve_draft,
    resolve_mergeable,
    waiter_alive,
    write_entries,
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


def test_notify_text_includes_bound_repo() -> None:
    text = notify_text(
        "bc-done",
        {
            "runStatus": "FINISHED",
            "prUrl": "https://github.com/atebites-hub/grok-cloud-studio/pull/1",
            "name": "demo",
            "url": "https://cursor.com/agents/bc-done",
            "repoUrl": "https://github.com/atebites-hub/grok-cloud-studio",
        },
    )
    assert "repo=https://github.com/atebites-hub/grok-cloud-studio" in text
    assert "FLEET_DONE" in text


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


def _ledger_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GCS_ROOT", str(ROOT))
    monkeypatch.setenv("GCS_A2A_STATE", str(tmp_path))
    monkeypatch.setenv("GCS_DIRECTOR_SEAT", "ops")


def _row(
    bc_id: str,
    *,
    status: str = "open",
    notified: bool = False,
    run_status: str = "",
    notified_by: str | None = None,
    seat: str = "ops",
    **extra: Any,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "bc_id": bc_id,
        "seat": seat,
        "status": status,
        "notified": notified,
        "run_status": run_status,
        "waiter_pid": None,
    }
    if notified_by is not None:
        row["notified_by"] = notified_by
    row.update(extra)
    return row


def test_closed_leftover_when_notified_and_terminal() -> None:
    for run_status in ("FINISHED", "ERROR", "CANCELLED", "EXPIRED"):
        row = _row(
            f"bc-{run_status.lower()}",
            status="closed",
            notified=True,
            notified_by="waiter",
            run_status=run_status,
        )
        assert is_closed_leftover(row) is True, run_status
        assert is_leftover_shell(row) is True, run_status


def test_open_finished_shell_is_not_closed_leftover() -> None:
    """Open ACTIVE+FINISHED leftover stays on the ledger (shepherd-skip slice)."""
    row = _row(
        "bc-open-finished",
        status="open",
        notified=False,
        run_status="FINISHED",
        agent_status="ACTIVE",
    )
    assert is_orphan(row) is True
    assert is_closed_leftover(row) is False
    assert is_leftover_shell(row) is True
    assert is_leftover_shell(row, {"agentStatus": "ACTIVE", "runStatus": "FINISHED"}) is True


def test_running_row_is_not_closed_leftover() -> None:
    row = _row("bc-running", status="open", notified=False, run_status="RUNNING")
    assert is_closed_leftover(row) is False
    assert is_leftover_shell(row) is False
    assert is_leftover_shell(row, {"agentStatus": "ACTIVE", "runStatus": "RUNNING"}) is False


def test_closed_without_terminal_run_is_not_prunable() -> None:
    row = _row(
        "bc-closed-no-run",
        status="closed",
        notified=True,
        notified_by="waiter",
        run_status="",
    )
    assert is_closed_leftover(row) is False


def test_prune_reread_keeps_row_registered_after_first_load(
    tmp_path: Path, monkeypatch
) -> None:
    """Do not wipe a launch that lands between snapshot and rewrite."""
    _ledger_env(tmp_path, monkeypatch)
    path = fleet_path("ops")
    write_entries(
        path,
        [
            _row(
                "bc-done",
                status="closed",
                notified=True,
                notified_by="waiter",
                run_status="FINISHED",
            )
        ],
    )
    real_load = fleet_ledger.load_entries
    injected = {"done": False}

    def load_then_inject(p: Path) -> list[dict[str, Any]]:
        rows = real_load(p)
        if not injected["done"] and p == path:
            injected["done"] = True
            write_entries(
                path,
                rows
                + [
                    _row(
                        "bc-new",
                        status="open",
                        notified=False,
                        run_status="RUNNING",
                    )
                ],
            )
        return rows

    monkeypatch.setattr(fleet_ledger, "load_entries", load_then_inject)
    result = prune_closed_leftovers()
    remaining = real_load(path)
    assert [row["bc_id"] for row in remaining] == ["bc-new"]
    assert result["pruned_count"] == 1
    assert result["pruned"][0]["bc_id"] == "bc-done"


def test_prune_drops_closed_terminal_rows_keeps_open_and_running(
    tmp_path: Path, monkeypatch
) -> None:
    _ledger_env(tmp_path, monkeypatch)
    path = fleet_path("ops")
    write_entries(
        path,
        [
            _row(
                "bc-done",
                status="closed",
                notified=True,
                notified_by="waiter",
                run_status="FINISHED",
            ),
            _row(
                "bc-err",
                status="closed",
                notified=True,
                notified_by="shepherd",
                run_status="ERROR",
            ),
            _row(
                "bc-open-finished",
                status="open",
                notified=False,
                run_status="FINISHED",
                agent_status="ACTIVE",
            ),
            _row("bc-live", status="open", notified=False, run_status="RUNNING"),
        ],
    )
    pings: list[str] = []
    monkeypatch.setattr(
        fleet_ledger, "ping_seat", lambda seat, text: pings.append(text) or True
    )

    result = prune_closed_leftovers()

    assert result["pruned_count"] == 2
    assert result["kept_count"] == 2
    assert result["dry_run"] is False
    pruned_ids = {item["bc_id"] for item in result["pruned"]}
    assert pruned_ids == {"bc-done", "bc-err"}
    remaining = load_entries(path)
    assert [row["bc_id"] for row in remaining] == ["bc-open-finished", "bc-live"]
    assert pings == []


def test_prune_dry_run_does_not_rewrite(tmp_path: Path, monkeypatch) -> None:
    _ledger_env(tmp_path, monkeypatch)
    path = fleet_path("ops")
    rows = [
        _row(
            "bc-closed",
            status="closed",
            notified=True,
            notified_by="waiter",
            run_status="CANCELLED",
        ),
        _row("bc-keep", status="open", notified=False, run_status="RUNNING"),
    ]
    write_entries(path, rows)
    before = path.read_text(encoding="utf-8")

    result = prune_closed_leftovers(dry_run=True)

    assert result["dry_run"] is True
    assert result["pruned_count"] == 1
    assert result["pruned"][0]["bc_id"] == "bc-closed"
    assert path.read_text(encoding="utf-8") == before


def test_prune_cli_rewrites_mixed_seats(tmp_path: Path, monkeypatch, capsys) -> None:
    _ledger_env(tmp_path, monkeypatch)
    write_entries(
        fleet_path("ops"),
        [
            _row(
                "bc-ops-done",
                status="closed",
                notified=True,
                notified_by="waiter",
                run_status="EXPIRED",
                seat="ops",
            ),
            _row(
                "bc-ops-live",
                status="open",
                notified=False,
                run_status="RUNNING",
                seat="ops",
            ),
        ],
    )
    write_entries(
        fleet_path("floor"),
        [
            _row(
                "bc-floor-done",
                status="closed",
                notified=True,
                notified_by="webhook",
                run_status="FINISHED",
                seat="floor",
            )
        ],
    )

    rc = fleet_ledger.main(["prune"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["pruned_count"] == 2
    assert {item["bc_id"] for item in out["pruned"]} == {"bc-ops-done", "bc-floor-done"}
    assert [row["bc_id"] for row in load_entries(fleet_path("ops"))] == ["bc-ops-live"]
    assert load_entries(fleet_path("floor")) == []


def test_prune_cli_seat_does_not_touch_other_seats(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    _ledger_env(tmp_path, monkeypatch)
    write_entries(
        fleet_path("ops"),
        [
            _row(
                "bc-ops-done",
                status="closed",
                notified=True,
                notified_by="waiter",
                run_status="FINISHED",
                seat="ops",
            )
        ],
    )
    write_entries(
        fleet_path("floor"),
        [
            _row(
                "bc-floor-done",
                status="closed",
                notified=True,
                notified_by="waiter",
                run_status="FINISHED",
                seat="floor",
            )
        ],
    )

    rc = fleet_ledger.main(["prune", "--seat", "ops"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["pruned_count"] == 1
    assert out["pruned"][0]["bc_id"] == "bc-ops-done"
    assert load_entries(fleet_path("ops")) == []
    assert [row["bc_id"] for row in load_entries(fleet_path("floor"))] == ["bc-floor-done"]


def test_prune_empty_state_is_noop(tmp_path: Path, monkeypatch) -> None:
    _ledger_env(tmp_path, monkeypatch)
    result = prune_closed_leftovers()
    assert result == {
        "dry_run": False,
        "pruned_count": 0,
        "kept_count": 0,
        "pruned": [],
    }


def test_prune_after_complete_drops_waiter_closed_row(
    tmp_path: Path, monkeypatch
) -> None:
    _ledger_env(tmp_path, monkeypatch)
    register("bc-done", seat="ops", name="slice")
    complete(
        "bc-done",
        {"runStatus": "FINISHED", "prUrl": "https://example.test/pr/1"},
        notified_by="waiter",
        seat="ops",
    )
    result = prune_closed_leftovers()
    assert result["pruned_count"] == 1
    assert result["pruned"][0]["bc_id"] == "bc-done"
    assert result["pruned"][0]["run_status"] == "FINISHED"
    assert load_entries(fleet_path("ops")) == []


def test_prune_cli_dry_run(tmp_path: Path, monkeypatch, capsys) -> None:
    _ledger_env(tmp_path, monkeypatch)
    write_entries(
        fleet_path("ops"),
        [
            _row(
                "bc-closed",
                status="closed",
                notified=True,
                notified_by="waiter",
                run_status="FINISHED",
            )
        ],
    )
    rc = fleet_ledger.main(["prune", "--dry-run"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["dry_run"] is True
    assert out["pruned_count"] == 1
    remaining = load_entries(fleet_path("ops"))
    assert len(remaining) == 1
    assert remaining[0]["bc_id"] == "bc-closed"


def test_prune_unknown_seat_exits_nonzero(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    _ledger_env(tmp_path, monkeypatch)
    rc = fleet_ledger.main(["prune", "--seat", "nope"])
    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert out["pruned_count"] == 0
    assert out["error"] == "unknown seat=nope"


def _notify_env(tmp_path: Path, monkeypatch) -> None:
    """Owner==REPORT_TO so first waiter notify pings the owning seat once."""
    _ledger_env(tmp_path, monkeypatch)
    monkeypatch.setenv("REPORT_TO", "ops")


def _finished_payload(bc_id: str, name: str = "dup-run") -> dict:
    return {
        "runStatus": "FINISHED",
        "name": name,
        "prUrl": "https://example.test/pr/1",
        "url": f"https://cursor.com/agents/{bc_id}",
    }


def test_first_waiter_notify_pings_once(tmp_path: Path, monkeypatch) -> None:
    _notify_env(tmp_path, monkeypatch)
    pings: list[tuple[str, str]] = []

    def fake_ping(seat: str, text: str) -> bool:
        pings.append((seat, text))
        return True

    monkeypatch.setattr(fleet_ledger, "ping_seat", fake_ping)
    register("bc-first", seat="ops", name="dup-run")
    row = notify_owner(
        "bc-first",
        _finished_payload("bc-first"),
        notified_by="waiter",
        seat="ops",
    )
    assert len(pings) == 1
    assert pings[0][0] == "ops"
    assert "FLEET_DONE" in pings[0][1]
    assert "bc-first" in pings[0][1]
    assert row["notified"] is True
    assert row["notified_by"] == "waiter"
    assert row["status"] == "closed"


def test_second_notify_on_waiter_row_does_not_ping(tmp_path: Path, monkeypatch) -> None:
    """Waiter then shepherd must not double-fire FLEET_DONE for the same bc-id."""
    _notify_env(tmp_path, monkeypatch)
    pings: list[tuple[str, str]] = []

    def fake_ping(seat: str, text: str) -> bool:
        pings.append((seat, text))
        return True

    monkeypatch.setattr(fleet_ledger, "ping_seat", fake_ping)
    register("bc-dup", seat="ops", name="dup-run")
    payload = _finished_payload("bc-dup")
    first = notify_owner("bc-dup", payload, notified_by="waiter", seat="ops")
    assert first["notified_by"] == "waiter"
    assert len(pings) == 1

    second = notify_owner("bc-dup", payload, notified_by="shepherd", seat="ops")
    assert len(pings) == 1
    assert second["notified_by"] == "waiter"
    assert second["notified"] is True
    assert second["status"] == "closed"


def test_notify_skips_ping_when_row_already_complete_by_waiter(
    tmp_path: Path, monkeypatch
) -> None:
    _notify_env(tmp_path, monkeypatch)
    pings: list[str] = []

    def fake_ping(seat: str, text: str) -> bool:
        pings.append(text)
        return True

    monkeypatch.setattr(fleet_ledger, "ping_seat", fake_ping)
    register("bc-done", seat="ops")
    complete(
        "bc-done",
        {"runStatus": "FINISHED"},
        notified_by="waiter",
        seat="ops",
    )
    row = notify_owner(
        "bc-done",
        {"runStatus": "FINISHED"},
        notified_by="shepherd",
        seat="ops",
    )
    assert pings == []
    assert row["notified_by"] == "waiter"
    assert row["notified"] is True


PR301 = "https://github.com/atebites-hub/grok-cloud-studio/pull/301"
PR304 = "https://github.com/atebites-hub/grok-cloud-studio/pull/304"
MERGE_READY = "ping QA (odd→qa-a, even→qa-b) MERGE_REQUEST"
_PASTE = (
    ".venv/bin/pytest -q\n"
    "3 passed in 0.01s\n"
    "python3 scripts/secret_scan.py\n"
    "secret_scan=clean\n"
)


def _mergeable_payload(**extra: object) -> dict:
    body: dict = {
        "runStatus": "FINISHED",
        "prUrl": PR301,
        "name": "LIV-41",
        "url": "https://cursor.com/agents/bc-liv41",
        "emptyChecks": False,
        "checkRuns": 1,
        "shipGateOk": True,
        "notes": _PASTE,
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
    text = notify_text("bc-liv41", _mergeable_payload(mergeable="CONFLICTING"))
    assert text.startswith("FLEET_DONE / PR_READY:")
    assert "mergeable=CONFLICTING" in text
    assert "HOLD squash" in text
    assert MERGE_READY not in text


def test_notify_text_mergeable_still_merge_request() -> None:
    text = notify_text("bc-ready", _mergeable_payload(mergeable="MERGEABLE"))
    assert text.startswith("FLEET_DONE / PR_READY:")
    assert "mergeable=MERGEABLE" in text
    assert MERGE_READY in text
    assert "HOLD squash" not in text


def test_notify_text_unknown_mergeable_does_not_hold() -> None:
    text = notify_text("bc-unk", _mergeable_payload(mergeable="UNKNOWN"))
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
        payload = resolve_mergeable({"runStatus": "FINISHED", "prUrl": PR301, "name": "LIV-41"})
    assert payload["mergeable"] == "CONFLICTING"


def test_resolve_mergeable_keeps_waiter_supplied_flag(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_API_BASE", "http://127.0.0.1:1")
    payload = resolve_mergeable(_mergeable_payload(mergeable="MERGEABLE"))
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
        _mergeable_payload(mergeable="CONFLICTING"),
        notified_by="waiter",
        seat="ops",
    )
    assert pings, "expected A2A ping"
    assert pings[0][0] == "ops"
    for _seat, text in pings:
        assert "mergeable=CONFLICTING" in text
        assert "HOLD squash" in text
        assert MERGE_READY not in text
    assert row.get("mergeable") == "CONFLICTING"


GCS41 = "https://github.com/atebites-hub/grok-cloud-studio/pull/41"
_DRAFT_PASTE = ".venv/bin/pytest -q\n12 passed\nsecret_scan=clean"


def _draft_finished_payload(**extra: object) -> dict:
    body: dict = {
        "runStatus": "FINISHED",
        "prUrl": GCS41,
        "name": "LIV-67",
        "url": "https://cursor.com/agents/bc-liv67",
    }
    body.update(extra)
    return body


def _draft_merge_ready_payload(**extra: object) -> dict:
    return _draft_finished_payload(
        draft=False,
        shipGateOk=True,
        emptyChecks=False,
        checkRuns=1,
        result=_DRAFT_PASTE,
        **extra,
    )


def test_parse_github_pull_url_gcs_41() -> None:
    assert parse_github_pull_url(GCS41) == ("atebites-hub", "grok-cloud-studio", 41)
    assert parse_github_pull_url(GCS41 + "/files") == ("atebites-hub", "grok-cloud-studio", 41)
    assert parse_github_pull_url("https://github.com/atebites-hub/grok-cloud-studio/issues/41") is None
    assert parse_github_pull_url("https://cursor.com/agents/bc-x") is None


def test_notify_text_ready_pr_asks_qa_merge_request() -> None:
    text = notify_text("bc-ready", _draft_merge_ready_payload())
    assert text.startswith("FLEET_DONE / PR_READY:")
    assert MERGE_READY in text
    assert "draft=true" not in text


def test_notify_text_draft_pr_is_not_merge_request_ready() -> None:
    """GCS #41 LIV-67 was draft — waiter must not tell Directors to ping QA squash."""
    text = notify_text("bc-liv67", _draft_finished_payload(draft=True))
    assert text.startswith("FLEET_DONE / PR_READY:")
    assert "draft=true" in text
    assert MERGE_READY not in text
    assert "do not squash" in text.lower()


def test_notify_text_draft_string_true() -> None:
    text = notify_text("bc-liv67", _draft_finished_payload(draft="true"))
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
                body: dict[str, object] = {"number": 41, "html_url": GCS41}
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
        payload = resolve_draft(_draft_finished_payload())
    assert payload["draft"] is True


def test_resolve_draft_keeps_waiter_supplied_flag(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_API_BASE", "http://127.0.0.1:1")
    payload = resolve_draft(_draft_finished_payload(draft=False))
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
    row = notify_owner("bc-liv67", _draft_finished_payload(draft=True), notified_by="waiter", seat="ops")
    assert pings, "expected A2A ping"
    assert pings[0][0] == "ops"
    text = pings[0][1]
    assert "draft=true" in text
    assert MERGE_READY not in text
    assert row.get("draft") is True


def test_leftover_shell_notified_closed() -> None:
    row = {
        "bc_id": "bc-closed",
        "status": "closed",
        "notified": True,
        "notified_by": "waiter",
        "run_status": "FINISHED",
    }
    assert is_leftover_shell(row) is True
    assert is_orphan(row) is False


def test_leftover_shell_latest_run_finished_is_not_a_live_worker() -> None:
    """ACTIVE membership + FINISHED run is leftover even if the ledger row is still open."""
    row = {
        "bc_id": "bc-left",
        "status": "open",
        "notified": False,
        "run_status": "FINISHED",
        "agent_status": "ACTIVE",
        "waiter_pid": None,
    }
    assert is_orphan(row) is True
    assert is_leftover_shell(row) is True
    assert is_leftover_shell(row, {"agentStatus": "ACTIVE", "runStatus": "FINISHED"}) is True


def test_active_running_orphan_is_not_leftover() -> None:
    row = {
        "bc_id": "bc-live",
        "status": "open",
        "notified": False,
        "run_status": "RUNNING",
        "agent_status": "ACTIVE",
        "waiter_pid": None,
    }
    assert is_leftover_shell(row) is False
    assert is_leftover_shell(row, {"agentStatus": "ACTIVE", "runStatus": "RUNNING"}) is False
    assert is_orphan(row) is True

