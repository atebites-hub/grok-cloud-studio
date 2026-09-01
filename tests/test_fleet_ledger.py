"""Fleet ledger orphan predicate and closed-leftover prune."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cloud"))
sys.path.insert(0, str(ROOT / "scripts" / "a2a"))

import fleet_ledger  # noqa: E402
from fleet_ledger import (  # noqa: E402
    complete,
    fleet_path,
    is_closed_leftover,
    is_orphan,
    load_entries,
    prune_closed_leftovers,
    register,
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


def test_running_row_is_not_closed_leftover() -> None:
    row = _row("bc-running", status="open", notified=False, run_status="RUNNING")
    assert is_closed_leftover(row) is False


def test_closed_without_terminal_run_is_not_prunable() -> None:
    row = _row(
        "bc-closed-no-run",
        status="closed",
        notified=True,
        notified_by="waiter",
        run_status="",
    )
    assert is_closed_leftover(row) is False


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



