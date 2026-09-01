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

SHIPPED_PROMPTS = Path("prompts")
DOCS_PROMPTS = Path("docs") / "studio" / "directors"
DIRECTOR_PROMPT_GLOB = "*_director_prompt.txt"
_SEAT_PROMPT_ALIASES = {
    "floor-ops": "floor",
    "floor": "floor-ops",
    "studio-ops": "ops",
    "ops": "studio-ops",
}

# CCGS lead titles fold onto first-class GCS seats. Audio and narrative are
# first-class (not aliases). Do not map the 49-specialist roster.
CCGS_LEAD_ALIASES = {
    "producer": "floor-ops",
    "creative": "floor",
    "technical": "systems",
    "game-designer": "content",
    "lead-programmer": "systems",
    "art-director": "art",
    "qa-lead": "qa-a",
    "release-manager": "studio-ops",
}


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


def canonical_seat(seat: str, root: Path | None = None) -> str:
    """Map aliases onto a registry seat name when the token is missing.

    First-class registry names win. `studio-ops` / `floor-ops` stay themselves
    when present; they only fold onto `ops` / `floor` on extract registries
    that still ship the short names.
    """
    key = normalize_seat(seat)
    entries = _seat_entries(root)
    if key in entries:
        return key
    aliases = {
        "studio-ops": "ops",
        "ops": "studio-ops",
        "floor-ops": "floor",
        "floor": "floor-ops",
        **CCGS_LEAD_ALIASES,
    }
    alt = aliases.get(key)
    if alt and alt in entries:
        return alt
    return key


def grow_seats(root: Path | None = None) -> frozenset[str]:
    """GROW inbox owners: persistent serve + wake-daemon, not leftover dispatch.

    Default GCS_GROW_SEATS / GCS_ACP_SEATS is floor,studio-ops. The example
    registry names ops `ops`; both aliases are included so dispatch skip and
    wake loops agree. CCGS lead titles fold onto first-class hive seats.
    """
    raw = env_first("GCS_GROW_SEATS", "GCS_ACP_SEATS", default="floor,studio-ops")
    skipped = skip_seats(root)
    known = set(_seat_entries(root))
    out: set[str] = set()
    for part in raw.split(","):
        token = part.strip()
        if not token:
            continue
        key = canonical_seat(token, root)
        if not key or key in skipped:
            continue
        if key in known:
            out.add(key)
    if "studio-ops" in out and "ops" in known and "ops" not in skipped:
        out.add("ops")
    if "ops" in out and "studio-ops" in known and "studio-ops" not in skipped:
        out.add("studio-ops")
    return frozenset(out)


def mind_seats(root: Path | None = None) -> frozenset[str]:
    """Opt-in Grok Build mind seats (GCS_MIND_SEATS, default empty).

    Example: GCS_MIND_SEATS=floor,ops. Palemon-floor wipe uses the
    first-class seats in studio.env.example (directors, CCGS leads including
    audio and narrative; not 49 specialists). skipSeats (orchestrator, donald)
    never join this set. Names missing from the registry are ignored.
    """
    raw = env_first("GCS_MIND_SEATS")
    if not raw:
        return frozenset()
    skipped = skip_seats(root)
    known = set(_seat_entries(root))
    out: set[str] = set()
    for part in raw.split(","):
        token = part.strip()
        if not token:
            continue
        key = canonical_seat(token, root)
        if not key or key in skipped:
            continue
        if key in known:
            out.add(key)
    return frozenset(out)


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


def hive_seats(root: Path | None = None) -> tuple[str, ...]:
    """Leftover launch map: first-class registry seats minus skipSeats.

    Independent of GCS_ACP_SEATS (crash-safe grok agent serve cap). Audio and
    narrative stay here as first-class CCGS leads. Do not mint the
    49-specialist roster.
    """
    skipped = skip_seats(root)
    return tuple(name for name in _seat_entries(root) if name not in skipped)


def launch_seats(root: Path | None = None) -> tuple[str, ...]:
    ordered = hive_seats(root)
    env_list = env_first("GCS_ACP_SEATS")
    if env_list:
        wanted = [canonical_seat(s, root) for s in env_list.split(",") if s.strip()]
        known = set(ordered)
        seen: set[str] = set()
        out: list[str] = []
        for s in wanted:
            if s in known and s not in seen:
                seen.add(s)
                out.append(s)
        return tuple(out)
    return ordered


def seat_acp_port(seat: str, root: Path | None = None) -> int:
    key = canonical_seat(seat, root)
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
        "Keep-alive / status turn: do work, do not idle. Tools are allowed. "
        "RESULT is duplex, not success. If you print one, use exactly: "
        "RESULT bc-id=<id or none> pr=<url or none> a2a=<task-id or none> notes=<one line>. "
        "RESULT-only / PONG is a bug. Remain this seat. "
        "Do not send.sh / a2a_send to ack the caller — duplex notifies.\n"
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
    seats = list(hive_seats(root))
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


def director_prompt_filename(seat: str) -> str:
    return f"{normalize_seat(seat).replace('-', '_')}_director_prompt.txt"


def director_prompt_filenames(seat: str, root: Path | None = None) -> tuple[str, ...]:
    key = normalize_seat(seat)
    names: list[str] = [director_prompt_filename(key)]
    canon = director_prompt_filename(canonical_seat(seat, root))
    if canon not in names:
        names.append(canon)
    alias = _SEAT_PROMPT_ALIASES.get(key)
    if alias:
        extra = director_prompt_filename(alias)
        if extra not in names:
            names.append(extra)
    return tuple(names)


def _dir_has_director_prompts(path: Path) -> bool:
    if not path.is_dir():
        return False
    try:
        next(path.glob(DIRECTOR_PROMPT_GLOB))
    except StopIteration:
        return False
    return True


def prompt_search_dirs(root: Path | None = None) -> tuple[Path, ...]:
    root = root or repo_root()
    dirs: list[Path] = []
    override = env_first("GCS_PROMPT_DIR", "PROMPTS_DIR")
    if override:
        dirs.append(Path(override).expanduser())
    for rel in (SHIPPED_PROMPTS, DOCS_PROMPTS):
        candidate = root / rel
        if candidate not in dirs:
            dirs.append(candidate)
    return tuple(dirs)


def prompts_dir(root: Path | None = None) -> Path:
    """Default director-prompt directory.

    GCS_PROMPT_DIR / PROMPTS_DIR override. Otherwise use $ROOT/prompts when it
    contains *_director_prompt.txt; if that dir is missing or empty, use
    $ROOT/docs/studio/directors (product-floor layout).
    """
    root = root or repo_root()
    override = env_first("GCS_PROMPT_DIR", "PROMPTS_DIR")
    if override:
        return Path(override).expanduser()
    shipped = root / SHIPPED_PROMPTS
    docs = root / DOCS_PROMPTS
    if _dir_has_director_prompts(shipped):
        return shipped
    if _dir_has_director_prompts(docs):
        return docs
    if shipped.is_dir():
        return shipped
    return docs


def resolve_director_prompt(seat: str, root: Path | None = None) -> Path | None:
    """Locate ${stem}_director_prompt.txt in prompts/ or docs/studio/directors."""
    root = root or repo_root()
    for directory in prompt_search_dirs(root):
        for name in director_prompt_filenames(seat, root):
            candidate = directory / name
            if candidate.is_file():
                return candidate
    return None


def ensure_prompt_links(root: Path | None = None) -> list[Path]:
    """Link docs/studio/directors/*_director_prompt.txt into prompts/ when missing."""
    root = root or repo_root()
    docs = root / DOCS_PROMPTS
    dest_dir = root / SHIPPED_PROMPTS
    created: list[Path] = []
    if not docs.is_dir():
        return created
    for src in sorted(docs.glob(DIRECTOR_PROMPT_GLOB)):
        if not src.is_file():
            continue
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        if dest.exists() or dest.is_symlink():
            continue
        dest.symlink_to(os.path.relpath(src, dest_dir))
        created.append(dest)
    return created


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(
            "usage: lib.py <launch-seats|hive-seats|skip-seats|grow-seats|mind-seats|"
            "port SEAT|normalize SEAT|canonical SEAT|root|state|registry|cloud-repo|"
            "cloud-ref|prompts-dir|prompt-file SEAT|ensure-prompts>",
            file=sys.stderr,
        )
        return 2
    cmd = argv[0]
    if cmd == "launch-seats":
        print("\n".join(launch_seats()))
        return 0
    if cmd == "hive-seats":
        print("\n".join(hive_seats()))
        return 0
    if cmd == "skip-seats":
        print("\n".join(sorted(skip_seats())))
        return 0
    if cmd == "grow-seats":
        print("\n".join(sorted(grow_seats())))
        return 0
    if cmd == "mind-seats":
        print("\n".join(sorted(mind_seats())))
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
    if cmd == "canonical":
        if len(argv) < 2:
            print("usage: lib.py canonical SEAT", file=sys.stderr)
            return 2
        print(canonical_seat(argv[1]))
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
    if cmd == "prompts-dir":
        print(prompts_dir())
        return 0
    if cmd == "prompt-file":
        if len(argv) < 2:
            print("usage: lib.py prompt-file SEAT", file=sys.stderr)
            return 2
        path = resolve_director_prompt(argv[1])
        if path is None:
            name = director_prompt_filename(argv[1])
            print(f"missing prompt: {prompts_dir() / name}", file=sys.stderr)
            return 1
        print(path)
        return 0
    if cmd == "ensure-prompts":
        for path in ensure_prompt_links():
            print(path)
        return 0
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
