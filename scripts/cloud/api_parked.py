#!/usr/bin/env python3
"""Detect CLOUD_API_PARKED so Extra High create can fail closed.

Sources (first match):
  env            CLOUD_API_PARKED truthy
  state          $GCS_A2A_STATE/CLOUD_API_PARKED (PALEMON_A2A_STATE alias)
  hive-beats     $GCS_HIVE_BEATS/CLOUD_API_PARKED,
                 $GCS_STUDIO_ARCHIVE/hive-beats/CLOUD_API_PARKED,
                 or $GCS_A2A_STATE/hive-beats/CLOUD_API_PARKED

Exit 0 and print ``CLOUD_API_PARKED source=…`` when parked.
Exit 1 when not parked. Never recommends a Bot CloudAgent path.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

MARKER_NAME = "CLOUD_API_PARKED"
FALSEY = frozenset({"", "0", "false", "no", "off", "unparked", "unset"})


def _truthy_park_env(raw: str | None) -> bool:
    text = (raw if raw is not None else os.environ.get("CLOUD_API_PARKED") or "")
    folded = text.strip().lower()
    return bool(folded) and folded not in FALSEY


def state_dir() -> Path | None:
    for key in ("GCS_A2A_STATE", "PALEMON_A2A_STATE"):
        raw = (os.environ.get(key) or "").strip()
        if raw:
            return Path(raw)
    root = (os.environ.get("GCS_ROOT") or "").strip()
    if root:
        return Path(root) / ".a2a-state"
    return None


def state_marker_paths() -> list[Path]:
    root = state_dir()
    if root is None:
        return []
    return [root / MARKER_NAME]


def hive_beats_dirs() -> list[Path]:
    dirs: list[Path] = []
    hive = (os.environ.get("GCS_HIVE_BEATS") or "").strip()
    if hive:
        dirs.append(Path(hive))
    archive = (os.environ.get("GCS_STUDIO_ARCHIVE") or "").strip()
    if archive:
        dirs.append(Path(archive) / "hive-beats")
    root = state_dir()
    if root is not None:
        dirs.append(root / "hive-beats")
        if not archive:
            dirs.append(root / "studio-archive" / "hive-beats")
    return dirs


def hive_beats_marker_paths() -> list[Path]:
    return [folder / MARKER_NAME for folder in hive_beats_dirs()]


def _is_marker_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def parked_source() -> str | None:
    """Return env, state, or hive-beats when parked; None otherwise."""
    if _truthy_park_env(None):
        return "env"
    if any(_is_marker_file(path) for path in state_marker_paths()):
        return "state"
    if any(_is_marker_file(path) for path in hive_beats_marker_paths()):
        return "hive-beats"
    return None


def parked() -> bool:
    return parked_source() is not None


def main() -> int:
    source = parked_source()
    if source is None:
        return 1
    print(f"CLOUD_API_PARKED source={source}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OSError as exc:
        print(f"error: CLOUD_API_PARKED probe failed: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
