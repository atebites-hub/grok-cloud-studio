#!/usr/bin/env python3
"""Fleet ledger for Extra High launches.

Each owning seat keeps `.a2a-state/<seat>/fleet.jsonl` rows:

  {bc_id, seat, run_id, name, status, notified, waiter_pid, notified_by, ...}

The per-launch waiter is the primary completion path. fleet-shepherd is an
orphan-only safety net (no live waiter_pid, never notified_by=waiter). It
skips leftover shells: notified closed rows, and agents whose latest run is
already FINISHED (Cursor Cloud membership stays ACTIVE until archive).
Probing those with get_agent_run burns the hourly cap and looks like spinning.

FLEET_DONE HOLDs GitHub draft PRs (`draft=true`, not MERGE_REQUEST-ready)
and PRs with empty checks (MERGEABLE+empty CI is leftover-green theatre;
required check is pytest -q and secret_scan) and until Extra High RESULT
/ MERGE_REQUEST pastes `.venv/bin/pytest -q` (`N passed`) and
`secret_scan=clean`. Empty leftover-green GitHub checks are not a
ship-gate. GitHub drafts are never squash-ready. REST `mergeable_state=dirty`
is GraphQL `mergeable=CONFLICTING`: the ping includes `mergeable=CONFLICTING`
and QA HOLD squash (Extra High rebase only; not MERGE_REQUEST-ready).

Presence of waiter_pid is not liveness. A pid that names a dead process is
evicted durably (waiter_pid null, waiter_tombstone) so a reused pid cannot
look live and shepherd can orphan-notify once.

Closed leftover rows (notified, status=closed, latest run
FINISHED/ERROR/CANCELLED/EXPIRED; US CANCELED maps to CANCELLED) can be
dropped with `python3 scripts/cloud/fleet_ledger.py prune`. fleet-shepherd
prunes those rows each cycle so they are not paged as live. Open leftover
shells stay. RUNNING is not cancelled.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
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
from collect_close import pr_url_or_none  # noqa: E402
from pr_evidence import has_paste_evidence, paste_from_payload  # noqa: E402
from ship_gate_evidence import (  # noqa: E402
    parse_github_pull_url,
    payload_empty_checks,
    payload_ship_gate_ok,
    resolve_ship_gate,
    should_hold_empty_checks,
)

TERMINAL = frozenset({"FINISHED", "ERROR", "CANCELLED", "EXPIRED"})
MEMBERSHIP_NOT_LIVENESS = frozenset({"ACTIVE", "IDLE"})
MERGE_READY = "ping QA (odd→qa-a, even→qa-b) MERGE_REQUEST"
_MERGEABLE_TOKENS = frozenset({"CONFLICTING", "MERGEABLE", "UNKNOWN"})
_CONFLICTING_STATES = frozenset({"dirty", "conflicting"})
_MERGEABLE_STATES = frozenset({"clean", "unstable", "blocked", "behind", "has_hooks", "draft"})


def normalize_run_status(value: object) -> str:
    """Map Cursor/SDK run status to GCS tokens. US `CANCELED` → `CANCELLED`."""
    raw = str(value or "").strip().upper()
    if raw == "CANCELED":
        return "CANCELLED"
    return raw or "unknown"


def run_status_from_payload(payload: dict[str, Any] | None) -> str:
    """Latest-run liveness from a result payload.

    Prefer ``runStatus`` / ``run_status``. Agent membership ``ACTIVE``/``IDLE``
    (Cloud Agents stay ACTIVE until archive) is not a live RUNNING run and
    must not be used as ``run_status``.
    """
    if not payload:
        return "unknown"
    for key in ("runStatus", "run_status"):
        raw = payload.get(key)
        if raw is None or str(raw).strip() == "":
            continue
        token = normalize_run_status(raw)
        if token in MEMBERSHIP_NOT_LIVENESS:
            continue
        return token
    status = str(payload.get("status") or "").strip()
    if not status:
        return "unknown"
    token = normalize_run_status(status)
    if token in MEMBERSHIP_NOT_LIVENESS:
        return "unknown"
    return token


def context_snippet(payload: dict[str, Any], limit: int = 240) -> str:
    """One-line SDK result/context for A2A pings. Prefer run.result over summary."""
    raw = payload.get("result")
    if raw is None or str(raw).strip() == "":
        raw = payload.get("summary")
    text = " ".join(str(raw or "").split())
    if not text:
        return ""
    if len(text) <= limit:
        return text
    if limit <= 1:
        return "…"[:limit]
    return text[: limit - 1] + "…"


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
    """Stamp waiter_pid on the row's owning seat.

    Prefer an explicit seat, then the seat that already registered this
    bc-id. Do not silently fork a second row onto the env default
    (ops/floor) when Extra High was registered on GCS_DIRECTOR_SEAT=cloud.
    """
    seat_name = (seat or "").strip() or None
    if seat_name is None:
        hit = find_by_bc(bc_id)
        if hit is not None:
            seat_name = hit[0]
    path = fleet_path(seat_name)
    entries = load_entries(path)
    for entry in entries:
        if entry.get("bc_id") == bc_id:
            entry["waiter_pid"] = waiter_pid
            entry["waiter_tombstone"] = False
            entry["updated_at"] = _now()
            write_entries(path, entries)
            return
    register(bc_id, seat=seat_name, waiter_pid=waiter_pid)


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
    return normalize_run_status(
        entry.get("run_status") or entry.get("runStatus") or ""
    )


def is_leftover_shell(
    entry: dict[str, Any],
    payload: dict[str, Any] | None = None,
) -> bool:
    """Skip ACTIVE+FINISHED leftover Cloud membership, not a live worker.

    Agent ``status`` stays ACTIVE until archive. A notified closed ledger
    row, or a row whose latest run is already FINISHED, must not be probed
    with get_agent_run (hourly cap + looks like spinning workers). Open
    leftover shells stay on the ledger; is_closed_leftover prune is separate.
    """
    if entry.get("notified") and entry.get("status") == "closed":
        return True
    run_status = ""
    if payload is not None:
        token = run_status_from_payload(payload)
        if token != "unknown":
            run_status = token
    if not run_status:
        run_status = _latest_run_status(entry)
    return run_status.upper() == "FINISHED"


def is_closed_leftover(entry: dict[str, Any]) -> bool:
    """True when a leftover fleet.jsonl row is already closed.

    Closed leftover: notified, ledger status closed, and latest run is
    FINISHED/ERROR/CANCELLED/EXPIRED (US CANCELED → CANCELLED). Open leftover
    shells (ACTIVE + FINISHED, not yet notified) stay on the ledger. Ledger
    fields only; this does not probe Cursor Cloud, cancel a run, or A2A-ping.
    """
    if not entry.get("notified"):
        return False
    if entry.get("status") != "closed":
        return False
    return _latest_run_status(entry) in TERMINAL


def _prune_record(seat: str, entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "seat": seat,
        "bc_id": entry.get("bc_id"),
        "run_status": str(entry.get("run_status") or entry.get("runStatus") or ""),
    }


def _seat_dirs(seat: str | None = None, *, state: Path | None = None) -> list[Path]:
    root = state or _state()
    if seat:
        path = root / seat
        return [path] if path.is_dir() else []
    if not root.is_dir():
        return []
    return [
        path
        for path in sorted(root.iterdir())
        if path.is_dir() and not path.name.startswith(".")
    ]


def prune_closed_leftovers(
    *,
    seat: str | None = None,
    dry_run: bool = False,
    state: Path | None = None,
) -> dict[str, Any]:
    """Drop closed leftover rows from fleet.jsonl. Ledger-only; no API probe."""
    empty: dict[str, Any] = {
        "dry_run": dry_run,
        "pruned_count": 0,
        "kept_count": 0,
        "pruned": [],
    }
    root = state or _state()
    if seat:
        seat_path = root / seat
        if not seat_path.is_dir():
            return {**empty, "error": f"unknown seat={seat}"}
    pruned: list[dict[str, Any]] = []
    kept_count = 0
    for seat_dir in _seat_dirs(seat, state=root):
        path = seat_dir / "fleet.jsonl"
        entries = load_entries(path)
        if not entries:
            continue
        if dry_run:
            for entry in entries:
                if is_closed_leftover(entry):
                    pruned.append(_prune_record(seat_dir.name, entry))
                else:
                    kept_count += 1
            continue
        if not any(is_closed_leftover(entry) for entry in entries):
            kept_count += len(entries)
            continue
        latest = load_entries(path)
        keep: list[dict[str, Any]] = []
        for entry in latest:
            if is_closed_leftover(entry):
                pruned.append(_prune_record(seat_dir.name, entry))
                continue
            keep.append(entry)
            kept_count += 1
        if len(keep) != len(latest):
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


def _already_notified_by_waiter(entry: dict[str, Any] | None) -> bool:
    if entry is None:
        return False
    return entry.get("notified_by") == "waiter"


def map_github_mergeable(body: dict[str, Any]) -> str | None:
    """Map GitHub REST/GraphQL pull fields to MERGEABLE|CONFLICTING|UNKNOWN.

    REST mergeable_state=dirty is GraphQL mergeable=CONFLICTING (PRs #301/#304).
    """
    raw = body.get("mergeable")
    if isinstance(raw, str):
        token = raw.strip().upper()
        if token in _MERGEABLE_TOKENS:
            return token
    state = str(
        body.get("mergeable_state") or body.get("mergeableState") or ""
    ).strip().lower()
    if state in _CONFLICTING_STATES:
        return "CONFLICTING"
    if raw is False:
        return "CONFLICTING"
    if state in _MERGEABLE_STATES or raw is True:
        return "MERGEABLE"
    return "UNKNOWN"


def _github_pull_json(pr_url: object) -> dict[str, Any] | None:
    """One-shot GET of GitHub pulls API. None if not a PR or lookup failed.

    Do not reuse Extra High get_agent_run 429 backoff (GCS #35).
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
    return body


def github_pr_mergeable(pr_url: object) -> str | None:
    """GET GitHub pulls API. CONFLICTING/MERGEABLE/UNKNOWN, or None on lookup miss."""
    body = _github_pull_json(pr_url)
    if body is None:
        return None
    return map_github_mergeable(body)


def github_pr_is_draft(pr_url: object) -> bool | None:
    """GET GitHub pulls API. True/False when known; None if not a PR or lookup failed."""
    body = _github_pull_json(pr_url)
    if body is None:
        return None
    draft = body.get("draft")
    if draft is True:
        return True
    if draft is False:
        return False
    return None


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
    state = payload.get("mergeableState") or payload.get("mergeable_state")
    if state is None or state == "":
        return None
    mapped = map_github_mergeable(
        {"mergeable": value, "mergeable_state": state, "mergeableState": state}
    )
    return mapped


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


def payload_is_draft(payload: dict[str, Any]) -> bool:
    value = payload.get("draft")
    if value is True:
        return True
    if isinstance(value, str) and value.strip().lower() in {"true", "1", "yes"}:
        return True
    return False


def resolve_draft(payload: dict[str, Any]) -> dict[str, Any]:
    """Honor waiter-supplied draft; otherwise look up GitHub when prUrl is a pull."""
    if payload.get("draft") is not None:
        return payload
    flag = github_pr_is_draft(payload.get("prUrl"))
    if flag is not None:
        payload["draft"] = flag
    return payload


def notify_owner(
    bc_id: str,
    payload: dict[str, Any],
    *,
    notified_by: str = "waiter",
    seat: str | None = None,
) -> dict[str, Any]:
    """A2A-ping the owning seat and REPORT_TO, then mark the ledger closed.

    Idempotent: a second notify on a row already notified_by=waiter returns
    that row and does not ping again (waiter+shepherd must not double-fire
    FLEET_DONE). If any ping fails, the row stays open so fleet-shepherd
    can retry.
    """
    hit = find_by_bc(bc_id)
    seat_name = seat or (hit[0] if hit else _seat_name())
    if hit is not None and _already_notified_by_waiter(hit[1]):
        return hit[1]
    payload = resolve_draft(dict(payload))
    payload = resolve_mergeable(resolve_ship_gate(payload))
    text = notify_text(bc_id, payload)
    for target in notify_targets(seat_name):
        if not ping_seat(target, text):
            raise RuntimeError(f"A2A ping failed seat={target} id={bc_id}")
    return complete(bc_id, payload, notified_by=notified_by, seat=seat_name)


def notify_text(bc_id: str, payload: dict[str, Any]) -> str:
    run_status = run_status_from_payload(payload)
    pr = payload.get("prUrl") or "none"
    name = payload.get("name") or ""
    url = payload.get("url") or f"https://cursor.com/agents/{bc_id}"
    repo = payload.get("repoUrl") or "none"
    ctx = context_snippet(payload)
    extra = f" context={ctx}" if ctx else ""
    mergeable = payload_mergeable(payload)
    merge_tag = f" mergeable={mergeable}" if mergeable else ""
    if run_status == "CANCELLED":
        # Latest run aborted. prUrl may still exist from git.branches — not merge-ready.
        return (
            f"FLEET_DONE / INSPECT: Extra High {bc_id} ({name}) "
            f"runStatus=CANCELLED pr={pr} repo={repo} url={url}.{extra} "
            f"Inspect with scripts/cloud/result-cloud-agent.sh {bc_id}; "
            f"follow-up-or-close; do not ignore. RESULT."
        )
    if run_status == "FINISHED":
        if pr_url_or_none(payload.get("prUrl")) is None:
            # Collect JSON prUrl none: leftover of merged shard is CLOSE.
            # No MERGE_REQUEST. No twin Extra High.
            return (
                f"FLEET_DONE / CLOSE: Extra High {bc_id} ({name}) "
                f"runStatus=FINISHED pr=none repo={repo}{merge_tag} url={url}.{extra} "
                f"Collect via scripts/cloud/result-cloud-agent.sh {bc_id}. "
                f"Directors CLOSE; leftover of merged shard is CLOSE; "
                f"do not ping QA MERGE_REQUEST; do not launch a twin Extra High. RESULT."
            )
        if payload_is_draft(payload):
            return (
                f"FLEET_DONE / PR_READY: Extra High {bc_id} ({name}) "
                f"runStatus=FINISHED pr={pr} repo={repo} draft=true{merge_tag} url={url}.{extra} "
                f"Collect via scripts/cloud/result-cloud-agent.sh {bc_id}. "
                f"GitHub PR is draft: do not ping QA MERGE_REQUEST; do not squash. "
                f"RESULT with bc-id + pr."
            )
        if mergeable == "CONFLICTING":
            return (
                f"FLEET_DONE / PR_READY: Extra High {bc_id} ({name}) "
                f"runStatus=FINISHED pr={pr} repo={repo}{merge_tag} url={url}.{extra} "
                f"Collect via scripts/cloud/result-cloud-agent.sh {bc_id}. "
                f"GitHub PR is CONFLICTING: QA HOLD squash; do not ping QA MERGE_REQUEST; "
                f"Extra High rebase only. RESULT with bc-id + pr."
            )
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
                f"runStatus=FINISHED pr={pr} repo={repo} check_runs={check_runs} "
                f"mergeable={mergeable} url={url}.{extra} "
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
                f"runStatus=FINISHED pr={pr} repo={repo}{merge_tag} url={url}.{extra} "
                f"Collect via scripts/cloud/result-cloud-agent.sh {bc_id}. "
                f"HOLD MERGE_REQUEST: empty GitHub leftover-green is not a "
                f"ship-gate. Paste .venv/bin/pytest -q (N passed, N>=1) and "
                f"python3 scripts/secret_scan.py (secret_scan=clean) before "
                f"pinging QA. RESULT with bc-id + pr."
            )
        return (
            f"FLEET_DONE / PR_READY: Extra High {bc_id} ({name}) "
            f"runStatus=FINISHED pr={pr} repo={repo}{merge_tag} url={url}.{extra} "
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
        f"runStatus={run_status} pr={pr} repo={repo}{merge_tag} url={url}.{extra} "
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
    row["run_status"] = run_status_from_payload(payload)
    row["pr_url"] = payload.get("prUrl")
    mergeable = payload_mergeable(payload)
    if mergeable is not None:
        row["mergeable"] = mergeable
    if payload.get("draft") is not None:
        row["draft"] = payload_is_draft(payload)
    snip = context_snippet(payload)
    if snip:
        row["context"] = snip
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
    prn = sub.add_parser(
        "prune",
        help="drop closed leftover fleet.jsonl rows",
        description=(
            "Drop leftover fleet.jsonl rows that are already closed "
            "(notified, status=closed, latest run "
            "FINISHED/ERROR/CANCELLED/EXPIRED). Open leftover shells stay. "
            "Ledger-only; no Cloud probe or A2A ping. Default rewrites every "
            "seat; pass --dry-run first."
        ),
    )
    prn.add_argument("--seat", default="", help="limit to one seat directory")
    prn.add_argument(
        "--dry-run",
        action="store_true",
        help="report rows that would be dropped without rewriting",
    )
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
        return 1 if result.get("error") else 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
