#!/usr/bin/env python3
"""Fleet shepherd — Bot-style completion callback for Grok Build Directors.

Grok Bot Directors stayed alive and were revived when CloudAgent finished.
Grok Build seats are one-shot (wake → RESULT → exit), so nothing receives the
completion. This process fills that gap:

  1. Scan .a2a-state/<seat>/fleet.jsonl for open bc-ids (registered on launch).
  2. Poll run status via scripts/cloud/result-cloud-agent.sh.
  3. On terminal run: A2A-ping the owning seat with PR_READY / FLEET_DONE + prUrl.
  4. Mark the ledger entry notified/closed.

Local studio only. Stdlib + existing cloud scripts.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("GCS_ROOT", Path(__file__).resolve().parents[2]))
STATE_DIR = Path(os.environ.get("GCS_A2A_STATE", str(ROOT / ".a2a-state")))
SEND = ROOT / "scripts" / "a2a" / "send.sh"
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


def _load_entries(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            rec = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict) and rec.get("bc_id"):
            out.append(rec)
    return out


def _write_entries(path: Path, entries: list[dict[str, Any]]) -> None:
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    tmp.replace(path)


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
    # last JSON line
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return None


def _notify(seat: str, bc_id: str, payload: dict[str, Any]) -> bool:
    if not SEND.is_file():
        _log(f"NOTIFY_FAIL missing send.sh")
        return False
    run_status = str(payload.get("runStatus") or payload.get("status") or "unknown")
    pr = payload.get("prUrl") or "none"
    name = payload.get("name") or ""
    url = payload.get("url") or f"https://cursor.com/agents/{bc_id}"
    if run_status == "FINISHED":
        msg = (
            f"FLEET_DONE / PR_READY: your Extra High {bc_id} ({name}) "
            f"runStatus=FINISHED pr={pr} url={url}. "
            f"Collect via scripts/cloud/result-cloud-agent.sh {bc_id}. "
            f"If pr is a URL: ping QA (odd→qa-a, even→qa-b) MERGE_REQUEST; "
            f"do not launch a twin. RESULT with bc-id + pr."
        )
    else:
        msg = (
            f"FLEET_DONE: your Extra High {bc_id} ({name}) "
            f"runStatus={run_status} pr={pr} url={url}. "
            f"Inspect with scripts/cloud/result-cloud-agent.sh {bc_id}; "
            f"follow-up or close; do not ignore. RESULT."
        )
    try:
        proc = subprocess.run(
            ["bash", str(SEND), seat, msg],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        _log(f"NOTIFY_ERR seat={seat} id={bc_id} {e}")
        return False
    ok = proc.returncode == 0
    _log(
        f"NOTIFY {'OK' if ok else 'FAIL'} seat={seat} id={bc_id} "
        f"runStatus={run_status} pr={pr} rc={proc.returncode}"
    )
    return ok


def _cycle() -> int:
    notified = 0
    if not STATE_DIR.is_dir():
        return 0
    for seat_dir in sorted(STATE_DIR.iterdir()):
        if not seat_dir.is_dir() or seat_dir.name.startswith("."):
            continue
        fleet_path = seat_dir / "fleet.jsonl"
        entries = _load_entries(fleet_path)
        if not entries:
            continue
        dirty = False
        for e in entries:
            if e.get("status") == "closed" and e.get("notified"):
                continue
            if e.get("notified") and e.get("status") == "closed":
                continue
            bc_id = str(e.get("bc_id") or "")
            if not bc_id:
                continue
            # Still open or never notified
            if e.get("notified") and str(e.get("run_status") or "") in TERMINAL:
                continue
            payload = _probe(bc_id)
            if not payload:
                e["status"] = "closed"
                e["notified"] = True
                e["run_status"] = "GONE"
                e["closed_reason"] = "probe_empty"
                e["notified_at"] = _now()
                dirty = True
                _log(f"FLEET_CLOSE_GONE seat={seat_dir.name} id={bc_id}")
                continue
            run_status = str(payload.get("runStatus") or payload.get("status") or "")
            e["run_status"] = run_status
            e["pr_url"] = payload.get("prUrl")
            e["last_probe"] = _now()
            dirty = True
            if run_status not in TERMINAL:
                continue
            seat = str(e.get("seat") or seat_dir.name)
            if _notify(seat, bc_id, payload):
                e["notified"] = True
                e["status"] = "closed"
                e["notified_at"] = _now()
                notified += 1
                dirty = True
            else:
                # leave open for retry
                e["notify_fail_at"] = _now()
                dirty = True
        if dirty:
            _write_entries(fleet_path, entries)
    return notified


def main() -> int:
    once = "--once" in sys.argv
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()) + "\n", encoding="utf-8")
    _log(f"SHEPHERD_START root={ROOT} state={STATE_DIR} poll={POLL_SEC}s once={int(once)}")
    if once:
        n = _cycle()
        _log(f"SHEPHERD_ONCE notified={n}")
        return 0
    while True:
        try:
            n = _cycle()
            if n:
                _log(f"SHEPHERD_CYCLE notified={n}")
        except Exception as e:  # noqa: BLE001 — keep loop alive
            _log(f"SHEPHERD_ERR {e}")
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    raise SystemExit(main())
