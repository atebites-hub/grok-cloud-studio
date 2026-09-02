"""LIV-104: waiter A2A-pings REPORT_TO (default studio-ops)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cloud"))
sys.path.insert(0, str(ROOT / "scripts" / "a2a"))

import fleet_ledger  # noqa: E402
from fleet_ledger import notify_owner, register, report_to_seat  # noqa: E402


def test_report_to_defaults_studio_ops(monkeypatch) -> None:
    monkeypatch.delenv("REPORT_TO", raising=False)
    monkeypatch.delenv("GCS_REPORT_TO", raising=False)
    assert report_to_seat() == "studio-ops"


def test_report_to_env_wins(monkeypatch) -> None:
    monkeypatch.setenv("REPORT_TO", "floor")
    assert report_to_seat() == "floor"


def test_notify_owner_pings_owner_and_studio_ops(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GCS_ROOT", str(ROOT))
    monkeypatch.setenv("GCS_A2A_STATE", str(tmp_path))
    monkeypatch.delenv("REPORT_TO", raising=False)
    pings: list[str] = []

    def fake_ping(seat: str, text: str) -> bool:
        pings.append(seat)
        assert "FLEET_DONE" in text
        return True

    monkeypatch.setattr(fleet_ledger, "ping_seat", fake_ping)
    register("bc-liv104", seat="art", run_id="run-1", name="demo")
    notify_owner(
        "bc-liv104",
        {"runStatus": "FINISHED", "prUrl": "https://example.test/pr/1"},
        seat="art",
    )
    assert pings == ["art", "studio-ops"]


def test_notify_owner_does_not_double_ping_when_owner_is_report_to(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("GCS_ROOT", str(ROOT))
    monkeypatch.setenv("GCS_A2A_STATE", str(tmp_path))
    monkeypatch.delenv("REPORT_TO", raising=False)
    pings: list[str] = []

    def fake_ping(seat: str, text: str) -> bool:
        pings.append(seat)
        return True

    monkeypatch.setattr(fleet_ledger, "ping_seat", fake_ping)
    register("bc-ops", seat="studio-ops")
    notify_owner("bc-ops", {"runStatus": "ERROR"}, seat="studio-ops")
    assert pings == ["studio-ops"]
