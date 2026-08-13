#!/usr/bin/env python3
"""Shared Grok Cloud Studio A2A / ACP seat helpers. Stdlib only.

Seats, skip list, and ACP ports come from docs/a2a/registry.json so this
control plane is not bound to any one product repo.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

HUB_PORT = int(os.environ.get("GCS_A2A_PORT", "8732"))
GROK_DEFAULT_ACP_PORT = 2419
ACP_PORT_BASE = int(os.environ.get("GCS_ACP_PORT_BASE", "8740"))


def env_first(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return default


def repo_root() -> Path:
    env = env_first("GCS_ROOT")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2]


def state_root(root: Path | None = None) -> Path:
    env = env_first("GCS_A2A_STATE")
    if env:
        return Path(env)
    return (root or repo_root()) / ".a2a-state"


def registry_path(root: Path | None = None) -> Path:
    env = env_first("GCS_A2A_REGISTRY")
    if env:
        return Path(env)
    return (root or repo_root()) / "docs" / "a2a" / "registry.json"


def load_registry(root: Path | None = None) -> dict[str, Any]:
    path = registry_path(root)
    if not path.is_file():
        return {
            "version": "1.0.0",
            "hub": f"http://127.0.0.1:{HUB_PORT}",
            "skipSeats": [],
            "seats": {},
        }
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_seat(seat: str) -> str:
    return seat.strip().lower().replace("_", "-")


def _seat_entries(root: Path | None = None) -> dict[str, dict[str, Any]]:
    raw = load_registry(root).get("seats") or {}
    out: dict[str, dict[str, Any]] = {}
    if isinstance(raw, dict):
        for name, meta in raw.items():
            key = normalize_seat(str(name))
            out[key] = meta if isinstance(meta, dict) else {}
    return out


def skip_seats(root: Path | None = None) -> frozenset[str]:
    extra = env_first("GCS_SKIP_SEATS")
    names = [normalize_seat(s) for s in extra.split(",") if s.strip()] if extra else []
    raw = load_registry(root).get("skipSeats") or []
    if isinstance(raw, list):
        names.extend(normalize_seat(str(s)) for s in raw)
    return frozenset(n for n in names if n)


def launch_seats(root: Path | None = None) -> tuple[str, ...]:
    skipped = skip_seats(root)
    ordered = tuple(name for name in _seat_entries(root) if name not in skipped)
    env_list = env_first("GCS_ACP_SEATS")
    if env_list:
        wanted = [normalize_seat(s) for s in env_list.split(",") if s.strip()]
        known = set(ordered)
        return tuple(s for s in wanted if s in known)
    return ordered


def seat_acp_port(seat: str, root: Path | None = None) -> int:
    key = normalize_seat(seat)
    entries = _seat_entries(root)
    if key not in entries:
        raise KeyError(f"unknown seat: {seat}")
    meta = entries[key]
    if "acpPort" in meta:
        return int(meta["acpPort"])
    idx = list(entries).index(key)
    return ACP_PORT_BASE + idx


def seat_dir(seat: str, root: Path | None = None) -> Path:
    return state_root(root) / normalize_seat(seat)


def status_is_zombie(text: str) -> bool:
    for line in text.splitlines():
        if line.startswith("State:"):
            parts = line.split()
            return len(parts) > 1 and parts[1].startswith("Z")
    return False


def pid_alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    status_path = Path(f"/proc/{pid}/status")
    try:
        text = status_path.read_text(encoding="utf-8", errors="replace")
        if status_is_zombie(text):
            return False
    except OSError:
        pass
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_pid(path: Path) -> int | None:
    if not path.is_file():
        return None
    try:
        raw = path.read_text(encoding="utf-8").strip().split()[0]
        return int(raw)
    except (ValueError, IndexError, OSError):
        return None


def lock_held(path: Path) -> bool:
    return pid_alive(read_pid(path))


def acquire_lock(path: Path) -> bool:
    if lock_held(path):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{os.getpid()}\n", encoding="utf-8")
    return True


def release_lock(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def daemon_healthy(seat_path: Path) -> bool:
    if not pid_alive(read_pid(seat_path / "daemon.pid")):
        return False
    url_path = seat_path / "acp.url"
    if not url_path.is_file():
        return False
    try:
        return bool(url_path.read_text(encoding="utf-8").strip())
    except OSError:
        return False


def compose_extra(task_id: str | None, context: str | None, message: str | None) -> str:
    return (
        f"A2A_TASK_ID={task_id or 'none'}\n"
        f"A2A_CONTEXT={context or 'none'}\n"
        f"MESSAGE:\n{message or ''}\n"
    )


def message_text(record: dict) -> str:
    for part in record.get("parts") or []:
        if isinstance(part, dict) and part.get("text"):
            return str(part["text"])
    if record.get("text"):
        return str(record["text"])
    return ""


def default_poll_seats(root: Path | None = None) -> list[str]:
    seats = list(launch_seats(root))
    for skipped in sorted(skip_seats(root)):
        if skipped not in seats:
            seats.append(skipped)
    return seats


def cloud_repo_url() -> str:
    """Target git repo for Extra High creates. Fail closed if unset."""
    url = env_first("GCS_CLOUD_REPO", "CLOUD_REPO_URL", "CURSOR_CLOUD_REPO")
    if not url:
        raise RuntimeError(
            "CLOUD_BLOCKED: set GCS_CLOUD_REPO or CLOUD_REPO_URL "
            "(git URL of the repo Extra High should open PRs against)"
        )
    return url


def cloud_repo_ref() -> str:
    return env_first("GCS_CLOUD_REF", "CLOUD_REPO_REF", "CURSOR_CLOUD_REF", default="main")


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(
            "usage: lib.py <launch-seats|skip-seats|port SEAT|normalize SEAT|"
            "root|state|registry|cloud-repo|cloud-ref>",
            file=sys.stderr,
        )
        return 2
    cmd = argv[0]
    if cmd == "launch-seats":
        print("\n".join(launch_seats()))
        return 0
    if cmd == "skip-seats":
        print("\n".join(sorted(skip_seats())))
        return 0
    if cmd == "port":
        if len(argv) < 2:
            print("usage: lib.py port SEAT", file=sys.stderr)
            return 2
        print(seat_acp_port(argv[1]))
        return 0
    if cmd == "normalize":
        if len(argv) < 2:
            print("usage: lib.py normalize SEAT", file=sys.stderr)
            return 2
        print(normalize_seat(argv[1]))
        return 0
    if cmd == "root":
        print(repo_root())
        return 0
    if cmd == "state":
        print(state_root())
        return 0
    if cmd == "registry":
        print(registry_path())
        return 0
    if cmd == "cloud-repo":
        try:
            print(cloud_repo_url())
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        return 0
    if cmd == "cloud-ref":
        print(cloud_repo_ref())
        return 0
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
