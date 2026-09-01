#!/usr/bin/env python3
"""Fleet ledger for Extra High launches.

Each owning seat keeps `.a2a-state/<seat>/fleet.jsonl` rows:

  {bc_id, seat, run_id, name, status, notified, waiter_pid, notified_by, ...}

The per-launch waiter is the primary completion path. fleet-shepherd is an
orphan-only safety net (no live waiter_pid, never notified_by=waiter).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LIB_DIR = Path(__file__).resolve().parents[1] / "a2a"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
from lib import env_first, pid_alive, repo_root, state_root  # noqa: E402

TERMINAL = frozenset({"FINISHED", "ERROR", "CANCELLED", "EXPIRED"})
_GITHUB_PULL_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/([^/]+)/([^/]+)/pulls?/(\d+)(?:[/?#].*)?$",
    re.IGNORECASE,
)
MERGE_READY = "ping QA (odd→qa-a, even→qa-b) MERGE_REQUEST"
_MERGEABLE_TOKENS = frozenset({"CONFLICTING", "MERGEABLE", "UNKNOWN"})
_CONFLICTING_STATES = frozenset({"dirty", "conflicting"})
_MERGEABLE_STATES = frozenset({"clean", "unstable", "blocked", "behind", "has_hooks", "draft"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _root() -> Path:
    return repo_root()


def _state() -> Path:
    return state_root(_root())


def _seat_name() -> str:
    return env_first("GCS_DIRECTOR_SEAT", "CLOUD_OWNER_SEAT", default="ops")


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


def is_orphan(entry: dict[str, Any]) -> bool:
    if entry.get("notified") and entry.get("status") == "closed":
        return False
    if entry.get("notified_by") in {"waiter", "webhook", "shepherd"}:
        return False
    if waiter_alive(entry):
        return False
    return True


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


def parse_github_pull_url(pr_url: object) -> tuple[str, str, int] | None:
    """Parse https://github.com/<owner>/<repo>/pull/<n> (also /pulls/)."""
    if not isinstance(pr_url, str):
        return None
    match = _GITHUB_PULL_RE.match(pr_url.strip())
    if not match:
        return None
    return match.group(1), match.group(2), int(match.group(3))


def map_github_mergeable(body: dict[str, Any]) -> str | None:
    """Map GitHub REST/GraphQL pull fields to MERGEABLE|CONFLICTING|UNKNOWN.

    REST mergeable_state=dirty is GraphQL mergeable=CONFLICTING (PRs #301/#304).
    """
    raw = body.get("mergeable")
    if isinstance(raw, str):
        token = raw.strip().upper()
        if token in _MERGEABLE_TOKENS:
            return token
    state = str(body.get("mergeable_state") or "").strip().lower()
    if state in _CONFLICTING_STATES:
        return "CONFLICTING"
    if raw is False:
        return "CONFLICTING"
    if state in _MERGEABLE_STATES or raw is True:
        return "MERGEABLE"
    return "UNKNOWN"


def github_pr_mergeable(pr_url: object) -> str | None:
    """GET GitHub pulls API. CONFLICTING/MERGEABLE/UNKNOWN, or None on lookup miss.

    One-shot. Do not reuse Extra High get_agent_run 429 backoff (GCS #35).
    Never prints GH_TOKEN / GITHUB_TOKEN.
    """
    parsed = parse_github_pull_url(pr_url)
    if parsed is None:
        return None
    owner, repo, number = parsed
    base = (os.environ.get("GITHUB_API_BASE") or "https://api.github.com").rstrip("/")
    url = f"{base}/repos/{owner}/{repo}/pulls/{number}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "grok-cloud-studio-waiter",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read().decode("utf-8")
        body = json.loads(raw)
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(body, dict):
        return None
    return map_github_mergeable(body)


def payload_mergeable(payload: dict[str, Any]) -> str | None:
    value = payload.get("mergeable")
    if isinstance(value, str):
        token = value.strip().upper()
        if token in _MERGEABLE_TOKENS:
            return token
        lowered = token.lower()
        if lowered in {"true", "1", "yes"}:
            return "MERGEABLE"
        if lowered in {"false", "0", "no", "dirty"}:
            return "CONFLICTING"
    if value is True:
        return "MERGEABLE"
    if value is False:
        return "CONFLICTING"
    return None


def resolve_mergeable(payload: dict[str, Any]) -> dict[str, Any]:
    """Honor waiter-supplied mergeable; otherwise look up GitHub when prUrl is a pull."""
    known = payload_mergeable(payload)
    if known is not None:
        payload["mergeable"] = known
        return payload
    flag = github_pr_mergeable(payload.get("prUrl"))
    if flag is not None:
        payload["mergeable"] = flag
    return payload


def notify_owner(
    bc_id: str,
    payload: dict[str, Any],
    *,
    notified_by: str = "waiter",
    seat: str | None = None,
) -> dict[str, Any]:
    """A2A-ping the owning seat, then mark the ledger closed.

    If the ping fails, the row stays open so fleet-shepherd can retry.
    """
    hit = find_by_bc(bc_id)
    seat_name = seat or (hit[0] if hit else _seat_name())
    payload = resolve_mergeable(dict(payload))
    text = notify_text(bc_id, payload)
    ok = ping_seat(seat_name, text)
    if not ok:
        raise RuntimeError(f"A2A ping failed seat={seat_name} id={bc_id}")
    return complete(bc_id, payload, notified_by=notified_by, seat=seat_name)


def notify_text(bc_id: str, payload: dict[str, Any]) -> str:
    run_status = str(payload.get("runStatus") or payload.get("status") or "unknown")
    pr = payload.get("prUrl") or "none"
    name = payload.get("name") or ""
    url = payload.get("url") or f"https://cursor.com/agents/{bc_id}"
    mergeable = payload_mergeable(payload)
    merge_tag = f" mergeable={mergeable}" if mergeable else ""
    if run_status == "FINISHED":
        if mergeable == "CONFLICTING":
            return (
                f"FLEET_DONE / PR_READY: Extra High {bc_id} ({name}) "
                f"runStatus=FINISHED pr={pr}{merge_tag} url={url}. "
                f"Collect via scripts/cloud/result-cloud-agent.sh {bc_id}. "
                f"GitHub PR is CONFLICTING: QA HOLD squash; do not ping QA MERGE_REQUEST; "
                f"Extra High rebase only. RESULT with bc-id + pr."
            )
        return (
            f"FLEET_DONE / PR_READY: Extra High {bc_id} ({name}) "
            f"runStatus=FINISHED pr={pr}{merge_tag} url={url}. "
            f"Collect via scripts/cloud/result-cloud-agent.sh {bc_id}. "
            f"If pr is a URL: {MERGE_READY}; "
            f"do not launch a twin. RESULT with bc-id + pr."
        )
    hold = (
        " GitHub PR is CONFLICTING: QA HOLD squash; Extra High rebase only."
        if mergeable == "CONFLICTING"
        else ""
    )
    return (
        f"FLEET_DONE: Extra High {bc_id} ({name}) "
        f"runStatus={run_status} pr={pr}{merge_tag} url={url}. "
        f"Inspect with scripts/cloud/result-cloud-agent.sh {bc_id}; "
        f"follow-up or close; do not ignore.{hold} RESULT."
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
    mergeable = payload_mergeable(payload)
    if mergeable is not None:
        row["mergeable"] = mergeable
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
                for entry in load_entries(seat_dir / "fleet.jsonl"):
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
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
