"""Fleet ledger orphan predicate."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cloud"))
sys.path.insert(0, str(ROOT / "scripts" / "a2a"))

from fleet_ledger import is_orphan, register, waiter_alive  # noqa: E402


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
