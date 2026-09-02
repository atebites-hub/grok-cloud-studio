"""Hive stale membership: Extra High waiter_pid is not liveness.

Complementary to GCS #77/#36 (bot-bridge.pid tombstone). Do not import or
touch bot-bridge.py. Distinct from GCS #32 leftover ACTIVE+FINISHED skip:
this file plants a dead waiter_pid on fleet.jsonl and requires durable
eviction so shepherd can orphan-notify once.
"""
from __future__ import annotations

import importlib.util
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cloud"))
sys.path.insert(0, str(ROOT / "scripts" / "a2a"))

import fleet_ledger as fl  # noqa: E402

FEATURE = ROOT / "tests" / "features" / "stale_waiter_pid.feature"
SHEPHERD = ROOT / "scripts" / "directors" / "fleet-shepherd.py"
LEDGER = ROOT / "scripts" / "cloud" / "fleet_ledger.py"
BOT_BRIDGE = ROOT / "scripts" / "a2a" / "bot-bridge.py"
CLOUD_README = ROOT / "scripts" / "cloud" / "README.md"
ARCH = ROOT / "docs" / "ARCHITECTURE.md"


def _dead_pid() -> int:
    """Return a pid that is not running (Hive leftover membership)."""
    proc = subprocess.Popen(
        ["sleep", "30"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    pid = int(proc.pid)
    proc.kill()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
        for _ in range(20):
            try:
                os.kill(pid, 0)
            except OSError:
                break
            time.sleep(0.05)
    try:
        os.kill(pid, 0)
        alive = True
    except OSError:
        alive = False
    assert not alive, f"expected dead pid still alive: {pid}"
    return pid


def _plant(seat_dir: Path, rows: list[dict[str, Any]]) -> None:
    seat_dir.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    (seat_dir / "fleet.jsonl").write_text(text, encoding="utf-8")


def _load_shepherd(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SHEPHERD)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _bind_shepherd(mod: ModuleType, state: Path) -> None:
    mod.STATE_DIR = state
    mod.LOG = state / "fleet-shepherd.log"
    mod.PID_FILE = state / "fleet-shepherd.pid"


def _reload_ops(state: Path) -> dict[str, Any]:
    rows = fl.load_entries(state / "ops" / "fleet.jsonl")
    assert rows, "expected fleet.jsonl row"
    return rows[0]


def test_stale_waiter_feature_binds_ledger_and_shepherd() -> None:
    text = FEATURE.read_text(encoding="utf-8")
    fold = " ".join(text.lower().split())
    assert FEATURE.is_file()
    assert "waiter_pid" in fold
    assert "fleet.jsonl" in fold
    assert "not liveness" in fold or "not a live waiter" in fold
    assert "durable" in fold
    assert "orphan-notify once" in fold or "orphan-notifies once" in fold
    assert "bot-bridge.py" in fold
    assert "do not touch bot-bridge.py" in fold
    assert "#32" in text or "leftover active" in fold
    ledger = LEDGER.read_text(encoding="utf-8")
    assert "sweep_stale_waiters" in ledger
    assert "waiter_tombstone" in ledger
    shepherd = SHEPHERD.read_text(encoding="utf-8")
    assert "sweep_stale_waiters" in shepherd
    assert "WAITER_EVICT" in shepherd
    readme = CLOUD_README.read_text(encoding="utf-8")
    assert "waiter_pid" in readme
    assert "tombstone" in readme.lower() or "evict" in readme.lower()
    arch = ARCH.read_text(encoding="utf-8")
    assert "waiter_pid" in arch
    assert BOT_BRIDGE.is_file()


def test_dead_waiter_pid_is_not_liveness(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GCS_ROOT", str(ROOT))
    monkeypatch.setenv("GCS_A2A_STATE", str(tmp_path))
    monkeypatch.setenv("GCS_DIRECTOR_SEAT", "ops")
    dead = _dead_pid()
    row = fl.register("bc-dead", seat="ops", waiter_pid=dead)
    assert fl.waiter_alive(row) is False
    assert fl.is_orphan(row) is True


def test_in_memory_orphan_is_not_eviction(tmp_path: Path, monkeypatch) -> None:
    """pid_alive / is_orphan must not be the leave — fleet.jsonl keeps the pid."""
    monkeypatch.setenv("GCS_ROOT", str(ROOT))
    monkeypatch.setenv("GCS_A2A_STATE", str(tmp_path))
    monkeypatch.setenv("GCS_DIRECTOR_SEAT", "ops")
    dead = _dead_pid()
    fl.register("bc-ghost", seat="ops", waiter_pid=dead)
    path = tmp_path / "ops" / "fleet.jsonl"
    loaded = fl.load_entries(path)
    assert fl.is_orphan(loaded[0]) is True
    still = fl.load_entries(path)
    assert still[0].get("waiter_pid") == dead


def test_sweep_evicts_dead_waiter_pid_durably(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GCS_ROOT", str(ROOT))
    monkeypatch.setenv("GCS_A2A_STATE", str(tmp_path))
    monkeypatch.setenv("GCS_DIRECTOR_SEAT", "ops")
    dead = _dead_pid()
    fl.register("bc-evict", seat="ops", waiter_pid=dead)
    path = tmp_path / "ops" / "fleet.jsonl"
    n = fl.sweep_stale_waiters(path)
    assert n == 1
    after = fl.load_entries(path)
    assert after[0].get("waiter_pid") is None
    assert after[0].get("waiter_tombstone") is True
    assert after[0].get("waiter_pid_evicted") == dead
    assert after[0].get("waiter_evicted_at")
    assert fl.is_orphan(after[0]) is True
    assert fl.waiter_alive(after[0]) is False


def test_live_waiter_pid_is_not_evicted(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GCS_ROOT", str(ROOT))
    monkeypatch.setenv("GCS_A2A_STATE", str(tmp_path))
    monkeypatch.setenv("GCS_DIRECTOR_SEAT", "ops")
    live = os.getpid()
    fl.register("bc-live", seat="ops", waiter_pid=live)
    path = tmp_path / "ops" / "fleet.jsonl"
    n = fl.sweep_stale_waiters(path)
    assert n == 0
    after = fl.load_entries(path)
    assert after[0].get("waiter_pid") == live
    assert after[0].get("waiter_tombstone") in (None, False)
    assert fl.is_orphan(after[0]) is False
    assert fl.waiter_alive(after[0]) is True


def test_durable_eviction_survives_pid_reuse(monkeypatch) -> None:
    stale = 999001
    row: dict[str, Any] = {
        "bc_id": "bc-reuse",
        "status": "open",
        "notified": False,
        "waiter_pid": stale,
    }
    monkeypatch.setattr(fl, "pid_alive", lambda pid: False)
    assert fl.evict_stale_waiter_pid(row) is True
    monkeypatch.setattr(fl, "pid_alive", lambda pid: True)
    assert row.get("waiter_pid") is None
    assert row.get("waiter_tombstone") is True
    assert row.get("waiter_pid_evicted") == stale
    assert fl.waiter_alive(row) is False
    assert fl.is_orphan(row) is True


def test_set_waiter_pid_clears_tombstone(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GCS_ROOT", str(ROOT))
    monkeypatch.setenv("GCS_A2A_STATE", str(tmp_path))
    monkeypatch.setenv("GCS_DIRECTOR_SEAT", "ops")
    dead = _dead_pid()
    fl.register("bc-respawn", seat="ops", waiter_pid=dead)
    path = tmp_path / "ops" / "fleet.jsonl"
    assert fl.sweep_stale_waiters(path) == 1
    live = os.getpid()
    fl.set_waiter_pid("bc-respawn", live, seat="ops")
    after = fl.load_entries(path)
    assert after[0].get("waiter_pid") == live
    assert after[0].get("waiter_tombstone") is False
    assert fl.is_orphan(after[0]) is False


def test_shepherd_evicts_dead_waiter_pid_when_probe_empty(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("GCS_ROOT", str(ROOT))
    monkeypatch.setenv("GCS_A2A_STATE", str(tmp_path))
    dead = _dead_pid()
    _plant(
        tmp_path / "ops",
        [
            {
                "bc_id": "bc-empty",
                "seat": "ops",
                "status": "open",
                "notified": False,
                "waiter_pid": dead,
            }
        ],
    )
    mod = _load_shepherd("gcs_shepherd_evict_empty")
    _bind_shepherd(mod, tmp_path)
    notifies: list[str] = []
    mod._probe = lambda bc_id: None  # type: ignore[assignment]
    mod.notify_owner = lambda bc_id, payload, **kwargs: notifies.append(bc_id)  # type: ignore[assignment]

    assert mod._cycle() == 0
    assert notifies == []
    after = _reload_ops(tmp_path)
    assert after.get("waiter_pid") is None
    assert after.get("waiter_tombstone") is True
    assert after.get("waiter_pid_evicted") == dead
    log = (tmp_path / "fleet-shepherd.log").read_text(encoding="utf-8")
    assert "WAITER_EVICT" in log
    assert "bc-empty" in log


def test_shepherd_orphan_notifies_once_after_eviction(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("GCS_ROOT", str(ROOT))
    monkeypatch.setenv("GCS_A2A_STATE", str(tmp_path))
    monkeypatch.setenv("GCS_DIRECTOR_SEAT", "ops")
    monkeypatch.delenv("REPORT_TO", raising=False)
    monkeypatch.delenv("GCS_REPORT_TO", raising=False)
    dead = _dead_pid()
    _plant(
        tmp_path / "ops",
        [
            {
                "bc_id": "bc-once",
                "seat": "ops",
                "status": "open",
                "notified": False,
                "waiter_pid": dead,
                "name": "once",
            }
        ],
    )
    pings: list[tuple[str, str]] = []

    def _ping(seat: str, text: str) -> bool:
        pings.append((seat, text))
        return True

    monkeypatch.setattr(fl, "ping_seat", _ping)
    mod = _load_shepherd("gcs_shepherd_notify_once")
    _bind_shepherd(mod, tmp_path)

    def _probe(bc_id: str) -> dict[str, Any]:
        return {
            "runStatus": "FINISHED",
            "agentStatus": "ACTIVE",
            "status": "FINISHED",
            "prUrl": "https://example.test/pr/1",
            "name": "once",
            "url": "https://cursor.com/agents/bc-once",
        }

    mod._probe = _probe  # type: ignore[assignment]
    # Use the real notify_owner (imported at load) so complete() is durable.
    mod.notify_owner = fl.notify_owner  # type: ignore[assignment]

    assert mod._cycle() == 1
    assert [seat for seat, _text in pings] == ["ops", "studio-ops"]
    assert all("FLEET_DONE" in text for _seat, text in pings)
    after = _reload_ops(tmp_path)
    assert after.get("waiter_pid") is None
    assert after.get("waiter_tombstone") is True
    assert after.get("notified_by") == "shepherd"
    assert after.get("status") == "closed"
    assert after.get("notified") is True

    pings.clear()
    assert mod._cycle() == 0
    assert pings == []
    again = _reload_ops(tmp_path)
    assert again.get("notified_by") == "shepherd"


def test_orphans_cli_evicts_dead_waiter_pid(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GCS_ROOT", str(ROOT))
    monkeypatch.setenv("GCS_A2A_STATE", str(tmp_path))
    monkeypatch.setenv("GCS_DIRECTOR_SEAT", "ops")
    dead = _dead_pid()
    fl.register("bc-cli", seat="ops", waiter_pid=dead)
    proc = subprocess.run(
        ["python3", str(LEDGER), "orphans"],
        cwd=str(ROOT),
        env={**os.environ, "GCS_ROOT": str(ROOT), "GCS_A2A_STATE": str(tmp_path)},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == 0, proc.stderr
    found = json.loads(proc.stdout)
    assert any(row.get("bc_id") == "bc-cli" for row in found)
    after = fl.load_entries(tmp_path / "ops" / "fleet.jsonl")
    assert after[0].get("waiter_pid") is None
    assert after[0].get("waiter_tombstone") is True
