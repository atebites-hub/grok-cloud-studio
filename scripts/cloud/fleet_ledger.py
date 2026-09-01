#!/usr/bin/env python3
"""Fleet ledger for Extra High launches.

Each owning seat keeps `.a2a-state/<seat>/fleet.jsonl` rows:

  {bc_id, seat, run_id, name, status, notified, waiter_pid, notified_by, ...}

The per-launch waiter is the primary completion path. fleet-shepherd is an
orphan-only safety net (no live waiter_pid, never notified_by=waiter).

FLEET_DONE HOLDs GitHub PRs with empty checks (MERGEABLE+empty CI is
leftover-green theatre; required check is pytest -q and secret_scan) and
until Extra High RESULT / MERGE_REQUEST pastes `.venv/bin/pytest -q`
(`N passed`) and `secret_scan=clean`. Empty leftover-green GitHub checks
are not a ship-gate.

Presence of waiter_pid is not liveness. A pid that names a dead process is
evicted durably (waiter_pid null, waiter_tombstone) so a reused pid cannot
look live and shepherd can orphan-notify once.

Closed leftover rows (notified, latest run FINISHED/ERROR/CANCELLED/EXPIRED)
can be dropped with `python3 scripts/cloud/fleet_ledger.py prune`.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LIB_DIR = Path(__file__).resolve().parents[1] / "a2a"
_CLOUD_DIR = Path(__file__).resolve().parent
if str(_CLOUD_DIR) not in sys.path:
    sys.path.insert(0, str(_CLOUD_DIR))
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
from lib import env_first, pid_alive, repo_root, state_root  # noqa: E402
from pr_evidence import has_paste_evidence, paste_from_payload  # noqa: E402
from ship_gate_evidence import (  # noqa: E402
    payload_empty_checks,
    payload_ship_gate_ok,
    resolve_ship_gate,
    should_hold_empty_checks,
)

TERMINAL = frozenset({"FINISHED", "ERROR", "CANCELLED", "EXPIRED"})
MERGE_READY = "ping QA (odd→qa-a, even→qa-b) MERGE_REQUEST"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _root() -> Path:
    return repo_root()


def _state() -> Path:
    return state_root(_root())


def _seat_name() -> str:
    return env_first("GCS_DIRECTOR_SEAT", "CLOUD_OWNER_SEAT", default="ops")


def report_to_seat() -> str:
    """LIV-104: waiter/webhook A2A copy. Default studio-ops."""
    return env_first("REPORT_TO", "GCS_REPORT_TO", default="studio-ops")


def notify_targets(owner: str) -> list[str]:
    targets = [owner]
    report = report_to_seat()
    if report and report not in targets:
        targets.append(report)
    return targets


def fleet_path(seat: str | None = None) -> Path:
    return _state() / (seat or _seat_name()) / "fleet.jsonl"


def load_entries(path: Path) -> list[dict[str, Any]]:
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


def write_entries(path: Path, entries: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    tmp.replace(path)


def register(
    bc_id: str,
    *,
    seat: str | None = None,
    run_id: str = "",
    name: str = "",
    waiter_pid: int | None = None,
) -> dict[str, Any]:
    seat_name = seat or _seat_name()
    path = fleet_path(seat_name)
    entries = load_entries(path)
    for entry in entries:
        if entry.get("bc_id") == bc_id:
            if run_id:
                entry["run_id"] = run_id
            if name:
                entry["name"] = name
            if waiter_pid:
                entry["waiter_pid"] = waiter_pid
                entry["waiter_tombstone"] = False
            entry["updated_at"] = _now()
            write_entries(path, entries)
            return entry
    row = {
        "bc_id": bc_id,
        "seat": seat_name,
        "run_id": run_id,
        "name": name,
        "status": "open",
        "notified": False,
        "waiter_pid": waiter_pid,
        "registered_at": _now(),
    }
    entries.append(row)
    write_entries(path, entries)
    return row


def set_waiter_pid(bc_id: str, waiter_pid: int, seat: str | None = None) -> None:
    path = fleet_path(seat)
    entries = load_entries(path)
    for entry in entries:
        if entry.get("bc_id") == bc_id:
            entry["waiter_pid"] = waiter_pid
            entry["waiter_tombstone"] = False
            entry["updated_at"] = _now()
            write_entries(path, entries)
            return
    register(bc_id, seat=seat, waiter_pid=waiter_pid)


def waiter_alive(entry: dict[str, Any]) -> bool:
    pid = entry.get("waiter_pid")
    try:
        pid_i = int(pid)
    except (TypeError, ValueError):
        return False
    return pid_alive(pid_i)


def evict_stale_waiter_pid(entry: dict[str, Any], *, now: str | None = None) -> bool:
    """Clear a waiter_pid that names a dead process. Durable membership leave.

    Presence of waiter_pid is not liveness. Returns True if the entry was mutated.
    """
    raw = entry.get("waiter_pid")
    if raw is None:
        return False
    try:
        pid_i = int(raw)
    except (TypeError, ValueError):
        entry["waiter_pid_evicted"] = raw
        entry["waiter_pid"] = None
        entry["waiter_tombstone"] = True
        entry["waiter_evicted_at"] = now or _now()
        return True
    if pid_i > 0 and pid_alive(pid_i):
        return False
    entry["waiter_pid_evicted"] = pid_i
    entry["waiter_pid"] = None
    entry["waiter_tombstone"] = True
    entry["waiter_evicted_at"] = now or _now()
    return True


def sweep_stale_waiters(path: Path) -> int:
    """Persist eviction of dead waiter_pid rows on one fleet.jsonl path.

    An in-memory is_orphan / pid_alive check is not eviction. Returns the
    number of rows mutated and written.
    """
    entries = load_entries(path)
    n = 0
    for entry in entries:
        if evict_stale_waiter_pid(entry):
            n += 1
    if n:
        write_entries(path, entries)
    return n


def is_orphan(entry: dict[str, Any]) -> bool:
    if entry.get("notified") and entry.get("status") == "closed":
        return False
    if entry.get("notified_by") in {"waiter", "webhook", "shepherd"}:
        return False
    if waiter_alive(entry):
        return False
    return True


def _latest_run_status(entry: dict[str, Any]) -> str:
    return str(entry.get("run_status") or entry.get("runStatus") or "").strip().upper()


def is_closed_leftover(entry: dict[str, Any]) -> bool:
    """True when a leftover fleet.jsonl row is already closed.

    Closed leftover: notified, ledger status closed, and latest run is
    FINISHED/ERROR/CANCELLED/EXPIRED. Open leftover shells (ACTIVE +
    FINISHED, not yet notified) stay on the ledger. Ledger fields only;
    this does not probe Cursor Cloud or A2A-ping.
    """
    if not entry.get("notified"):
        return False
    if entry.get("status") != "closed":
        return False
    return _latest_run_status(entry) in TERMINAL


def _seat_dirs(seat: str | None = None) -> list[Path]:
    state = _state()
    if seat:
        path = state / seat
        return [path] if path.is_dir() else []
    if not state.is_dir():
        return []
    return [
        path
        for path in sorted(state.iterdir())
        if path.is_dir() and not path.name.startswith(".")
    ]


def prune_closed_leftovers(
    *,
    seat: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Drop closed leftover rows from fleet.jsonl. Ledger-only; no API probe."""
    pruned: list[dict[str, Any]] = []
    kept_count = 0
    for seat_dir in _seat_dirs(seat):
        path = seat_dir / "fleet.jsonl"
        entries = load_entries(path)
        if not entries:
            continue
        keep: list[dict[str, Any]] = []
        for entry in entries:
            if is_closed_leftover(entry):
                pruned.append(
                    {
                        "seat": seat_dir.name,
                        "bc_id": entry.get("bc_id"),
                        "run_status": str(
                            entry.get("run_status") or entry.get("runStatus") or ""
                        ),
                    }
                )
                continue
            keep.append(entry)
            kept_count += 1
        if not dry_run and len(keep) != len(entries):
            write_entries(path, keep)
    return {
        "dry_run": dry_run,
        "pruned_count": len(pruned),
        "kept_count": kept_count,
        "pruned": pruned,
    }


def ping_seat(seat: str, text: str) -> bool:
    send = _root() / "scripts" / "a2a" / "send.sh"
    if not send.is_file():
        return False
    try:
        proc = subprocess.run(
            ["bash", str(send), seat, text],
            cwd=str(_root()),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def notify_owner(
    bc_id: str,
    payload: dict[str, Any],
    *,
    notified_by: str = "waiter",
    seat: str | None = None,
) -> dict[str, Any]:
    """A2A-ping the owning seat and REPORT_TO, then mark the ledger closed.

    If any ping fails, the row stays open so fleet-shepherd can retry.
    """
    hit = find_by_bc(bc_id)
    seat_name = seat or (hit[0] if hit else _seat_name())
    payload = resolve_ship_gate(dict(payload))
    text = notify_text(bc_id, payload)
    for target in notify_targets(seat_name):
        if not ping_seat(target, text):
            raise RuntimeError(f"A2A ping failed seat={target} id={bc_id}")
    return complete(bc_id, payload, notified_by=notified_by, seat=seat_name)


def notify_text(bc_id: str, payload: dict[str, Any]) -> str:
    run_status = str(payload.get("runStatus") or payload.get("status") or "unknown")
    pr = payload.get("prUrl") or "none"
    name = payload.get("name") or ""
    url = payload.get("url") or f"https://cursor.com/agents/{bc_id}"
    if run_status == "FINISHED":
        if should_hold_empty_checks(payload):
            check_runs = payload.get("checkRuns")
            if check_runs is None:
                check_runs = payload.get("check_runs", 0)
            mergeable = (
                payload.get("mergeableState")
                or payload.get("mergeable_state")
                or "unknown"
            )
            empty = payload_empty_checks(payload) or check_runs == 0 or check_runs == []
            if empty:
                reason = (
                    "Empty GitHub checks are not evidence "
                    "(MERGEABLE+empty CI is leftover-green theatre). "
                )
            else:
                reason = (
                    "Required GitHub check pytest -q and secret_scan is not SUCCESS. "
                    "MERGEABLE is not a substitute. "
                )
            return (
                f"FLEET_DONE / PR_READY: Extra High {bc_id} ({name}) "
                f"runStatus=FINISHED pr={pr} check_runs={check_runs} "
                f"mergeable={mergeable} url={url}. "
                f"Collect via scripts/cloud/result-cloud-agent.sh {bc_id}. "
                f"HOLD MERGE_REQUEST: {reason}"
                f"Need pull_request ship-gate: .venv/bin/pytest -q AND "
                f"python3 scripts/secret_scan.py. "
                f"Do not ping QA MERGE_REQUEST until that check is SUCCESS; "
                f"then re-collect and ping QA. RESULT with bc-id + pr."
            )
        pr_is_url = pr not in {"", "none"}
        paste = paste_from_payload(payload)
        if pr_is_url and not has_paste_evidence(paste):
            return (
                f"FLEET_DONE / PR_READY: Extra High {bc_id} ({name}) "
                f"runStatus=FINISHED pr={pr} url={url}. "
                f"Collect via scripts/cloud/result-cloud-agent.sh {bc_id}. "
                f"HOLD MERGE_REQUEST: empty GitHub leftover-green is not a "
                f"ship-gate. Paste .venv/bin/pytest -q (N passed, N>=1) and "
                f"python3 scripts/secret_scan.py (secret_scan=clean) before "
                f"pinging QA. RESULT with bc-id + pr."
            )
        return (
            f"FLEET_DONE / PR_READY: Extra High {bc_id} ({name}) "
            f"runStatus=FINISHED pr={pr} url={url}. "
            f"Collect via scripts/cloud/result-cloud-agent.sh {bc_id}. "
            f"If pr is a URL: {MERGE_READY}; "
            f"do not launch a twin. RESULT with bc-id + pr."
        )
    return (
        f"FLEET_DONE: Extra High {bc_id} ({name}) "
        f"runStatus={run_status} pr={pr} url={url}. "
        f"Inspect with scripts/cloud/result-cloud-agent.sh {bc_id}; "
        f"follow-up or close; do not ignore. RESULT."
    )


def complete(
    bc_id: str,
    payload: dict[str, Any],
    *,
    notified_by: str = "waiter",
    seat: str | None = None,
) -> dict[str, Any]:
    seat_name = seat or _seat_name()
    path = fleet_path(seat_name)
    entries = load_entries(path)
    row: dict[str, Any] | None = None
    for entry in entries:
        if entry.get("bc_id") == bc_id:
            row = entry
            break
    if row is None:
        row = register(bc_id, seat=seat_name)
        entries = load_entries(path)
        for entry in entries:
            if entry.get("bc_id") == bc_id:
                row = entry
                break
    assert row is not None
    row["run_status"] = str(payload.get("runStatus") or payload.get("status") or "")
    row["pr_url"] = payload.get("prUrl")
    if payload.get("emptyChecks") is not None or payload.get("empty_checks") is not None:
        row["empty_checks"] = payload_empty_checks(payload)
    if payload.get("shipGateOk") is not None or payload.get("ship_gate_ok") is not None:
        row["ship_gate_ok"] = payload_ship_gate_ok(payload)
    row["notified"] = True
    row["status"] = "closed"
    row["notified_by"] = notified_by
    row["notified_at"] = _now()
    write_entries(path, entries)
    return row


def find_by_bc(bc_id: str) -> tuple[str, dict[str, Any]] | None:
    state = _state()
    if not state.is_dir():
        return None
    for seat_dir in sorted(state.iterdir()):
        if not seat_dir.is_dir() or seat_dir.name.startswith("."):
            continue
        for entry in load_entries(seat_dir / "fleet.jsonl"):
            if entry.get("bc_id") == bc_id:
                return seat_dir.name, entry
    return None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Grok Cloud Studio fleet ledger")
    sub = parser.add_subparsers(dest="cmd", required=True)
    reg = sub.add_parser("register")
    reg.add_argument("--id", required=True)
    reg.add_argument("--run", default="")
    reg.add_argument("--name", default="")
    reg.add_argument("--seat", default="")
    reg.add_argument("--waiter-pid", type=int, default=0)
    setp = sub.add_parser("set-waiter")
    setp.add_argument("--id", required=True)
    setp.add_argument("--pid", type=int, required=True)
    setp.add_argument("--seat", default="")
    comp = sub.add_parser("complete")
    comp.add_argument("--id", required=True)
    comp.add_argument("--payload-file", default="")
    comp.add_argument("--notified-by", default="waiter")
    comp.add_argument("--seat", default="")
    sub.add_parser("orphans")
    lookup = sub.add_parser("lookup")
    lookup.add_argument("--id", required=True)
    ntf = sub.add_parser("notify")
    ntf.add_argument("--id", required=True)
    ntf.add_argument("--payload-file", default="")
    ntf.add_argument("--notified-by", default="waiter")
    ntf.add_argument("--seat", default="")
    prn = sub.add_parser("prune")
    prn.add_argument("--seat", default="")
    prn.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if args.cmd == "register":
        row = register(
            args.id,
            seat=args.seat or None,
            run_id=args.run,
            name=args.name,
            waiter_pid=args.waiter_pid or None,
        )
        print(json.dumps(row))
        return 0
    if args.cmd == "set-waiter":
        set_waiter_pid(args.id, args.pid, args.seat or None)
        return 0
    if args.cmd == "complete":
        if args.payload_file:
            payload = json.loads(Path(args.payload_file).read_text(encoding="utf-8"))
        else:
            payload = json.loads(sys.stdin.read() or "{}")
        row = complete(args.id, payload, notified_by=args.notified_by, seat=args.seat or None)
        print(json.dumps(row))
        return 0
    if args.cmd == "orphans":
        state = _state()
        found: list[dict[str, Any]] = []
        if state.is_dir():
            for seat_dir in sorted(state.iterdir()):
                if not seat_dir.is_dir() or seat_dir.name.startswith("."):
                    continue
                path = seat_dir / "fleet.jsonl"
                sweep_stale_waiters(path)
                for entry in load_entries(path):
                    if is_orphan(entry):
                        found.append(entry)
        print(json.dumps(found))
        return 0
    if args.cmd == "lookup":
        hit = find_by_bc(args.id)
        if not hit:
            print("{}")
            return 1
        seat, entry = hit
        print(json.dumps({"seat": seat, "entry": entry}))
        return 0
    if args.cmd == "notify":
        if args.payload_file:
            payload = json.loads(Path(args.payload_file).read_text(encoding="utf-8"))
        else:
            payload = json.loads(sys.stdin.read() or "{}")
        try:
            row = notify_owner(
                args.id,
                payload,
                notified_by=args.notified_by,
                seat=args.seat or None,
            )
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(json.dumps(row))
        return 0
    if args.cmd == "prune":
        result = prune_closed_leftovers(
            seat=args.seat or None,
            dry_run=args.dry_run,
        )
        print(json.dumps(result))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
