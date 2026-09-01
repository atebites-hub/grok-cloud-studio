"""Fleet ledger orphan predicate and leftover-shell skip."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cloud"))
sys.path.insert(0, str(ROOT / "scripts" / "a2a"))

from fleet_ledger import is_leftover_shell, is_orphan, register, waiter_alive  # noqa: E402


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
