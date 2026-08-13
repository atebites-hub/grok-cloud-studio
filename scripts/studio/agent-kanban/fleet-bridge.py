#!/usr/bin/env python3
"""Sync Extra High fleet.jsonl onto Agent Kanban via `ak apply` Task YAML.

Sync-only: never runs `ak start`. Stdlib + subprocess. Logs AK_BRIDGE_* without secrets.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
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


def root() -> Path:
    return Path(env_first("GCS_ROOT") or Path(__file__).resolve().parents[3])


def state_dir() -> Path:
    return Path(env_first("GCS_A2A_STATE") or str(root() / ".a2a-state"))


def ak_dir() -> Path:
    return state_dir() / "agent-kanban"


def ak_bin() -> str:
    return env_first("AGENT_KANBAN_BIN", "GCS_AGENT_KANBAN_BIN", default="ak")


def log(kind: str, **fields: Any) -> None:
    bits = " ".join(f"{key}={val}" for key, val in fields.items() if val is not None)
    print(f"AK_BRIDGE_{kind}" + (f" {bits}" if bits else ""), flush=True)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_map(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_map(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def board_id() -> str:
    path = ak_dir() / "board.id"
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip().splitlines()[0].strip()
    except OSError:
        return ""


def fleet_rows() -> list[tuple[str, dict[str, Any]]]:
    rows: list[tuple[str, dict[str, Any]]] = []
    for path in sorted(state_dir().glob("*/fleet.jsonl")):
        seat = path.parent.name
        if seat == "agent-kanban":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict) and rec.get("bc_id"):
                rows.append((seat, rec))
    return rows


def row_hash(seat: str, rec: dict[str, Any]) -> str:
    payload = {
        "seat": seat,
        "bc_id": rec.get("bc_id"),
        "name": rec.get("name"),
        "status": rec.get("status"),
        "notified": rec.get("notified"),
        "notified_by": rec.get("notified_by"),
        "run_id": rec.get("run_id"),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def yaml_dump(spec: dict[str, Any]) -> str:
    lines = ["kind: Task", "spec:"]
    for key, val in spec.items():
        if isinstance(val, list):
            lines.append(f"  {key}:")
            for item in val:
                lines.append(f"    - {json.dumps(item)}")
        elif val is None:
            continue
        else:
            lines.append(f"  {key}: {json.dumps(val)}")
    return "\n".join(lines) + "\n"


def task_spec(seat: str, rec: dict[str, Any], board: str, task_id: str) -> dict[str, Any]:
    bc_id = str(rec.get("bc_id") or "")
    name = str(rec.get("name") or "")
    status = str(rec.get("status") or "open")
    spec: dict[str, Any] = {
        "boardId": board,
        "title": f"[{seat}] {name or bc_id}".strip(),
        "description": (
            f"Grok Cloud Studio Extra High sync-only mirror.\n"
            f"seat={seat} bc_id={bc_id} status={status} "
            f"notified_by={rec.get('notified_by') or 'none'}"
        ),
        "labels": ["fleet", "extra-high", f"seat-{seat}", f"status-{status}"],
    }
    repo = env_first("GCS_CLOUD_REPO", "CLOUD_REPO_URL", "AGENT_KANBAN_GITHUB_REPO")
    if repo:
        spec["repo"] = repo
    if task_id:
        spec["id"] = task_id
    return spec


TASK_RE = re.compile(r"(?:Created|Updated) task (\S+):", re.I)


def parse_task_id(text: str) -> str:
    match = TASK_RE.search(text)
    if match:
        return match.group(1).strip().rstrip(",")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return ""
    if isinstance(data, dict):
        return str(data.get("id") or "")
    return ""


def apply_yaml(yaml_text: str) -> tuple[int, str]:
    path = ak_dir() / "apply-task.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml_text, encoding="utf-8")
    try:
        proc = subprocess.run(
            [ak_bin(), "apply", "-f", str(path)],
            cwd=str(root()),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, type(exc).__name__
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def run_cycle() -> int:
    board = board_id()
    if not board:
        log("SKIP", reason="no_board")
        return 0
    tmap_path = ak_dir() / "task-map.json"
    tmap = load_map(tmap_path)
    applied = 0
    for seat, rec in fleet_rows():
        bc_id = str(rec.get("bc_id") or "")
        key = f"{seat}:{bc_id}"
        digest = row_hash(seat, rec)
        entry = tmap.get(key) if isinstance(tmap.get(key), dict) else {}
        if entry.get("hash") == digest and entry.get("task_id"):
            log("SKIP", seat=seat, bc=bc_id, reason="unchanged")
            continue
        task_id = str(entry.get("task_id") or "")
        rc, out = apply_yaml(yaml_dump(task_spec(seat, rec, board, task_id)))
        if rc != 0:
            log("FAIL", seat=seat, bc=bc_id, rc=rc)
            continue
        new_id = parse_task_id(out) or task_id
        if not new_id:
            log("FAIL", seat=seat, bc=bc_id, reason="no_task_id")
            continue
        tmap[key] = {"task_id": new_id, "hash": digest, "updated_at": now()}
        save_map(tmap_path, tmap)
        log("APPLY", seat=seat, bc=bc_id, task=new_id)
        applied += 1
    return applied


def main() -> int:
    parser = argparse.ArgumentParser(description="fleet.jsonl → Agent Kanban Task YAML (sync-only)")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    poll = float(env_first("AK_BRIDGE_POLL_SEC", "GCS_AK_BRIDGE_POLL_SEC", default="15") or "15")
    ak_dir().mkdir(parents=True, exist_ok=True)
    log("READY", state=state_dir(), poll=poll, once=int(args.once), sync="only")
    stopping = False

    def _handle(signum: int, _frame: Any) -> None:
        nonlocal stopping
        stopping = True
        log("STOP", signal=signum)

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)
    if args.once:
        run_cycle()
        return 0
    while not stopping:
        run_cycle()
        end = time.time() + poll
        while not stopping and time.time() < end:
            time.sleep(min(0.25, max(0.0, end - time.time())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
