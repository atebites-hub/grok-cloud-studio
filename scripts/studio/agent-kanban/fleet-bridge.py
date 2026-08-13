#!/usr/bin/env python3
"""Sync-only Agent Kanban observer for Extra High fleet rows.

Watches `.a2a-state/*/fleet.jsonl` and `.a2a-state/agent-kanban/events.jsonl`,
mirrors bc-ids to AK Tasks, and records `.a2a-state/kanban/task-map.json (mirrored under agent-kanban/)`.

Does not spawn workers. Must never invoke `ak start` — Extra High remains the
grunt spawner. Directors stay on ACP serve + A2A hub.

Local studio only. Stdlib. Never prints API keys.

Prefer running under scripts/studio/agent-kanban/board-writer.sh so
argv0=cursor-agent + CURSOR_AGENT=1 satisfy ak leader ancestry
(direct CLI may 403 / fail ancestry).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

def env_first(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return default


ROOT = Path(env_first("GCS_ROOT") or Path(__file__).resolve().parents[3])
STATE_DIR = Path(env_first("GCS_A2A_STATE") or str(ROOT / ".a2a-state"))
SKIP_SEATS = frozenset({"agent-kanban", "kanban", "dashboard", "waiters"})
CREATED_ID_RE = re.compile(
    r"(?:Created (?:task|board)|Added repository)\s+(\S+)",
    re.IGNORECASE,
)

AK_TODO = "todo"
AK_IN_PROGRESS = "in_progress"
AK_IN_REVIEW = "in_review"
AK_DONE = "done"
AK_CANCELLED = "cancelled"

DRY_RUN = False
FORCE = False


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ak_state_dir(state_dir: Path | None = None) -> Path:
    """Primary observer state: .a2a-state/kanban (legacy agent-kanban mirrored)."""
    state = Path(state_dir or STATE_DIR)
    kanban = state / "kanban"
    legacy = state / "agent-kanban"
    kanban.mkdir(parents=True, exist_ok=True)
    legacy.mkdir(parents=True, exist_ok=True)
    return kanban


def legacy_ak_state_dir(state_dir: Path | None = None) -> Path:
    return Path(state_dir or STATE_DIR) / "agent-kanban"


def normalize_bc(raw: Any) -> str:
    text = str(raw or "").strip()
    if text.startswith("bc_"):
        return "bc-" + text[3:]
    return text


def load_jsonl(path: Path) -> list[dict[str, Any]]:
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
        if isinstance(rec, dict):
            out.append(rec)
    return out


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def desired_ak_status(record: dict[str, Any]) -> str:
    """Map Extra High ledger / observer event → AK column.

    launch/open → todo; ACTIVE → in_progress; PR → in_review;
    FINISHED/MERGED → done; ERROR/CANCELLED → cancelled (when supported).
    """
    event = str(record.get("event") or "").strip().lower()
    run_status = str(
        record.get("run_status") or record.get("runStatus") or ""
    ).strip().upper()
    ledger = str(record.get("status") or "").strip().lower()
    pr_url = record.get("pr_url") or record.get("prUrl") or ""
    if str(pr_url).lower() in {"", "none", "null"}:
        pr_url = ""

    if run_status in {"ERROR", "CANCELLED", "EXPIRED"} or event in {
        "error",
        "cancelled",
        "cancel",
        "expired",
    }:
        return AK_CANCELLED
    if run_status in {"FINISHED", "MERGED"} or event in {"finished", "merged", "done"}:
        return AK_DONE
    if pr_url or event in {"pr", "in_review", "review"}:
        return AK_IN_REVIEW
    if run_status == "ACTIVE" or event in {"active", "in_progress", "launched", "launch"}:
        return AK_IN_PROGRESS
    # launched / open ledger rows are in progress for mission-control UI
    if ledger in {"open", "active", "running"} or event in {"todo", "open"}:
        return AK_IN_PROGRESS
    return AK_IN_PROGRESS


def collect_records(state_dir: Path) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for fleet in sorted(Path(state_dir).glob("*/fleet.jsonl")):
        seat = fleet.parent.name
        if seat in SKIP_SEATS:
            continue
        for entry in load_jsonl(fleet):
            bc_id = normalize_bc(entry.get("bc_id"))
            if not bc_id:
                continue
            rec = dict(entry)
            rec["bc_id"] = bc_id
            rec["seat"] = rec.get("seat") or seat
            by_id[bc_id] = rec
    event_paths = [
        ak_state_dir(state_dir) / "events.jsonl",
        legacy_ak_state_dir(state_dir) / "events.jsonl",
    ]
    seen_paths: set[str] = set()
    for ep in event_paths:
        key = str(ep.resolve()) if ep.exists() else str(ep)
        if key in seen_paths:
            continue
        seen_paths.add(key)
        for event in load_jsonl(ep):
            bc_id = normalize_bc(event.get("bc_id"))
            if not bc_id:
                continue
            rec = dict(by_id.get(bc_id) or {"bc_id": bc_id})
            for key_name, value in event.items():
                if value is None or value == "":
                    continue
                rec[key_name] = value
            rec["bc_id"] = bc_id
            by_id[bc_id] = rec
    return by_id


def load_board_id(state_dir: Path) -> str:
    for key in ("AGENT_KANBAN_BOARD_ID", "GCS_AGENT_KANBAN_BOARD_ID"):
        env_id = str(os.environ.get(key) or "").strip()
        if env_id:
            return env_id
    state = Path(state_dir)
    for path in (
        ak_state_dir(state) / "board.json",
        legacy_ak_state_dir(state) / "board.json",
        ak_state_dir(state) / "board.id",
        legacy_ak_state_dir(state) / "board.id",
    ):
        if not path.is_file():
            continue
        if path.suffix == ".id":
            bid = path.read_text(encoding="utf-8").strip()
            if bid:
                return bid
            continue
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict):
            bid = str(rec.get("board_id") or rec.get("id") or "")
            if bid:
                return bid
    return ""


def load_task_map(state_dir: Path) -> dict[str, dict[str, Any]]:
    path = ak_state_dir(state_dir) / "task-map.json"
    if not path.is_file():
        path = legacy_ak_state_dir(state_dir) / "task-map.json"
    if not path.is_file():
        return {}
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(rec, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for key, value in rec.items():
        if isinstance(value, dict):
            out[str(key)] = value
    return out


def ak_bin() -> str:
    env = os.environ.get("AK_BIN")
    if env:
        return env
    home = Path.home()
    for cand in (
        home / ".local" / "bin" / "ak",
        home / ".local" / "lib" / "node_modules" / "agent-kanban" / "dist" / "index.js",
    ):
        if cand.exists():
            return str(cand)
    return "ak"


def parse_created_id(stdout: str) -> str:
    text = (stdout or "").strip()
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict) and rec.get("id"):
                return str(rec["id"])
    match = CREATED_ID_RE.search(text)
    if match:
        return match.group(1).rstrip(":")
    return ""


def run_ak(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    if args and args[0] == "start":
        raise RuntimeError("observer bridge must not run ak start")
    cmd = [ak_bin(), *args]
    try:
        return subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return subprocess.CompletedProcess(cmd, 127, "", "ak not found")
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 124, "", "ak timeout")


def task_title(record: dict[str, Any]) -> str:
    seat = str(record.get("seat") or "fleet")
    name = str(record.get("name") or "").strip()
    bc_id = str(record.get("bc_id") or "")
    label = name or bc_id
    return f"[{seat}] Extra High {label}"


def task_description(record: dict[str, Any]) -> str:
    bc_id = str(record.get("bc_id") or "")
    seat = str(record.get("seat") or "")
    url = str(record.get("url") or (f"https://cursor.com/agents/{bc_id}" if bc_id else ""))
    pr = str(record.get("pr_url") or record.get("prUrl") or "")
    lines = [
        "Sync-only observer mirror of a Cursor Cloud Extra High grunt.",
        "Directors stay on Grok Build ACP serve; A2A hub routes work; Extra High is the worker.",
        "Do not treat this AK task as a worker spawn. The AK worker daemon is not used.",
        f"bc_id={bc_id}",
        f"seat={seat}",
        f"url={url}",
    ]
    if pr and pr.lower() not in {"none", "null"}:
        lines.append(f"pr={pr}")
    return "\n".join(lines)



def is_placeholder_task_id(task_id: str) -> bool:
    """dry-* ids from --dry-run are not real board tasks."""
    tid = str(task_id or "").strip()
    return (not tid) or tid.startswith("dry-")


def redact_ak_text(blob: str) -> str:
    """Strip likely secrets from ak stdout/stderr before logging."""
    text = str(blob or "")
    text = re.sub(r"(?i)(api[_-]?key|authorization|bearer)\s*[:=]\s*\S+", r"\1=[REDACTED]", text)
    text = re.sub(r'(?i)("api_key"\s*:\s*")([^"]+)(")', r"\1[REDACTED]\3", text)
    return text.strip()


def create_task(board_id: str, record: dict[str, Any]) -> str:
    seat = str(record.get("seat") or "fleet")
    if DRY_RUN:
        fake = f"dry-{normalize_bc(record.get('bc_id'))[:24]}"
        print(f"AK_BRIDGE_DRY create board={board_id} title={task_title(record)!r} -> {fake}")
        return fake
    args = [
        "create",
        "task",
        "--board",
        board_id,
        "--title",
        task_title(record),
        "--description",
        task_description(record),
        # Only well-known labels — seat names (e.g. studio-ops) are not board labels.
        "--labels",
        "extra-high",
        "-o",
        "json",
    ]
    proc = run_ak(args)
    if proc.returncode != 0:
        err = redact_ak_text((proc.stderr or "") + "\n" + (proc.stdout or ""))
        print(
            f"AK_BRIDGE_ERR create failed id={record.get('bc_id')} rc={proc.returncode} err={err[:500]}",
            file=sys.stderr,
        )
        return ""
    tid = parse_created_id(proc.stdout) or parse_created_id(proc.stderr)
    if not tid:
        err = redact_ak_text((proc.stderr or "") + "\n" + (proc.stdout or ""))
        print(
            f"AK_BRIDGE_ERR create parse_id_empty id={record.get('bc_id')} out={err[:300]}",
            file=sys.stderr,
        )
    return tid


def apply_status(task_id: str, current: str, desired: str, pr_url: str = "") -> str:
    """Best-effort lifecycle walk. Returns the status we believe we reached."""
    if not task_id or current == desired:
        return current or desired
    if DRY_RUN:
        print(f"AK_BRIDGE_DRY status task={task_id} {current or 'todo'}->{desired} pr={pr_url or 'none'}")
        return desired
    if desired == AK_CANCELLED:
        proc = run_ak(["task", "cancel", task_id])
        return AK_CANCELLED if proc.returncode == 0 else current
    if desired == AK_TODO and current != AK_TODO:
        proc = run_ak(["task", "release", task_id])
        return AK_TODO if proc.returncode == 0 else current

    reached = current or AK_TODO
    if reached == AK_TODO and desired in {AK_IN_PROGRESS, AK_IN_REVIEW, AK_DONE}:
        proc = run_ak(["task", "claim", task_id])
        if proc.returncode == 0:
            reached = AK_IN_PROGRESS
        elif desired == AK_IN_PROGRESS:
            return reached
    if reached == AK_IN_PROGRESS and desired in {AK_IN_REVIEW, AK_DONE}:
        cmd = ["task", "review", task_id]
        if pr_url:
            cmd.extend(["--pr-url", pr_url])
        proc = run_ak(cmd)
        if proc.returncode == 0:
            reached = AK_IN_REVIEW
        elif desired == AK_IN_REVIEW:
            return reached
    if desired == AK_DONE and reached in {AK_IN_REVIEW, AK_IN_PROGRESS, AK_TODO}:
        proc = run_ak(["task", "complete", task_id])
        if proc.returncode == 0:
            reached = AK_DONE
    return reached


def sync_once(state_dir: Path | None = None) -> dict[str, dict[str, Any]]:
    state = Path(state_dir or STATE_DIR)
    board_id = load_board_id(state)
    if not board_id:
        if DRY_RUN:
            board_id = "dry-board"
            print("AK_BRIDGE_DRY missing board_id; using dry-board")
        else:
            print("AK_BRIDGE_ERR missing board_id (run bootstrap-board.sh)", file=sys.stderr)
            return {}
    records = collect_records(state)
    task_map = load_task_map(state)
    created = 0
    updated = 0
    for bc_id, record in sorted(records.items()):
        desired = desired_ak_status(record)
        pr_url = str(record.get("pr_url") or record.get("prUrl") or "")
        if pr_url.lower() in {"none", "null"}:
            pr_url = ""
        row = dict(task_map.get(bc_id) or {})
        task_id = str(row.get("task_id") or "")
        current = str(row.get("ak_status") or "")
        # dry-* placeholders are not real; recreate unless DRY_RUN.
        if is_placeholder_task_id(task_id) and not DRY_RUN:
            if FORCE or str(task_id).startswith("dry-"):
                print(f"AK_BRIDGE_RECREATE placeholder task_id={task_id!r} bc_id={bc_id}")
                task_id = ""
                current = ""
        if not task_id:
            task_id = create_task(board_id, record)
            if not task_id:
                continue
            created += 1
            current = AK_TODO
        reached = apply_status(task_id, current or AK_TODO, desired, pr_url=pr_url)
        if reached != current:
            updated += 1
        task_map[bc_id] = {
            "task_id": task_id,
            "ak_status": reached,
            "seat": record.get("seat") or row.get("seat") or "",
            "title": task_title(record),
            "pr_url": pr_url or None,
            "updated_at": now_iso(),
        }
    atomic_write_json(ak_state_dir(state) / "task-map.json", task_map)
    atomic_write_json(legacy_ak_state_dir(state) / "task-map.json", task_map)
    print(f"AK_BRIDGE_SYNC agents={len(records)} created={created} updated={updated}")
    return task_map


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Observer bridge: Extra High fleet → Agent Kanban tasks (never ak start)."
    )
    parser.add_argument("--once", action="store_true", help="One sync pass then exit (smoke).")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Treat dry-* task-map placeholders as missing and recreate real tasks.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan creates/status transitions without calling ak mutate APIs.",
    )
    parser.add_argument(
        "--poll-sec",
        type=float,
        default=float(env_first("GCS_AK_POLL_SEC", "AK_BRIDGE_POLL_SEC", "GCS_AK_BRIDGE_POLL_SEC", default="60") or "60"),
        help="Watch interval when not --once.",
    )
    args = parser.parse_args(argv)
    global DRY_RUN, FORCE
    DRY_RUN = bool(args.dry_run) or str(os.environ.get("GCS_AK_DRY", "")).strip() in {"1", "true", "yes"}
    FORCE = bool(args.force) or str(os.environ.get("GCS_AK_FORCE", "")).strip() in {"1", "true", "yes"}
    state = STATE_DIR
    ak_state_dir(state).mkdir(parents=True, exist_ok=True)
    legacy_ak_state_dir(state).mkdir(parents=True, exist_ok=True)
    # Ensure local ak shims are visible when PATH is thin post-crash.
    local_bin = str(Path.home() / ".local" / "bin")
    os.environ["PATH"] = local_bin + os.pathsep + os.environ.get("PATH", "")
    if args.once:
        sync_once(state)
        return 0
    print(f"AK_BRIDGE_WATCH state={state} poll={args.poll_sec} (observer; never ak start)")
    while True:
        try:
            sync_once(state)
        except Exception as exc:  # noqa: BLE001 — keep the watcher alive
            print(f"AK_BRIDGE_ERR cycle {exc}", file=sys.stderr)
        time.sleep(max(1.0, float(args.poll_sec)))


if __name__ == "__main__":
    raise SystemExit(main())
