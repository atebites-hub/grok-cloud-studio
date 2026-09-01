#!/usr/bin/env python3
"""Host process ticker: enqueue ACP_PING STATUS/CONTINUE onto seat inboxes.

The clock is this host process, not `/loop` inside an idle grok agent serve
session and not watchdog ACP-injecting keep-alives. Each tick grows
inbox.jsonl. The seat wake loop then ACP session/prompts the live serve.
The ping is a work turn (not RESULT-only hang-up). Not a central LAUNCH
assigner and not a LAUNCH kind. Tools are allowed. Default interval is
GCS_TICKER_SEC (600). Local studio only. Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(os.environ.get("GCS_ROOT", Path(__file__).resolve().parents[2]))
STATE_DIR = Path(os.environ.get("GCS_A2A_STATE", str(ROOT / ".a2a-state")))
CLOCK_SH = ROOT / "scripts" / "directors" / "host-clock-ticker.sh"
INTERVAL_SEC = float(os.environ.get("GCS_TICKER_SEC", "600"))

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
from lib import canonical_seat, grow_seats  # noqa: E402

GROW_SEATS = tuple(sorted(grow_seats(ROOT)))


def _now_ts() -> float:
    return time.time()


def _tick_text(seat: str, token: str) -> str:
    return (
        f"ACP_PING STATUS/CONTINUE seat={seat} token={token}. "
        "Keep-alive turn: do work, do not idle. Quote token in STATUS. "
        "Tools are allowed (taskboard ticket move, send.sh, "
        "scripts/cloud/capacity-count.sh, scripts/launch-cloud-extra-high.sh). "
        "Count runStatus=RUNNING, not leftover ACTIVE+FINISHED. "
        "RESULT-only is a bug."
    )


def tick_once(seats: Iterable[str] | None = None, now: float | None = None) -> int:
    """Append one ACP_PING STATUS/CONTINUE inbox line per seat. Returns lines written."""
    chosen = tuple(seats) if seats is not None else GROW_SEATS
    env = os.environ.copy()
    env["GCS_ROOT"] = str(ROOT)
    env["GCS_A2A_STATE"] = str(STATE_DIR)
    written = 0
    seen: set[str] = set()
    for seat in chosen:
        seat = canonical_seat(str(seat).strip(), ROOT)
        if not seat or seat in seen:
            continue
        seen.add(seat)
        if CLOCK_SH.is_file():
            proc = subprocess.run(
                ["bash", str(CLOCK_SH), "enqueue_continue", seat],
                cwd=str(ROOT),
                env=env,
                capture_output=True,
                text=True,
                timeout=15,
            )
            if proc.returncode == 0:
                written += 1
                print(f"TICKER_ENQUEUE seat={seat}", flush=True)
                continue
        ts = int(now if now is not None else _now_ts())
        token = f"tick-{seat}-{ts}"
        inbox = STATE_DIR / seat / "inbox.jsonl"
        inbox.parent.mkdir(parents=True, exist_ok=True)
        rec = {
            "kind": "message",
            "role": "user",
            "taskId": token,
            "contextId": "host-clock",
            "parts": [{"kind": "text", "text": _tick_text(seat, token)}],
        }
        with inbox.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        written += 1
        print(f"TICKER_ENQUEUE seat={seat} task={token}", flush=True)
    return written


def _write_pid() -> None:
    path = STATE_DIR / "host-ticker.pid"
    try:
        path.write_text(str(os.getpid()) + "\n", encoding="utf-8")
    except OSError:
        pass


def run_forever() -> int:
    global GROW_SEATS
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    _write_pid()
    print(
        f"TICKER_READY state={STATE_DIR} interval={INTERVAL_SEC}s seats={','.join(GROW_SEATS)}",
        flush=True,
    )
    stopping = False

    def _handle(signum: int, _frame: Any) -> None:
        nonlocal stopping
        stopping = True
        print(f"TICKER_STOP signal={signum}", flush=True)

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)
    while not stopping:
        tick_once()
        end = time.time() + INTERVAL_SEC
        while not stopping and time.time() < end:
            time.sleep(min(0.5, max(0.0, end - time.time())))
    return 0


def main() -> int:
    global GROW_SEATS
    parser = argparse.ArgumentParser(description="GROW host ticker (inbox keep-alives)")
    parser.add_argument("--once", action="store_true", help="Enqueue one tick then exit")
    parser.add_argument(
        "--seats",
        default="",
        help="Comma-separated seat filter (default: GROW design seats)",
    )
    args = parser.parse_args()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    seats: tuple[str, ...] | None = None
    if args.seats.strip():
        seats = tuple(s.strip() for s in args.seats.split(",") if s.strip())
    if args.once:
        tick_once(seats=seats)
        return 0
    if seats is not None:
        GROW_SEATS = seats
    return run_forever()


if __name__ == "__main__":
    sys.exit(main())
