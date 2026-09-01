#!/usr/bin/env python3
"""Count live Extra High workers (runStatus=RUNNING), not leftover ACTIVE shells.

Staff each active GCS_CLOUD_REPO until >= GCS_CLOUD_MIN_RUNNING (default 8)
RUNNING. CREATING is in-flight but not yet RUNNING. ACTIVE+FINISHED leftovers
are not capacity. Directors / cloud mind MUST cloud_launch while below the floor.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

# Path bootstrap so this file can import sibling list_rows.py from tests.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
from list_rows import (
    is_in_flight,
    is_live_worker,
    parse_list_output,
)

DEFAULT_MIN_RUNNING = 8


def min_running(raw: str | None = None) -> int:
    text = (raw if raw is not None else os.environ.get("GCS_CLOUD_MIN_RUNNING") or "").strip()
    if not text:
        return DEFAULT_MIN_RUNNING
    try:
        value = int(text)
    except ValueError:
        return DEFAULT_MIN_RUNNING
    return value if value > 0 else DEFAULT_MIN_RUNNING


def _norm_repo(url: str) -> str:
    text = (url or "").strip().lower()
    if text.startswith("git@github.com:"):
        text = "https://github.com/" + text.split(":", 1)[1]
    if text.endswith(".git"):
        text = text[:-4]
    return text.rstrip("/")


def row_matches_repo(item: dict[str, Any], repo: str | None) -> bool:
    if not (repo or "").strip():
        return True
    wanted = _norm_repo(repo)
    urls: list[str] = []
    for key in ("repo", "url"):
        value = item.get(key)
        if isinstance(value, str) and value.strip() and key == "repo":
            urls.append(value.strip())
    repos = item.get("repos") or []
    if isinstance(repos, list):
        for entry in repos:
            if isinstance(entry, str) and entry.strip():
                urls.append(entry.strip())
            elif isinstance(entry, dict):
                found = str(entry.get("url") or "").strip()
                if found:
                    urls.append(found)
    if not urls:
        return True
    return any(_norm_repo(url) == wanted for url in urls)


def count_running(rows: list[dict[str, Any]], repo: str | None = None) -> int:
    return sum(1 for row in rows if row_matches_repo(row, repo) and is_live_worker(row))


def count_in_flight(rows: list[dict[str, Any]], repo: str | None = None) -> int:
    return sum(1 for row in rows if row_matches_repo(row, repo) and is_in_flight(row))


def must_launch(*, running_count: int, min_running_n: int | None = None) -> bool:
    limit = min_running() if min_running_n is None else min_running_n
    if limit <= 0:
        return False
    return running_count < limit


def must_launch_reason(*, running_count: int, min_running_n: int) -> str:
    if running_count >= min_running_n:
        return "at-min-running"
    return "below-min-running"


def decide(
    *,
    running_count: int,
    min_running_n: int | None = None,
    repo: str = "",
) -> dict[str, Any]:
    limit = min_running() if min_running_n is None else min_running_n
    launch = must_launch(running_count=running_count, min_running_n=limit)
    return {
        "running": running_count,
        "cap": limit,
        "repo": repo,
        "must_launch": launch,
        "reason": must_launch_reason(running_count=running_count, min_running_n=limit),
    }


def format_decision(decision: dict[str, Any]) -> str:
    must = 1 if decision["must_launch"] else 0
    repo = decision.get("repo") or "-"
    return (
        f"CLOUD_RUNNING={decision['running']} cap={decision['cap']} repo={repo}\n"
        f"CLOUD_MUST_LAUNCH={must} reason={decision['reason']}\n"
    )


def cmd_decide_from_list(*, repo: str, min_running_n: int | None) -> int:
    text = sys.stdin.read()
    sys.stdout.write(text)
    if text and not text.endswith("\n"):
        sys.stdout.write("\n")
    rows = parse_list_output(text)
    n = count_running(rows, repo=repo or None)
    decision = decide(running_count=n, min_running_n=min_running_n, repo=repo)
    sys.stdout.write(format_decision(decision))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    dec = sub.add_parser("decide-from-list")
    dec.add_argument("--repo", default="")
    dec.add_argument("--min-running", type=int, default=None)
    args = parser.parse_args(argv)
    if args.cmd == "decide-from-list":
        return cmd_decide_from_list(repo=args.repo, min_running_n=args.min_running)
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except OSError:
            pass
        raise SystemExit(0)
