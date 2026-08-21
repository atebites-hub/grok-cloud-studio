#!/usr/bin/env python3
"""Inbox wake: inbox.jsonl → ACP session/prompt into live grok agent serve.

One `grok agent serve` per seat that stays up, plus a local client that turns
inbox growth into ACP `session/prompt` inside that same serve process.

Success is mail delivered (session/prompt accepted). Inject disconnects
without session/cancel so serve keeps the turn. Advance wake.offset on
ACP_INJECT_OK / HANDOFF even if the model is still running.

NOT grok --resume (no forked grok child per ping).
NOT Agent Kanban workers.

If serve dies: restart serve (`ensure_seat_serve` / start-seat-daemon.sh).
Never fall back to grok --resume.

Pin ACP session id in `.a2a-state/<seat>/acp.session` (create once via
session/new; later session/load). Hub TASK_STATE_COMPLETED is a receipt,
not proof the Director acted. Local studio only. Stdlib only.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
from lib import normalize_seat as _normalize_seat  # noqa: E402
from lib import skip_seats as _skip_seats_fn  # noqa: E402

ROOT = Path(os.environ.get("GCS_ROOT", Path(__file__).resolve().parents[2]))
STATE_DIR = Path(os.environ.get("GCS_A2A_STATE", str(ROOT / ".a2a-state")))
START_DAEMON = ROOT / "scripts" / "directors" / "start-seat-daemon.sh"
SEAT_PROMPT_ACP = ROOT / "scripts" / "a2a" / "seat-prompt-acp.sh"
PROMPT_TIMEOUT_SEC = float(os.environ.get("GCS_WAKE_ACP_TIMEOUT", "180"))
PROMPT_FAIL_BACKOFF_SEC = float(os.environ.get("GCS_WAKE_PROMPT_FAIL_BACKOFF", "15"))

_DISPATCH: Any = None
_DUPLEX: Any = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_py(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _dispatch() -> Any:
    global _DISPATCH
    if _DISPATCH is None:
        _DISPATCH = _load_py(ROOT / "scripts" / "a2a" / "dispatch.py", "gcs_dispatch_for_wake")
    return _DISPATCH


def _duplex() -> Any:
    global _DUPLEX
    if _DUPLEX is None:
        _DUPLEX = _load_py(ROOT / "scripts" / "a2a" / "duplex.py", "gcs_duplex_for_wake")
    return _DUPLEX


def canonical_seat(seat: str) -> str:
    """Normalize seat names. studio-ops is the product alias for registry ops."""
    key = _normalize_seat(seat)
    if key == "studio-ops":
        return "ops"
    return key


def _skip_seats() -> frozenset[str]:
    return _skip_seats_fn(ROOT)


def _seat_dir(seat: str) -> Path:
    d = STATE_DIR / seat
    d.mkdir(parents=True, exist_ok=True)
    return d


def _wake_offset_path(seat: str) -> Path:
    return _seat_dir(seat) / "wake.offset"


def _read_offset(seat: str) -> int:
    p = _wake_offset_path(seat)
    if not p.is_file():
        return 0
    try:
        return max(0, int(p.read_text(encoding="utf-8").strip() or "0"))
    except ValueError:
        return 0


def _write_offset(seat: str, offset: int) -> None:
    p = _wake_offset_path(seat)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(str(offset) + "\n", encoding="utf-8")
    tmp.replace(p)


def _write_pid(seat: str) -> None:
    try:
        (_seat_dir(seat) / "wake.pid").write_text(str(os.getpid()) + "\n", encoding="utf-8")
    except OSError:
        pass


def _append_log(seat: str, line: str) -> None:
    path = _seat_dir(seat) / "wake.log"
    try:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line.rstrip() + "\n")
    except OSError:
        pass


def _write_wake_mode(seat: str) -> None:
    path = _seat_dir(seat) / "wake.mode"
    path.write_text(
        "kind=grok-build-serve\nawake=inbox-acp-prompt\nmode=acp-serve\n",
        encoding="utf-8",
    )


def pin_acp_session(seat_dir: Path) -> str:
    """Return the pinned ACP session id if present. Never remint here.

    session/new (first boot) is owned by acp_inject.py --pin-session writing
    acp.session. This helper refuses to invent a new id when the file is
    missing or corrupt — the serve client creates it once.
    """
    path = seat_dir / "acp.session"
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def install_grok_home_auth(grok_home: Path) -> None:
    """Copy host ~/.grok/auth.json into GROK_HOME for cached_token. Never print it."""
    grok_home.mkdir(parents=True, exist_ok=True)
    dest = grok_home / "auth.json"
    candidates: list[Path] = []
    override = os.environ.get("GROK_AUTH_JSON", "").strip()
    if override:
        candidates.append(Path(override))
    home = Path(os.environ.get("HOME") or str(Path.home()))
    candidates.append(home / ".grok" / "auth.json")
    for src in candidates:
        try:
            if not src.is_file():
                continue
        except OSError:
            continue
        dest.write_bytes(src.read_bytes())
        try:
            dest.chmod(0o600)
        except OSError:
            pass
        print("SEAT_GROK_AUTH_OK dest=GROK_HOME/auth.json method=cached_token", flush=True)
        return
    print("SEAT_GROK_AUTH_SKIP missing host auth.json", file=sys.stderr)


def prepare_seat_home(seat: str, seat_dir: Path) -> Path:
    """Ensure per-seat GROK_HOME (auth copy only). Named identity lives on serve."""
    del seat  # seat is the directory name; auth is host-global
    seat_dir.mkdir(parents=True, exist_ok=True)
    grok_home = seat_dir / "grok-home"
    grok_home.mkdir(parents=True, exist_ok=True)
    install_grok_home_auth(grok_home)
    return grok_home


def prompt_fail_backoff_sec(streak: int) -> float:
    """Exponential backoff after ACP prompt-fail. Cap 120s."""
    if streak <= 0:
        return 0.0
    delay = PROMPT_FAIL_BACKOFF_SEC * (2 ** (min(streak, 8) - 1))
    return float(min(delay, 120.0))


def prompt_output_accepted(returncode: int, stdout: str) -> bool:
    """True when inject handed the turn to serve, even if the wrapper rc is noisy.

    ACP_INJECT_OK / ACP_INJECT_HANDOFF means session/prompt was accepted.
    TIMEOUT / FAIL must not consume the inbox tick.
    """
    if returncode == 0:
        return True
    blob = stdout or ""
    return "ACP_INJECT_OK" in blob or "ACP_INJECT_HANDOFF" in blob


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    if not Path("/proc").is_dir():
        return True
    try:
        with open(f"/proc/{pid}/status", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("State:"):
                    return not line.split(":", 1)[1].strip().startswith("Z")
    except OSError:
        return False
    return True


def _read_serve_pid(seat: str) -> int:
    path = _seat_dir(seat) / "daemon.pid"
    if not path.is_file():
        return 0
    try:
        return int(path.read_text(encoding="utf-8").strip().split()[0])
    except (ValueError, IndexError, OSError):
        return 0


def serve_healthy(seat: str) -> bool:
    sd = _seat_dir(seat)
    pid = _read_serve_pid(seat)
    if pid <= 0 or not _pid_alive(pid):
        return False
    return (sd / "acp.url").is_file() and (sd / "acp.secret").is_file()


def ensure_seat_serve(seat: str) -> int:
    """Keep grok agent serve up. Never fall back to grok --resume."""
    if serve_healthy(seat):
        _write_wake_mode(seat)
        return _read_serve_pid(seat)
    if not START_DAEMON.is_file():
        print(f"WAKE_SERVE_FAIL seat={seat} missing {START_DAEMON}", file=sys.stderr)
        return 0
    try:
        proc = subprocess.run(
            ["bash", str(START_DAEMON), seat],
            cwd=str(ROOT),
            env={
                **os.environ,
                "GCS_ROOT": str(ROOT),
                "GCS_A2A_STATE": str(STATE_DIR),
                "GCS_DIRECTOR_SEAT": seat,
            },
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"WAKE_SERVE_FAIL seat={seat} err={e}", file=sys.stderr)
        return 0
    if proc.stdout:
        print(proc.stdout.rstrip(), flush=True)
    if proc.returncode != 0:
        err = (proc.stderr or "").rstrip()
        if "server-key=" in err:
            err = "[redacted]"
        if err:
            print(err, file=sys.stderr)
        print(f"WAKE_SERVE_FAIL seat={seat} rc={proc.returncode}", file=sys.stderr)
        return 0
    _write_wake_mode(seat)
    return _read_serve_pid(seat)


def prompt_acp(seat: str, prompt: str, env: dict[str, str]) -> int:
    """Local ACP session/prompt into the live serve. Never grok --resume."""
    if not SEAT_PROMPT_ACP.is_file():
        print(f"WAKE_PROMPT_FAIL seat={seat} missing {SEAT_PROMPT_ACP}", file=sys.stderr)
        return 2
    try:
        proc = subprocess.run(
            ["bash", str(SEAT_PROMPT_ACP), seat, "--stdin"],
            cwd=str(ROOT),
            env=env,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=PROMPT_TIMEOUT_SEC + 30,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        out = e.stdout or ""
        if isinstance(out, bytes):
            out = out.decode("utf-8", errors="replace")
        if out:
            print(out.rstrip(), flush=True)
        if prompt_output_accepted(1, out):
            return 0
        print(f"WAKE_PROMPT_FAIL seat={seat} err={e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"WAKE_PROMPT_FAIL seat={seat} err={e}", file=sys.stderr)
        return 1
    if proc.stdout:
        print(proc.stdout.rstrip(), flush=True)
    if prompt_output_accepted(proc.returncode, proc.stdout or ""):
        return 0
    if proc.returncode != 0 and proc.stderr:
        print(proc.stderr.rstrip(), file=sys.stderr)
    return proc.returncode


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
    path = _seat_dir(seat) / "inbox.jsonl"
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
                    f"WAKE_WARN seat={seat} bad_json offset={line_start}: {e}",
                    file=sys.stderr,
                )
                records.append((end, {"__corrupt__": True, "taskId": f"corrupt-{end}"}))
                continue
            if not isinstance(rec, dict):
                records.append((end, {"__corrupt__": True, "taskId": f"corrupt-{end}"}))
                continue
            records.append((end, rec))
    return records


def _compose_prompt(seat: str, rec: dict[str, Any], text: str) -> str:
    del seat
    disp = _dispatch()
    task_id = str(rec.get("taskId") or "")
    context_id = str(rec.get("contextId") or "")
    if disp is None:
        return f"A2A_TASK_ID={task_id}\nA2A_CONTEXT={context_id}\nMESSAGE:\n{text}\n"
    return disp._compose_extra(task_id, context_id, text)


def process_once(seat: str, *, dry_run: bool = False) -> dict[str, Any]:
    """Consume at most one inbox line and ACP-prompt the live serve. No grok --resume."""
    seat = canonical_seat(seat)
    seat_dir = _seat_dir(seat)
    prepare_seat_home(seat, seat_dir)
    if seat in _skip_seats():
        print(f"WAKE_SKIP seat={seat} reason=skip-seat", flush=True)
        return {
            "consumed": 0,
            "serve_pid": _read_serve_pid(seat),
            "acp_session": pin_acp_session(seat_dir),
            "reason": "skip-seat",
        }
    records = _read_new_records(seat)
    if not records:
        return {
            "consumed": 0,
            "serve_pid": _read_serve_pid(seat),
            "acp_session": pin_acp_session(seat_dir),
            "reason": "empty",
        }

    for end_offset, rec in records:
        if rec.get("__corrupt__"):
            if not dry_run:
                _write_offset(seat, end_offset)
            continue
        task_id = str(rec.get("taskId") or "")
        text = _extract_text(rec.get("parts"))
        if not text:
            print(f"WAKE_SKIP seat={seat} reason=empty task={task_id}", flush=True)
            if not dry_run:
                _write_offset(seat, end_offset)
            continue
        extra = _compose_prompt(seat, rec, text)
        if dry_run:
            print(
                f"WAKE_DRY_RUN seat={seat} task={task_id} extra_chars={len(extra)}",
                flush=True,
            )
            break

        serve_pid = ensure_seat_serve(seat)
        if serve_pid <= 0:
            print(f"WAKE_FAIL seat={seat} task={task_id} reason=serve-down", file=sys.stderr)
            return {
                "consumed": 0,
                "serve_pid": 0,
                "acp_session": pin_acp_session(seat_dir),
                "reason": "serve-down",
            }

        from_seat = ""
        duplex = _duplex()
        if duplex is not None:
            try:
                from_seat = str(duplex.extract_caller(rec) or "")
            except Exception:
                from_seat = ""
        extra_env = os.environ.copy()
        extra_env["GCS_ROOT"] = str(ROOT)
        extra_env["GCS_A2A_STATE"] = str(STATE_DIR)
        extra_env["GCS_DIRECTOR_SEAT"] = seat
        extra_env["GCS_A2A_TASK_ID"] = task_id
        extra_env["GCS_A2A_CONTEXT"] = str(rec.get("contextId") or "")
        extra_env["GCS_A2A_SEAT"] = seat
        extra_env["GROK_HOME"] = str(seat_dir / "grok-home")
        extra_env["PATH"] = str(Path.home() / ".grok" / "bin") + ":" + extra_env.get("PATH", "")
        if from_seat:
            extra_env["GCS_A2A_FROM"] = from_seat

        rc = prompt_acp(seat, extra, extra_env)
        if rc != 0:
            print(f"WAKE_FAIL seat={seat} task={task_id} prompt_rc={rc}", file=sys.stderr)
            _append_log(seat, f"{_now()} FAIL seat={seat} task={task_id} rc={rc}")
            return {
                "consumed": 0,
                "serve_pid": serve_pid,
                "acp_session": pin_acp_session(seat_dir),
                "reason": "prompt-fail",
            }
        _write_offset(seat, end_offset)
        session = pin_acp_session(seat_dir)
        _append_log(
            seat,
            f"{_now()} ACP_PROMPT seat={seat} task={task_id} serve_pid={serve_pid} "
            f"session={session or 'none'}",
        )
        print(
            f"WAKE_ACP_PROMPT seat={seat} task={task_id} serve_pid={serve_pid} "
            f"session={session or 'none'}",
            flush=True,
        )
        return {
            "consumed": 1,
            "serve_pid": serve_pid,
            "acp_session": session,
            "task_id": task_id,
            "rc": rc,
        }

    return {
        "consumed": 0,
        "serve_pid": _read_serve_pid(seat),
        "acp_session": pin_acp_session(seat_dir),
        "reason": "no-actionable",
    }


def wait_for_inbox(seat: str, timeout: float = 30.0) -> None:
    """Block until inbox.jsonl grows past wake.offset (or timeout)."""
    inbox = _seat_dir(seat) / "inbox.jsonl"
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
    seat = canonical_seat(seat)
    _write_pid(seat)
    _write_wake_mode(seat)
    prepare_seat_home(seat, _seat_dir(seat))
    print(
        f"WAKE_READY seat={seat} state={STATE_DIR} mode=acp-serve",
        flush=True,
    )
    stopping = False

    def _handle(signum: int, _frame: Any) -> None:
        nonlocal stopping
        stopping = True
        print(f"WAKE_STOP seat={seat} signal={signum}", flush=True)

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)
    fail_streak = 0
    while not stopping:
        ensure_seat_serve(seat)
        result = process_once(seat)
        if result.get("consumed"):
            fail_streak = 0
            continue
        if result.get("reason") == "prompt-fail":
            fail_streak += 1
            delay = prompt_fail_backoff_sec(fail_streak)
            print(
                f"WAKE_BACKOFF seat={seat} delay={delay} streak={fail_streak} reason=prompt-fail",
                flush=True,
            )
            end = time.time() + delay
            while not stopping and time.time() < end:
                time.sleep(min(0.5, max(0.0, end - time.time())))
            continue
        fail_streak = 0
        wait_for_inbox(seat, timeout=30.0)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Grok Cloud Studio inbox wake (ACP session/prompt into grok agent serve)"
    )
    parser.add_argument("--seat", required=True, help="Director seat (floor, ops, …)")
    parser.add_argument("--once", action="store_true", help="Process one pending line then exit")
    parser.add_argument("--dry-run", action="store_true", help="Print compose text; do not prompt")
    args = parser.parse_args()
    seat = canonical_seat(args.seat)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if args.once or args.dry_run:
        process_once(seat, dry_run=args.dry_run)
        return 0
    return run_forever(seat)


if __name__ == "__main__":
    sys.exit(main())
