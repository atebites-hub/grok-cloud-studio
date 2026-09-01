#!/usr/bin/env python3
"""Orphan-only Extra High completion safety net.

The per-launch waiter (scripts/cloud/sdk/wait-notify.ts) is the primary path.
This process only notifies when a ledger row has no live waiter_pid and was
never closed by waiter/webhook. A waiter_pid that names a dead process is not
liveness: eviction is written to fleet.jsonl (waiter_tombstone) before the
orphan notify. Local studio. Stdlib + existing cloud scripts.

Each cycle also probes tcarac/taskboard health: the SQLite DB file plus
`ticket list` or HTTP /mcp. Logs TASKBOARD_HEALTH_OK or TASKBOARD_HEALTH_FAIL.
Does not start the board, install seat MCP, or reconnect Agent Kanban.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_CLOUD = Path(__file__).resolve().parents[1] / "cloud"
if str(_CLOUD) not in sys.path:
    sys.path.insert(0, str(_CLOUD))
from fleet_ledger import (
    is_orphan,
    load_entries,
    notify_owner,
    sweep_stale_waiters,
    write_entries,
)

ROOT = Path(os.environ.get("GCS_ROOT", Path(__file__).resolve().parents[2]))
STATE_DIR = Path(os.environ.get("GCS_A2A_STATE", str(ROOT / ".a2a-state")))
RESULT = ROOT / "scripts" / "cloud" / "result-cloud-agent.sh"
POLL_SEC = float(os.environ.get("GCS_FLEET_POLL_SEC", "45"))
LOG = STATE_DIR / "fleet-shepherd.log"
PID_FILE = STATE_DIR / "fleet-shepherd.pid"
TERMINAL = frozenset({"FINISHED", "ERROR", "CANCELLED", "EXPIRED"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{_now()} {msg}"
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, flush=True)


def _probe(bc_id: str) -> dict[str, Any] | None:
    if not RESULT.is_file():
        return None
    try:
        proc = subprocess.run(
            ["bash", str(RESULT), bc_id],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        _log(f"PROBE_ERR id={bc_id} {e}")
        return None
    text = (proc.stdout or "").strip()
    if not text:
        _log(f"PROBE_EMPTY id={bc_id} rc={proc.returncode} err={(proc.stderr or '')[:160]}")
        return None
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return None


def _reload_entry(seat: str, bc_id: str) -> dict[str, Any] | None:
    for entry in load_entries(STATE_DIR / seat / "fleet.jsonl"):
        if entry.get("bc_id") == bc_id:
            return entry
    return None


def _taskboard_db() -> Path:
    override = (os.environ.get("GCS_TASKBOARD_DB") or os.environ.get("TASKBOARD_DB") or "").strip()
    if override:
        return Path(override)
    return STATE_DIR / "taskboard" / "taskboard.db"


def _taskboard_bin() -> Path | None:
    override = (os.environ.get("TASKBOARD_BIN") or "").strip()
    if override:
        candidate = Path(override)
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    which = shutil.which("taskboard")
    if which:
        return Path(which)
    for candidate in (
        ROOT / "vendor" / "taskboard" / "taskboard",
        ROOT / "vendor" / "taskboard" / "bin" / "taskboard",
        ROOT / "bin" / "taskboard",
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def _ticket_list_ok(db: Path) -> bool:
    binary = _taskboard_bin()
    env = os.environ.copy()
    if binary is not None:
        argv = [str(binary), "--db", str(db), "ticket", "list"]
    else:
        ticket = shutil.which("ticket")
        if ticket is None:
            return False
        argv = [ticket, "list"]
        env["GCS_TASKBOARD_DB"] = str(db)
    try:
        proc = subprocess.run(
            argv,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def _mcp_http_url() -> str:
    override = (os.environ.get("GCS_TASKBOARD_MCP_URL") or "").strip()
    if override:
        return override
    host = (os.environ.get("GCS_TASKBOARD_MCP_HOST") or "127.0.0.1").strip() or "127.0.0.1"
    port = (os.environ.get("GCS_TASKBOARD_MCP_PORT") or "3011").strip() or "3011"
    return f"http://{host}:{port}/mcp"


def _mcp_http_ok() -> bool:
    url = _mcp_http_url()
    payload = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=2) as resp:
            status = int(getattr(resp, "status", 200) or 200)
            resp.read()
        return 200 <= status < 300
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, ValueError):
        return False


def _probe_taskboard_health() -> bool:
    db = _taskboard_db()
    if not db.is_file():
        _log(f"TASKBOARD_HEALTH_FAIL db={db} reason=missing-db")
        return False
    if _ticket_list_ok(db):
        _log(f"TASKBOARD_HEALTH_OK db={db} via=ticket")
        return True
    if _mcp_http_ok():
        _log(f"TASKBOARD_HEALTH_OK db={db} via=mcp")
        return True
    _log(f"TASKBOARD_HEALTH_FAIL db={db} reason=cli-and-mcp")
    return False


def _cycle() -> int:
    _probe_taskboard_health()
    notified = 0
    if not STATE_DIR.is_dir():
        return 0
    for seat_dir in sorted(STATE_DIR.iterdir()):
        if not seat_dir.is_dir() or seat_dir.name.startswith("."):
            continue
        fleet_path = seat_dir / "fleet.jsonl"
        pending = [
            (e.get("bc_id"), e.get("waiter_pid"))
            for e in load_entries(fleet_path)
            if e.get("waiter_pid") is not None
        ]
        n_evict = sweep_stale_waiters(fleet_path)
        if n_evict:
            after = {row.get("bc_id"): row for row in load_entries(fleet_path)}
            for bc_id, pid_was in pending:
                row = after.get(bc_id)
                if row and row.get("waiter_tombstone") and row.get("waiter_pid") is None:
                    _log(
                        f"WAITER_EVICT seat={seat_dir.name} id={bc_id} "
                        f"pid={pid_was} reason=dead"
                    )
        entries = load_entries(fleet_path)
        if not entries:
            continue
        dirty = False
        for e in entries:
            if not is_orphan(e):
                continue
            bc_id = str(e.get("bc_id") or "")
            if not bc_id:
                continue
            fresh = _reload_entry(seat_dir.name, bc_id)
            if fresh is None or not is_orphan(fresh):
                continue
            payload = _probe(bc_id)
            if not payload:
                e["last_probe"] = _now()
                e["probe_empty"] = True
                dirty = True
                _log(f"SHEPHERD_ORPHAN_EMPTY seat={seat_dir.name} id={bc_id}")
                continue
            run_status = str(payload.get("runStatus") or payload.get("status") or "")
            e["run_status"] = run_status
            e["pr_url"] = payload.get("prUrl")
            e["last_probe"] = _now()
            dirty = True
            if run_status not in TERMINAL:
                continue
            seat = str(e.get("seat") or seat_dir.name)
            try:
                notify_owner(bc_id, payload, notified_by="shepherd", seat=seat)
            except RuntimeError as exc:
                e["notify_fail_at"] = _now()
                e["notify_fail"] = str(exc)
                dirty = True
                _log(f"NOTIFY_FAIL seat={seat} id={bc_id} {exc}")
                continue
            notified += 1
            _log(f"NOTIFY_OK seat={seat} id={bc_id} runStatus={run_status} via=shepherd")
        if dirty:
            latest = {row.get("bc_id"): row for row in load_entries(fleet_path)}
            merged: list[dict[str, Any]] = []
            for e in entries:
                bc = e.get("bc_id")
                live = latest.get(bc)
                if live is None:
                    merged.append(e)
                    continue
                if live.get("status") == "closed":
                    merged.append(live)
                    continue
                merged.append({**live, **{k: e[k] for k in e if k in ("last_probe", "probe_empty", "run_status", "pr_url", "notify_fail_at", "notify_fail") and k in e}})
            write_entries(fleet_path, merged)
    return notified


def main() -> int:
    once = "--once" in sys.argv
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()) + "\n", encoding="utf-8")
    _log(
        f"SHEPHERD_START root={ROOT} state={STATE_DIR} poll={POLL_SEC}s "
        f"once={int(once)} orphan_only=1"
    )
    if once:
        n = _cycle()
        _log(f"SHEPHERD_ONCE notified={n}")
        return 0
    while True:
        try:
            n = _cycle()
            if n:
                _log(f"SHEPHERD_CYCLE notified={n}")
        except Exception as e:
            _log(f"SHEPHERD_ERR {e}")
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    raise SystemExit(main())
