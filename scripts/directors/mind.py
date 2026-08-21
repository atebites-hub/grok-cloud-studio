#!/usr/bin/env python3
"""Grok Build seat mind: mailbox + pin + stay-up.

Python is not the agent. It harvests one inbox line, pins a grok session UUID,
runs one `grok -p` turn, persists json stdout, and stays up. Grok is the agent
for that turn (its own tool loop, `--max-turns 40`).

Do not parse grok stdout for function calls. Do not run a second tool-calling
loop. Do not use grok agent serve or leftover ACP inject on opted-in mind
seats. Pin one UUID in mind/session; first turn `--session-id`, later turns
`--resume` that id. Never remint because harvest was empty.

Stdlib only. Donald/orchestrator (skipSeats) are not mind seats.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_LIB_DIR = Path(__file__).resolve().parents[1] / "a2a"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
from lib import canonical_seat, skip_seats  # noqa: E402

ROOT = Path(os.environ.get("GCS_ROOT", Path(__file__).resolve().parents[2]))
STATE_DIR = Path(os.environ.get("GCS_A2A_STATE", str(ROOT / ".a2a-state")))

_SECRET_ASSIGN_RE = re.compile(
    r"(?i)\b(CURSOR_API_KEY|GCS_WEBHOOK_SECRET|Authorization|Bearer|"
    r"server-key|ACP_SECRET|api[_-]?key)\s*[=:]\s*\S+"
)


@dataclass(frozen=True)
class Plugin:
    """Fallback helper callable plus JSON schema. Not a second agent loop.

    Grok sees tools via builtins, seat GROK_HOME taskboard MCP, and
    `--plugin-dir plugins/studio-mind` when that directory exists. This dict
    stays for `call_plugin` / tests / the plugin-dir MCP server.
    """

    schema: dict[str, Any]
    call: Callable[[dict[str, Any]], str]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact(text: str) -> str:
    """Strip credential assignments from plugin/runner output. Never print secrets."""
    if not text:
        return text
    return _SECRET_ASSIGN_RE.sub(lambda m: f"{m.group(1)}=[redacted]", text)


def mind_dir(seat: str) -> Path:
    d = STATE_DIR / seat / "mind"
    d.mkdir(parents=True, exist_ok=True)
    return d


def grok_home_dir(seat: str) -> Path:
    d = STATE_DIR / seat / "grok-home"
    d.mkdir(parents=True, exist_ok=True)
    return d


def taskboard_db() -> Path:
    raw = os.environ.get("GCS_TASKBOARD_DB") or os.environ.get("TASKBOARD_DB")
    if raw:
        return Path(raw)
    return STATE_DIR / "taskboard" / "taskboard.db"


def _write_pid(seat: str) -> None:
    try:
        (mind_dir(seat) / "pid").write_text(str(os.getpid()) + "\n", encoding="utf-8")
    except OSError:
        pass


def _read_offset(seat: str) -> int:
    path = mind_dir(seat) / "offset"
    if not path.is_file():
        return 0
    try:
        return max(0, int(path.read_text(encoding="utf-8").strip() or "0"))
    except ValueError:
        return 0


def _write_offset(seat: str, offset: int) -> None:
    path = mind_dir(seat) / "offset"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(str(offset) + "\n", encoding="utf-8")
    tmp.replace(path)


def _append_transcript(seat: str, row: dict[str, Any]) -> None:
    path = mind_dir(seat) / "transcript.jsonl"
    rec = dict(row)
    rec.setdefault("ts", _now())
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def session_file(seat: str) -> Path:
    return mind_dir(seat) / "session"


def session_minted_file(seat: str) -> Path:
    return mind_dir(seat) / "session.minted"


def load_or_create_session(seat: str) -> str:
    """UUID once. Never rewrite because a later harvest was empty."""
    path = session_file(seat)
    if path.is_file():
        raw = path.read_text(encoding="utf-8").strip()
        if raw:
            return raw
    sid = str(uuid.uuid4())
    tmp = path.with_suffix(".tmp")
    tmp.write_text(sid + "\n", encoding="utf-8")
    tmp.replace(path)
    return sid


def session_is_minted(seat: str) -> bool:
    return session_minted_file(seat).is_file()


def mark_session_minted(seat: str) -> None:
    session_minted_file(seat).write_text("1\n", encoding="utf-8")


def soul_profile(seat: str) -> str | None:
    """`--agent-profile` value: seat SOUL.md, else docs souls, else omit."""
    local = STATE_DIR / seat / "SOUL.md"
    if local.is_file():
        return str(local)
    src = ROOT / "docs" / "studio" / "directors" / "souls" / seat / "SOUL.md"
    if src.is_file():
        return str(src)
    return None


def studio_mind_plugin_dir() -> Path | None:
    """Grok Agent SDK inject dir. Omit `--plugin-dir` when it is missing."""
    path = ROOT / "plugins" / "studio-mind"
    if path.is_dir():
        return path
    return None


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


def _read_new_records(seat: str) -> list[tuple[int, dict[str, Any]]]:
    path = STATE_DIR / seat / "inbox.jsonl"
    if not path.is_file():
        return []
    size = path.stat().st_size
    offset = _read_offset(seat)
    if offset > size:
        offset = size
    records: list[tuple[int, dict[str, Any]]] = []
    with path.open("rb") as fh:
        fh.seek(offset)
        while True:
            line_start = fh.tell()
            raw = fh.readline()
            if not raw:
                break
            if not raw.endswith(b"\n"):
                break
            end = fh.tell()
            try:
                rec = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                print(
                    f"MIND_WARN seat={seat} bad_json offset={line_start}: {e}",
                    file=sys.stderr,
                )
                records.append((end, {"__corrupt__": True}))
                continue
            if not isinstance(rec, dict):
                records.append((end, {"__corrupt__": True}))
                continue
            records.append((end, rec))
    return records


def _argv_list(arguments: dict[str, Any]) -> list[str]:
    raw = arguments.get("argv")
    if raw is None:
        raw = arguments.get("args")
    if raw is None:
        raw = arguments.get("command")
    if isinstance(raw, str):
        return raw.split()
    if isinstance(raw, list):
        return [str(x) for x in raw]
    return []


def _run_cmd(cmd: list[str], *, timeout: int = 60) -> str:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env={**os.environ, "GCS_ROOT": str(ROOT), "GCS_A2A_STATE": str(STATE_DIR)},
        )
    except FileNotFoundError:
        return f"PLUGIN_ERR missing binary: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return f"PLUGIN_ERR timeout after {timeout}s: {cmd[0]}"
    except OSError as e:
        return f"PLUGIN_ERR {e}"
    out = (proc.stdout or "") + (proc.stderr or "")
    blob = redact(out.strip() or f"rc={proc.returncode}")
    if proc.returncode != 0 and "PLUGIN_ERR" not in blob:
        return f"PLUGIN_ERR rc={proc.returncode} {blob}"
    return blob


def plugin_ticket(arguments: dict[str, Any]) -> str:
    """Exec TASKBOARD_BIN --db GCS_TASKBOARD_DB ticket <argv>."""
    candidates: list[Path] = []
    env_bin = (os.environ.get("TASKBOARD_BIN") or "").strip()
    if env_bin:
        candidates.append(Path(env_bin))
    candidates.append(ROOT / "bin" / "taskboard")
    binary: Path | None = None
    for cand in candidates:
        try:
            if cand.is_file() and os.access(cand, os.X_OK):
                binary = cand
                break
        except OSError:
            continue
    if binary is None:
        return "PLUGIN_ERR ticket: missing TASKBOARD_BIN (set TASKBOARD_BIN)"
    argv = _argv_list(arguments)
    db = str(taskboard_db())
    cmd = [str(binary), "--db", db, "ticket", *argv]
    return _run_cmd(cmd, timeout=60)


def plugin_a2a_send(arguments: dict[str, Any]) -> str:
    """scripts/a2a/send.sh [--from SEAT] <seat> <text>."""
    script = ROOT / "scripts" / "a2a" / "send.sh"
    if not script.is_file():
        return "PLUGIN_ERR a2a_send: missing scripts/a2a/send.sh"
    seat = str(arguments.get("seat") or "").strip()
    text = str(arguments.get("text") or "")
    if not seat or not text:
        return "PLUGIN_ERR a2a_send: seat and text are required"
    cmd = ["bash", str(script)]
    from_seat = str(arguments.get("from") or arguments.get("from_seat") or "").strip()
    if from_seat:
        cmd.extend(["--from", from_seat])
    cmd.extend([seat, text])
    return _run_cmd(cmd, timeout=60)


def plugin_cloud_launch(arguments: dict[str, Any]) -> str:
    """scripts/launch-cloud-extra-high.sh [--name NAME] PROMPT."""
    script = ROOT / "scripts" / "launch-cloud-extra-high.sh"
    if not script.is_file():
        return "PLUGIN_ERR cloud_launch: missing scripts/launch-cloud-extra-high.sh"
    prompt = str(arguments.get("prompt") or "").strip()
    if not prompt:
        return "PLUGIN_ERR cloud_launch: prompt is required"
    cmd = ["bash", str(script)]
    name = str(arguments.get("name") or "").strip()
    if name:
        cmd.extend(["--name", name])
    cmd.append(prompt)
    return _run_cmd(cmd, timeout=180)


TICKET_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "argv": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Arguments after `ticket`, e.g. [\"list\"] or "
                "[\"move\", \"T-1\", \"--status\", \"done\"]."
            ),
        }
    },
    "required": ["argv"],
    "additionalProperties": False,
}

A2A_SEND_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "seat": {"type": "string", "description": "Destination seat id"},
        "text": {"type": "string", "description": "Message body"},
        "from": {"type": "string", "description": "Optional caller seat for --from"},
    },
    "required": ["seat", "text"],
    "additionalProperties": False,
}

CLOUD_LAUNCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "prompt": {"type": "string"},
        "name": {"type": "string", "description": "Short Extra High agent name"},
    },
    "required": ["prompt"],
    "additionalProperties": False,
}

PLUGINS: dict[str, Plugin] = {
    "ticket": Plugin(schema=TICKET_SCHEMA, call=plugin_ticket),
    "a2a_send": Plugin(schema=A2A_SEND_SCHEMA, call=plugin_a2a_send),
    "cloud_launch": Plugin(schema=CLOUD_LAUNCH_SCHEMA, call=plugin_cloud_launch),
}


def call_plugin(name: str, arguments: dict[str, Any] | None = None) -> str:
    plugin = PLUGINS.get(name)
    if plugin is None:
        return f"PLUGIN_ERR unknown plugin: {name}"
    try:
        return redact(plugin.call(arguments or {}))
    except Exception as e:
        return f"PLUGIN_ERR {name}: {e}"


def grok_cli_argv(
    *,
    session_id: str,
    minted: bool,
    mail_path: Path,
    soul: str | None = None,
    plugin_dir: Path | None = None,
    grok: str | None = None,
) -> list[str]:
    """Pinned-session grok CLI. First turn mints; later turns resume that UUID."""
    binary = grok or os.environ.get("GROK_BIN") or "grok"
    argv: list[str] = [binary, "-p"]
    if minted:
        argv.extend(["--resume", session_id])
    else:
        argv.extend(["--session-id", session_id])
    argv.extend(
        [
            "--prompt-file",
            str(mail_path),
            "--verbatim",
            "--output-format",
            "json",
            "--always-approve",
            "--permission-mode",
            "bypassPermissions",
            "--trust",
        ]
    )
    if soul:
        argv.extend(["--agent-profile", soul])
    if plugin_dir is not None:
        argv.extend(["--plugin-dir", str(plugin_dir)])
    argv.extend(["--max-turns", "40"])
    return argv


def grok_cli_runner(prompt: str, *, seat: str = "", **_kwargs: Any) -> dict[str, Any]:
    grok_home = grok_home_dir(seat)
    session_id = load_or_create_session(seat)
    minted = session_is_minted(seat)
    mail_path = mind_dir(seat) / "mail.txt"
    mail_path.write_text(prompt, encoding="utf-8")
    argv = grok_cli_argv(
        session_id=session_id,
        minted=minted,
        mail_path=mail_path,
        soul=soul_profile(seat),
        plugin_dir=studio_mind_plugin_dir(),
    )
    env = os.environ.copy()
    env["GCS_ROOT"] = str(ROOT)
    env["GCS_A2A_STATE"] = str(STATE_DIR)
    env["GROK_HOME"] = str(grok_home)
    env["GROK_MEMORY"] = "1"
    timeout_raw = os.environ.get("GCS_MIND_TURN_TIMEOUT", "").strip()
    timeout: float | None = float(timeout_raw) if timeout_raw else None
    try:
        proc = subprocess.run(
            argv,
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return {"text": "PLUGIN_ERR grok CLI missing on PATH", "returncode": 127}
    except subprocess.TimeoutExpired:
        return {"text": "PLUGIN_ERR grok CLI timeout", "returncode": 124}
    except OSError as e:
        return {"text": f"PLUGIN_ERR grok CLI: {e}", "returncode": 1}
    text = redact((proc.stdout or "").strip())
    stderr = redact((proc.stderr or "").strip())
    return {"text": text, "returncode": int(proc.returncode), "stderr": stderr}


DEFAULT_RUNNER: Callable[..., Any] = grok_cli_runner


def _runner_payload(raw: Any) -> tuple[str, int]:
    if raw is None:
        return "", 0
    if isinstance(raw, dict):
        text = str(raw.get("text") or "")
        rc = raw.get("returncode")
        if rc is None:
            rc = 0
        try:
            code = int(rc)
        except (TypeError, ValueError):
            code = 1
        return text, code
    return str(raw), 0


def _is_skip_seat(seat: str) -> bool:
    skipped = skip_seats(ROOT)
    key = canonical_seat(seat, ROOT)
    return key in skipped or seat.strip().lower() in skipped


def process_once(seat: str, *, runner: Callable[..., Any] | None = None) -> dict[str, Any]:
    """One inbox line → one grok turn. Offset advances only on grok exit 0."""
    seat = canonical_seat(seat, ROOT)
    if _is_skip_seat(seat):
        print(f"MIND_SKIP seat={seat} reason=skipSeats", flush=True)
        return {"consumed": 0, "reason": "skipSeats"}

    mind_dir(seat)
    grok_home_dir(seat)
    records = _read_new_records(seat)
    if not records:
        return {"consumed": 0, "reason": "empty", "offset": _read_offset(seat)}

    run = runner if runner is not None else DEFAULT_RUNNER
    for end_offset, rec in records:
        if rec.get("__corrupt__"):
            _write_offset(seat, end_offset)
            continue
        task_id = str(rec.get("taskId") or "")
        context_id = str(rec.get("contextId") or "")
        text = _extract_text(rec.get("parts"))
        prompt = text or json.dumps(rec, ensure_ascii=False)
        try:
            raw = run(prompt, seat=seat)
        except Exception as e:
            print(
                f"MIND_FAIL seat={seat} task={task_id} reason=runner-fail err={e}",
                file=sys.stderr,
            )
            return {"consumed": 0, "reason": "runner-fail", "task_id": task_id}

        assistant_text, returncode = _runner_payload(raw)
        if returncode != 0:
            print(
                f"MIND_FAIL seat={seat} task={task_id} reason=runner-fail rc={returncode}",
                file=sys.stderr,
            )
            return {
                "consumed": 0,
                "reason": "runner-fail",
                "task_id": task_id,
                "returncode": returncode,
            }

        mark_session_minted(seat)
        _append_transcript(
            seat,
            {
                "role": "user",
                "content": prompt,
                "taskId": task_id,
                "contextId": context_id,
            },
        )
        _append_transcript(
            seat,
            {
                "role": "assistant",
                "content": assistant_text,
                "format": "json",
            },
        )
        _write_offset(seat, end_offset)
        print(
            f"MIND_TURN seat={seat} task={task_id} offset={end_offset}",
            flush=True,
        )
        return {
            "consumed": 1,
            "reason": "ok",
            "task_id": task_id,
            "offset": end_offset,
        }

    return {"consumed": 0, "reason": "no-actionable", "offset": _read_offset(seat)}


def wait_for_inbox(seat: str, timeout: float = 30.0) -> None:
    inbox = STATE_DIR / seat / "inbox.jsonl"
    offset = _read_offset(seat)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if inbox.is_file() and inbox.stat().st_size > offset:
                return
        except OSError:
            pass
        time.sleep(0.25)


def run_forever(seat: str) -> int:
    seat = canonical_seat(seat, ROOT)
    if _is_skip_seat(seat):
        print(f"MIND_SKIP seat={seat} reason=skipSeats", file=sys.stderr)
        return 2
    _write_pid(seat)
    print(f"MIND_READY seat={seat} state={STATE_DIR} mode=grok-build-mind", flush=True)
    stopping = False

    def _handle(signum: int, _frame: Any) -> None:
        nonlocal stopping
        stopping = True
        print(f"MIND_STOP seat={seat} signal={signum}", flush=True)

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)
    while not stopping:
        result = process_once(seat)
        if result.get("consumed"):
            continue
        if result.get("reason") == "runner-fail":
            end = time.time() + 2.0
            while not stopping and time.time() < end:
                time.sleep(0.25)
            continue
        wait_for_inbox(seat, timeout=30.0)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Grok Build seat mind (mailbox + pin + stay-up; grok is the agent)"
    )
    parser.add_argument("--seat", required=True, help="Director seat (floor, ops, …)")
    parser.add_argument("--once", action="store_true", help="Process one pending line then exit")
    args = parser.parse_args(argv)
    seat = canonical_seat(args.seat, ROOT)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if args.once:
        process_once(seat)
        return 0
    return run_forever(seat)


if __name__ == "__main__":
    sys.exit(main())
