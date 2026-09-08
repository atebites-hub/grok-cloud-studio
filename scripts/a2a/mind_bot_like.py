#!/usr/bin/env python3
"""Grok-bot-like remaining A2A mechanics for Grok Build minds.

Mailbox harvest writes a disk turn (mind/mail.txt + mind/turn.txt, Bot
wake analog) before the runner. Mind spawn PATH is Extra High
(cloud_launch) plus a2a_send. cloud_launch execs
scripts/launch-cloud-extra-high.sh. Not leftover ACP overlay. Not a Grok Bot
grunt runtime.

Do not vendor Hermes. Do not land harvest envelope helpers. Do not
restack #47 command-center list/follow tools here.

Stdlib only. Local studio only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
from lib import canonical_seat, grow_seats, mind_seats, state_root  # noqa: E402

ROOT = Path(os.environ.get("GCS_ROOT", Path(__file__).resolve().parents[2]))

SPAWN_WRAPPERS: tuple[tuple[str, Path], ...] = (
    ("cloud_launch", Path("scripts") / "launch-cloud-extra-high.sh"),
    ("a2a_send", Path("scripts") / "a2a" / "send.sh"),
)

# Ack is an action (Grokking Simplicity): STATUS ACK must not clobber an
# in-flight Donald TASK in mind/mail.txt. Unique remaining vs CLOSED #81:
# hold file is mind/mail.hold (not the closed PR's inflight filename);
# runners may still write the same-turn wrap. Do not remint that PR's
# sole-writer helper.

_STATUS_ACK_HEAD_RE = re.compile(
    r"^\s*(?:STATUS(?:\s+ACK)?|ACP_PING|ACK)\b",
    re.IGNORECASE,
)
_MAIL_TURNS: set[str] = set()
MAIL_HELD_ERR = "PLUGIN_ERR mail held (STATUS ACK cannot clobber TASK)"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_status_ack(text: str) -> bool:
    """True for keep-alive / protocol ACK lines that must not clobber a TASK.

    Ack is an action: writing STATUS ACK onto mail.txt mutates the in-flight
    grok --prompt-file. A Donald TASK / TASK_ASSIGN is not an ack. wrap_mind_mail
    (A2A_TASK_ID header) is not an ack.
    """
    blob = (text or "").strip()
    if not blob:
        return False
    head = blob.split("\n", 1)[0]
    if _STATUS_ACK_HEAD_RE.match(head):
        return True
    if "STATUS/CONTINUE" in blob.upper():
        return True
    if re.search(r"\bSTATUS ACK\b", blob, re.IGNORECASE):
        return True
    if re.search(r"^ACK seat=", blob, re.MULTILINE):
        return True
    return False


def mail_file(state_dir: Path, seat: str) -> Path:
    return Path(state_dir) / seat / "mind" / "mail.txt"


def mail_hold_file(state_dir: Path, seat: str) -> Path:
    return Path(state_dir) / seat / "mind" / "mail.hold"


def begin_mail_turn(seat: str) -> None:
    _MAIL_TURNS.add(seat)


def end_mail_turn(seat: str) -> None:
    _MAIL_TURNS.discard(seat)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def mail_turn_held(state_dir: Path, seat: str) -> bool:
    """True when this process or another live pid holds mind/mail.txt."""
    if seat in _MAIL_TURNS:
        return True
    path = mail_hold_file(state_dir, seat)
    if not path.is_file():
        return False
    try:
        pid = int(path.read_text(encoding="utf-8").strip().split()[0])
    except (ValueError, OSError, IndexError):
        return True
    if pid == os.getpid():
        return False
    return _pid_alive(pid)


def try_write_mail(state_dir: Path, seat: str, prompt: str) -> bool:
    """Write mind/mail.txt unless a STATUS ACK would clobber an in-flight TASK.

    Same-turn wrap (A2A_TASK_ID / RESULT law around the TASK) is allowed.
    Nested harvest is refused via mail_turn_held. Returns False when the
    write was refused so grok --prompt-file still holds the TASK until
    that runner exits 0.
    """
    mind = Path(state_dir) / seat / "mind"
    mind.mkdir(parents=True, exist_ok=True)
    path = mail_file(state_dir, seat)
    hold = mail_hold_file(state_dir, seat)
    current = ""
    if path.is_file():
        try:
            current = path.read_text(encoding="utf-8")
        except OSError:
            current = ""
    held = hold.is_file() or seat in _MAIL_TURNS
    if (
        held
        and is_status_ack(prompt)
        and current.strip()
        and not is_status_ack(current)
    ):
        return False
    path.write_text(prompt, encoding="utf-8")
    hold.write_text(f"{os.getpid()}\n", encoding="utf-8")
    return True


def clear_mail_hold(state_dir: Path, seat: str) -> None:
    path = mail_hold_file(state_dir, seat)
    try:
        path.unlink()
    except OSError:
        pass


def extract_mail_text(rec: dict[str, Any]) -> str:
    """Inbox record → prompt body. Raw mailbox text. No envelope."""
    parts = rec.get("parts")
    bits: list[str] = []
    if isinstance(parts, list):
        for part in parts:
            if not isinstance(part, dict):
                continue
            if part.get("kind") == "text" or "text" in part:
                text = part.get("text")
                if text is not None:
                    bits.append(str(text))
            elif part.get("kind") == "data" and "data" in part:
                try:
                    bits.append(json.dumps(part["data"], ensure_ascii=False))
                except (TypeError, ValueError):
                    bits.append(str(part["data"]))
    body = "\n".join(bits).strip()
    if body:
        return body
    return json.dumps(rec, ensure_ascii=False)


def prepare_mail_turn(
    state_dir: Path,
    seat: str,
    rec: dict[str, Any],
    *,
    now: str | None = None,
) -> str:
    """Write Bot-like turn files, then return the runner prompt.

    mind/mail.txt is the grok --prompt-file body. mind/turn.txt +
    mind/turn.jsonl match Bot wake artifacts (latest + append log).
    Offset still advances only after the runner exits 0.
    """
    prompt = extract_mail_text(rec)
    mind = Path(state_dir) / seat / "mind"
    mind.mkdir(parents=True, exist_ok=True)
    mail_body = prompt if prompt.endswith("\n") else prompt + "\n"
    if not try_write_mail(state_dir, seat, mail_body):
        return prompt
    ts = now or _now()
    task_id = str(rec.get("taskId") or rec.get("id") or "")
    context_id = str(rec.get("contextId") or "")
    turn_txt = (
        f"ts={ts}\nseat={seat}\ntaskId={task_id}\ncontextId={context_id}\n\n"
        f"{prompt.rstrip()}\n"
    )
    (mind / "turn.txt").write_text(turn_txt, encoding="utf-8")
    artifact = {
        "ts": ts,
        "seat": seat,
        "taskId": task_id,
        "contextId": context_id,
        "text": prompt,
    }
    with (mind / "turn.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(artifact, ensure_ascii=False) + "\n")
    return prompt


def default_tick_seats(root: Path | None = None) -> tuple[str, ...]:
    """Stay-up keep-alives: leftover GROW plus opted-in mind seats.

    Re-read each call. skipSeats never join. Not a 45s assigner.
    """
    return tuple(sorted(grow_seats(root) | mind_seats(root)))


def _write_exec_wrapper(dest: Path, script: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    quoted = shlex.quote(str(script.resolve()))
    dest.write_text(
        "#!/bin/bash\n"
        "# gcs-mind-bot-like-wrapper: exec target script\n"
        "set -euo pipefail\n"
        f"exec {quoted} \"$@\"\n",
        encoding="utf-8",
    )
    dest.chmod(0o755)


def install_mind_spawn_path(
    *,
    root: Path,
    grok_home: Path,
    home: Path | None = None,
) -> list[Path]:
    """Install Extra High spawn + A2A send wrappers onto the mind PATH.

    GROK_HOME/bin and ~/.grok/bin. Cursor CLI inherits PATH from the mind
    loop; do not copy GROK_HOME MCP. Do not wrap watch.
    """
    home_dir = Path(home) if home is not None else Path(
        os.environ.get("HOME") or str(grok_home)
    )
    written: list[Path] = []
    wrap_dirs = (Path(grok_home) / "bin", home_dir / ".grok" / "bin")
    for name, rel in SPAWN_WRAPPERS:
        script = Path(root) / rel
        for wrap_dir in wrap_dirs:
            dest = wrap_dir / name
            _write_exec_wrapper(dest, script)
            written.append(dest)
    return written


def install_spawn_for_seat(seat: str, *, root: Path | None = None) -> int:
    """CLI helper for seat-mind-loop.sh. Never abort the mind loop."""
    repo = Path(root) if root is not None else ROOT
    key = canonical_seat(seat, repo)
    sd = state_root(repo) / key
    grok_home = Path(os.environ.get("GROK_HOME") or str(sd / "grok-home"))
    try:
        written = install_mind_spawn_path(
            root=repo,
            grok_home=grok_home,
            home=Path(os.environ.get("HOME") or str(grok_home)),
        )
    except OSError as exc:
        print(f"MIND_SPAWN_PATH_SKIP seat={key} err={type(exc).__name__}", flush=True)
        return 0
    print(
        f"MIND_SPAWN_PATH_OK seat={key} wrap={grok_home / 'bin'} n={len(written)}",
        flush=True,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Grok-bot-like remaining A2A helpers for Grok Build minds"
    )
    sub = parser.add_subparsers(dest="cmd")
    spawn = sub.add_parser("install-spawn", help="Install cloud_launch + a2a_send PATH wrappers")
    spawn.add_argument("--seat", required=True, help="Director seat id")
    args = parser.parse_args(argv)
    if args.cmd == "install-spawn":
        return install_spawn_for_seat(args.seat)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
