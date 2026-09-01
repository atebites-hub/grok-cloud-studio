"""fleet-shepherd skips ACTIVE+FINISHED leftover shells.

Cursor Cloud agents stay ACTIVE until archive. Notified closed ledger rows
and agents whose latest run is already FINISHED are leftover membership, not
live workers. Shepherd must not call result-cloud-agent / get_agent_run on
those rows — that burns the hourly run-GET cap and looks like spinning.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SHEPHERD = ROOT / "scripts" / "directors" / "fleet-shepherd.py"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SHEPHERD)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _plant(seat_dir: Path, rows: list[dict[str, Any]]) -> None:
    seat_dir.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    (seat_dir / "fleet.jsonl").write_text(text, encoding="utf-8")


def _bind_state(mod: ModuleType, state: Path) -> None:
    mod.STATE_DIR = state
    mod.LOG = state / "fleet-shepherd.log"
    mod.PID_FILE = state / "fleet-shepherd.pid"


def test_shepherd_does_not_probe_notified_closed_leftover(tmp_path: Path) -> None:
    """Closed+notified shells must not hit get_agent_run."""
    mod = _load("gcs_shepherd_skip_closed")
    _bind_state(mod, tmp_path)
    _plant(
        tmp_path / "ops",
        [
            {
                "bc_id": "bc-closed",
                "seat": "ops",
                "status": "closed",
                "notified": True,
                "notified_by": "waiter",
                "run_status": "FINISHED",
                "waiter_pid": None,
            }
        ],
    )
    probes: list[str] = []
    notifies: list[str] = []
    mod._probe = lambda bc_id: probes.append(bc_id) or {  # type: ignore[assignment]
        "runStatus": "FINISHED",
        "agentStatus": "ACTIVE",
        "status": "FINISHED",
    }
    mod.notify_owner = lambda bc_id, payload, **kwargs: notifies.append(bc_id)  # type: ignore[assignment]

    assert mod._cycle() == 0
    assert probes == []
    assert notifies == []


def test_shepherd_does_not_probe_finished_open_leftover(tmp_path: Path) -> None:
    """Open orphan whose latest run is already FINISHED is leftover — no run GET."""
    mod = _load("gcs_shepherd_skip_finished")
    _bind_state(mod, tmp_path)
    _plant(
        tmp_path / "ops",
        [
            {
                "bc_id": "bc-leftover",
                "seat": "ops",
                "status": "open",
                "notified": False,
                "run_status": "FINISHED",
                "agent_status": "ACTIVE",
                "waiter_pid": None,
            }
        ],
    )
    probes: list[str] = []
    notifies: list[str] = []
    mod._probe = lambda bc_id: probes.append(bc_id) or {  # type: ignore[assignment]
        "runStatus": "FINISHED",
        "agentStatus": "ACTIVE",
        "status": "FINISHED",
    }
    mod.notify_owner = lambda bc_id, payload, **kwargs: notifies.append(bc_id)  # type: ignore[assignment]

    assert mod._cycle() == 0
    assert probes == []
    assert notifies == []
    log = (tmp_path / "fleet-shepherd.log").read_text(encoding="utf-8")
    assert "SHEPHERD_SKIP leftover" in log
    assert "bc-leftover" in log


def test_shepherd_probes_live_orphan_without_finished_run(tmp_path: Path) -> None:
    """True orphans (no terminal run on the ledger) still get one result probe."""
    mod = _load("gcs_shepherd_probe_live")
    _bind_state(mod, tmp_path)
    _plant(
        tmp_path / "ops",
        [
            {
                "bc_id": "bc-live",
                "seat": "ops",
                "status": "open",
                "notified": False,
                "waiter_pid": None,
            }
        ],
    )
    probes: list[str] = []

    def _probe(bc_id: str) -> dict[str, Any]:
        probes.append(bc_id)
        return {
            "runStatus": "RUNNING",
            "agentStatus": "ACTIVE",
            "status": "RUNNING",
        }

    notified: list[str] = []
    mod._probe = _probe  # type: ignore[assignment]
    mod.notify_owner = lambda bc_id, payload, **kwargs: notified.append(bc_id)  # type: ignore[assignment]

    assert mod._cycle() == 0
    assert probes == ["bc-live"]
    assert notified == []


def test_shepherd_second_cycle_does_not_reprobe_finished(tmp_path: Path) -> None:
    """After a FINISHED probe, later cycles must not hammer get_agent_run."""
    mod = _load("gcs_shepherd_no_reprobe")
    _bind_state(mod, tmp_path)
    _plant(
        tmp_path / "ops",
        [
            {
                "bc_id": "bc-once",
                "seat": "ops",
                "status": "open",
                "notified": False,
                "waiter_pid": None,
            }
        ],
    )
    probes: list[str] = []

    def _probe(bc_id: str) -> dict[str, Any]:
        probes.append(bc_id)
        return {
            "runStatus": "FINISHED",
            "agentStatus": "ACTIVE",
            "status": "FINISHED",
            "prUrl": "https://example.test/pr/1",
            "name": "once",
            "url": "https://cursor.com/agents/bc-once",
        }

    def _notify_fail(bc_id: str, payload: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("A2A ping failed")

    mod._probe = _probe  # type: ignore[assignment]
    mod.notify_owner = _notify_fail  # type: ignore[assignment]

    assert mod._cycle() == 0
    assert probes == ["bc-once"]

    probes.clear()
    assert mod._cycle() == 0
    assert probes == [], "leftover FINISHED must not get_agent_run again"


def test_shepherd_skips_leftovers_while_probing_live_orphan(tmp_path: Path) -> None:
    """Same cycle: leftover FINISHED shells are skipped; a RUNNING orphan is probed."""
    mod = _load("gcs_shepherd_mixed")
    _bind_state(mod, tmp_path)
    _plant(
        tmp_path / "ops",
        [
            {
                "bc_id": "bc-closed",
                "seat": "ops",
                "status": "closed",
                "notified": True,
                "notified_by": "waiter",
                "run_status": "FINISHED",
            },
            {
                "bc_id": "bc-leftover",
                "seat": "ops",
                "status": "open",
                "notified": False,
                "run_status": "FINISHED",
                "agent_status": "ACTIVE",
            },
            {
                "bc_id": "bc-live",
                "seat": "ops",
                "status": "open",
                "notified": False,
            },
        ],
    )
    probes: list[str] = []

    def _probe(bc_id: str) -> dict[str, Any]:
        probes.append(bc_id)
        return {
            "runStatus": "RUNNING",
            "agentStatus": "ACTIVE",
            "status": "RUNNING",
        }

    def _no_notify(*_a: Any, **_k: Any) -> None:
        raise AssertionError("shepherd must not notify leftovers or RUNNING orphans")

    mod._probe = _probe  # type: ignore[assignment]
    mod.notify_owner = _no_notify  # type: ignore[assignment]

    assert mod._cycle() == 0
    assert probes == ["bc-live"]
