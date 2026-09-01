#!/usr/bin/env python3
"""Wake Grok Bot seats from A2A inbox lines (not ACP inject / grok -p).

Polls bot seat inboxes listed in docs/a2a/bot-agents.json (or
GCS_BOT_AGENTS_JSON). For each new inbox line past bot-bridge.offset,
appends a wake artifact and optionally runs BOT_BRIDGE_HOOK.

Bot agents (e.g. Donald) are not `grok agent serve` daemons — dispatch.py
keeps them in SKIP_SEATS. This bridge is the attach path: standing Bot
routines poll bot-wake / inbox on the shared box and act.

Do not stamp Linear. Hive already comments Living Sky issues after each
mind turn and A2A-pings Donald. LINEAR_STAMP receipts are not a Linear write.

Never prints secrets. Local studio only. Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("GCS_ROOT", Path(__file__).resolve().parents[2]))
STATE_DIR = Path(os.environ.get("GCS_A2A_STATE", str(ROOT / ".a2a-state")))
DEFAULT_CONFIG = ROOT / "docs" / "a2a" / "bot-agents.json"
CONFIG_PATH = Path(os.environ.get("GCS_BOT_AGENTS_JSON", str(DEFAULT_CONFIG)))
POLL_SEC = float(os.environ.get("GCS_BOT_BRIDGE_POLL_SEC", os.environ.get("GCS_A2A_POLL_SEC", "2")))
HOOK = (os.environ.get("BOT_BRIDGE_HOOK") or "").strip()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_bot_seats(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        print(f"BOT_BRIDGE_WARN missing config={path}", file=sys.stderr)
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"BOT_BRIDGE_FAIL config_parse err={e}", file=sys.stderr)
        return {}
    seats = data.get("seats") if isinstance(data, dict) else None
    if not isinstance(seats, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for name, meta in seats.items():
        if not isinstance(meta, dict):
            continue
        kind = str(meta.get("kind") or "")
        if kind and kind != "grok-bot":
            continue
        out[str(name)] = meta
    return out


def _seat_dir(seat: str, meta: dict[str, Any]) -> Path:
    inbox_rel = str(meta.get("inbox") or f".a2a-state/{seat}").strip()
    p = Path(inbox_rel)
    if not p.is_absolute():
        # inbox path in config points at seat dir (…/.a2a-state/<seat>)
        if inbox_rel.startswith(".a2a-state/"):
            p = ROOT / inbox_rel
        else:
            p = STATE_DIR / seat
    return p


def _inbox_path(seat_dir: Path) -> Path:
    return seat_dir / "inbox.jsonl"


def _offset_path(seat_dir: Path) -> Path:
    return seat_dir / "bot-bridge.offset"


def _read_offset(seat_dir: Path) -> int:
    p = _offset_path(seat_dir)
    if not p.is_file():
        return 0
    try:
        return max(0, int(p.read_text(encoding="utf-8").strip() or "0"))
    except ValueError:
        return 0


def _write_offset(seat_dir: Path, offset: int) -> None:
    p = _offset_path(seat_dir)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(str(offset) + "\n", encoding="utf-8")
    tmp.replace(p)


def _extract_text(parts: Any) -> str:
    bits: list[str] = []
    if not isinstance(parts, list):
        return ""
    for p in parts:
        if not isinstance(p, dict):
            continue
        if p.get("kind") == "text" or "text" in p:
            t = p.get("text")
            if t is not None:
                bits.append(str(t))
        elif p.get("kind") == "data" and "data" in p:
            try:
                bits.append(json.dumps(p["data"], ensure_ascii=False))
            except (TypeError, ValueError):
                bits.append(str(p["data"]))
    return "\n".join(bits).strip()


def _safe_task_id(rec: dict[str, Any]) -> str:
    return str(rec.get("taskId") or rec.get("id") or "")[:128]


def _write_wake(seat: str, seat_dir: Path, rec: dict[str, Any], text: str) -> Path:
    seat_dir.mkdir(parents=True, exist_ok=True)
    wake_jsonl = seat_dir / "bot-wake.jsonl"
    wake_txt = seat_dir / "bot-wake.txt"
    task_id = _safe_task_id(rec)
    context_id = str(rec.get("contextId") or "")[:128]
    artifact = {
        "ts": _now(),
        "seat": seat,
        "taskId": task_id,
        "contextId": context_id,
        "text": text,
    }
    # Strip accidental secret-looking keys from nested record copies — we only
    # persist the sanitized artifact above, never the raw env or tokens.
    line = json.dumps(artifact, ensure_ascii=False)
    with wake_jsonl.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    wake_txt.write_text(
        f"ts={artifact['ts']}\nseat={seat}\ntaskId={task_id}\ncontextId={context_id}\n\n{text.rstrip()}\n",
        encoding="utf-8",
    )
    return wake_txt


def _run_hook(seat: str, task_id: str, wake_txt: Path) -> None:
    if not HOOK:
        return
    env = os.environ.copy()
    env["GCS_ROOT"] = str(ROOT)
    env["GCS_A2A_STATE"] = str(STATE_DIR)
    env["BOT_BRIDGE_SEAT"] = seat
    env["BOT_BRIDGE_TASK"] = task_id
    env["BOT_BRIDGE_WAKE_TXT"] = str(wake_txt)
    # Do not forward obvious secret env names into logs; hook inherits env as-is
    # but we never print env values.
    try:
        proc = subprocess.run(
            HOOK,
            shell=True,
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"BOT_BRIDGE_HOOK_FAIL seat={seat} task={task_id} err={type(e).__name__}", file=sys.stderr)
        return
    if proc.returncode != 0:
        print(
            f"BOT_BRIDGE_HOOK_FAIL seat={seat} task={task_id} rc={proc.returncode}",
            file=sys.stderr,
        )


def _process_seat(seat: str, meta: dict[str, Any]) -> int:
    seat_dir = _seat_dir(seat, meta)
    inbox = _inbox_path(seat_dir)
    if not inbox.is_file():
        return 0
    try:
        size = inbox.stat().st_size
    except OSError:
        return 0
    offset = _read_offset(seat_dir)
    if offset > size:
        offset = 0
    woke = 0
    with inbox.open("rb") as f:
        f.seek(offset)
        while True:
            raw = f.readline()
            if not raw:
                break
            if not raw.endswith(b"\n"):
                break
            end = f.tell()
            try:
                rec = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                _write_offset(seat_dir, end)
                continue
            if not isinstance(rec, dict):
                _write_offset(seat_dir, end)
                continue
            text = _extract_text(rec.get("parts"))
            task_id = _safe_task_id(rec)
            wake_txt = _write_wake(seat, seat_dir, rec, text)
            print(f"BOT_BRIDGE_WAKE seat={seat} task={task_id}", flush=True)
            _run_hook(seat, task_id, wake_txt)
            _write_offset(seat_dir, end)
            woke += 1
    return woke


def run_cycle(seats: dict[str, dict[str, Any]]) -> int:
    total = 0
    for seat, meta in sorted(seats.items()):
        total += _process_seat(seat, meta)
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description="Grok Cloud Studio A2A → Grok Bot wake bridge")
    parser.add_argument("--once", action="store_true", help="One poll cycle then exit")
    parser.add_argument(
        "--config",
        default=str(CONFIG_PATH),
        help="Path to bot-agents.json",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    seats = _load_bot_seats(config_path)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    print(
        f"BOT_BRIDGE_READY state={STATE_DIR} config={config_path} "
        f"seats={','.join(sorted(seats)) or '(none)'} poll={POLL_SEC}s "
        f"hook={1 if HOOK else 0} once={int(args.once)}",
        flush=True,
    )
    if not seats:
        print("BOT_BRIDGE_WARN no bot seats configured", file=sys.stderr)

    stopping = False

    def _handle(signum: int, _frame: Any) -> None:
        nonlocal stopping
        stopping = True
        print(f"BOT_BRIDGE_STOP signal={signum}", flush=True)

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)

    if args.once:
        run_cycle(seats)
        return 0

    while not stopping:
        seats = _load_bot_seats(config_path)
        run_cycle(seats)
        end = time.time() + POLL_SEC
        while not stopping and time.time() < end:
            time.sleep(min(0.25, max(0.0, end - time.time())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
