"""Fleet ledger orphan predicate and notify idempotency."""
from __future__ import annotations

import importlib.util
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


def test_second_notify_after_shepherd_does_not_ping(tmp_path: Path, monkeypatch) -> None:
    """Shepherd-first must not let waiter fire a second FLEET_DONE."""
    _ledger_env(tmp_path, monkeypatch)
    pings: list[tuple[str, str]] = []

    def fake_ping(seat: str, text: str) -> bool:
        pings.append((seat, text))
        return True

    monkeypatch.setattr(fleet_ledger, "ping_seat", fake_ping)
    register("bc-shep", seat="ops", name="dup-run")
    payload = _finished_payload("bc-shep")
    first = notify_owner("bc-shep", payload, notified_by="shepherd", seat="ops")
    assert first["notified_by"] == "shepherd"
    assert len(pings) == 1

    second = notify_owner("bc-shep", payload, notified_by="waiter", seat="ops")
    assert len(pings) == 1
    assert second["notified_by"] == "shepherd"


def test_second_notify_after_webhook_does_not_ping(tmp_path: Path, monkeypatch) -> None:
    _ledger_env(tmp_path, monkeypatch)
    pings: list[tuple[str, str]] = []

    def fake_ping(seat: str, text: str) -> bool:
        pings.append((seat, text))
        return True

    monkeypatch.setattr(fleet_ledger, "ping_seat", fake_ping)
    register("bc-hook2", seat="ops")
    payload = _finished_payload("bc-hook2")
    first = notify_owner("bc-hook2", payload, notified_by="webhook", seat="ops")
    assert first["notified_by"] == "webhook"
    assert len(pings) == 1

    second = notify_owner("bc-hook2", payload, notified_by="waiter", seat="ops")
    assert len(pings) == 1
    assert second["notified_by"] == "webhook"


def test_notify_does_not_overwrite_waiter_if_complete_during_ping(
    tmp_path: Path, monkeypatch
) -> None:
    """If waiter closes the row during shepherd's ping, keep notified_by=waiter."""
    _ledger_env(tmp_path, monkeypatch)
    pings: list[str] = []
    payload = _finished_payload("bc-race")
    register("bc-race", seat="ops")

    def fake_ping(seat: str, text: str) -> bool:
        pings.append(text)
        complete("bc-race", payload, notified_by="waiter", seat="ops")
        return True

    monkeypatch.setattr(fleet_ledger, "ping_seat", fake_ping)
    row = notify_owner("bc-race", payload, notified_by="shepherd", seat="ops")
    assert len(pings) == 1
    assert row["notified_by"] == "waiter"
    assert row["notified"] is True


def test_shepherd_skips_when_waiter_closes_during_probe(
    tmp_path: Path, monkeypatch
) -> None:
    """Shepherd _probe can run after waiter already pinged; no second FLEET_DONE."""
    _ledger_env(tmp_path, monkeypatch)
    register("bc-probe", seat="ops", name="dup-run")
    pings: list[tuple[str, str]] = []

    def fake_ping(seat: str, text: str) -> bool:
        pings.append((seat, text))
        return True

    monkeypatch.setattr(fleet_ledger, "ping_seat", fake_ping)
    spec = importlib.util.spec_from_file_location(
        "gcs_shepherd_waiter_during_probe",
        ROOT / "scripts" / "directors" / "fleet-shepherd.py",
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.STATE_DIR = tmp_path
    mod.LOG = tmp_path / "fleet-shepherd.log"
    mod.PID_FILE = tmp_path / "fleet-shepherd.pid"
    mod.notify_owner = fleet_ledger.notify_owner
    payload = _finished_payload("bc-probe")

    def _probe(bc_id: str) -> dict:
        notify_owner(bc_id, payload, notified_by="waiter", seat="ops")
        return payload

    mod._probe = _probe  # type: ignore[assignment]
    assert mod._cycle() == 0
    assert len(pings) == 1
    row = fleet_ledger.load_entries(tmp_path / "ops" / "fleet.jsonl")[0]
    assert row["notified_by"] == "waiter"
    log = (tmp_path / "fleet-shepherd.log").read_text(encoding="utf-8")
    assert "NOTIFY_SKIP" in log
    assert "NOTIFY_OK" not in log
