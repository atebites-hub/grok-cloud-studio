"""Fleet ledger orphan predicate and notify idempotency."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cloud"))
sys.path.insert(0, str(ROOT / "scripts" / "a2a"))

import fleet_ledger  # noqa: E402
from fleet_ledger import complete, is_orphan, notify_owner, register, waiter_alive  # noqa: E402


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


def _finished_payload(bc_id: str, name: str = "dup-run") -> dict:
    return {
        "runStatus": "FINISHED",
        "name": name,
        "prUrl": "https://github.com/atebites-hub/grok-cloud-studio/pull/1",
        "url": f"https://cursor.com/agents/{bc_id}",
    }


def test_first_waiter_notify_pings_once(tmp_path: Path, monkeypatch) -> None:
    _ledger_env(tmp_path, monkeypatch)
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
    _ledger_env(tmp_path, monkeypatch)
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
    _ledger_env(tmp_path, monkeypatch)
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
