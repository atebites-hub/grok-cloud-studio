#!/usr/bin/env python3
"""Standing A2A inbox poller → Grok Build Director auto-dispatch.

Watches per-seat inbox.jsonl under STATE_DIR. Prefer persistent ACP inject
into per-seat `grok agent serve` daemons (scripts/directors/acp_inject.py).
If the daemon is down, start it only when the seat is in GCS_ACP_SEATS
(default floor,studio-ops). skipSeats never auto-start. Fall back to
one-shot launch-director.sh (-p) only when inject is impossible.

Hub remains protocol-ack; this process wakes seats so pings actually run work.
Local studio only. Stdlib only (acp_inject may use optional websockets).
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
from lib import launch_seats as _launch_seats_fn  # noqa: E402
from lib import skip_seats as _skip_seats_fn  # noqa: E402
from lib import repo_root as _repo_root  # noqa: E402
from lib import state_root as _state_root  # noqa: E402

ROOT = _repo_root()
STATE_DIR = _state_root(ROOT)
LAUNCHER = ROOT / "scripts" / "directors" / "launch-director.sh"
ACP_INJECT = ROOT / "scripts" / "directors" / "acp_inject.py"
START_DAEMON = ROOT / "scripts" / "directors" / "start-seat-daemon.sh"
POLL_SEC = float(os.environ.get("GCS_A2A_POLL_SEC", "2"))
LOCK_TTL_SEC = float(os.environ.get("GCS_DISPATCH_LOCK_TTL_SEC", "240"))
INJECT_TIMEOUT_SEC = float(os.environ.get("GCS_ACP_INJECT_TIMEOUT", "180"))


def _launch_seats() -> frozenset[str]:
    return frozenset(_launch_seats_fn(ROOT))


def _skip_seats() -> frozenset[str]:
    return _skip_seats_fn(ROOT)

# pid -> (seat, Popen, meta) for reaping; zombies accumulate without this.
_CHILDREN: dict[int, tuple[str, subprocess.Popen, dict[str, Any]]] = {}


def _duplex_mod() -> Any:
    path = ROOT / "scripts" / "a2a" / "duplex.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("gcs_a2a_duplex", path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _seat_dir(seat: str) -> Path:
    d = STATE_DIR / seat
    d.mkdir(parents=True, exist_ok=True)
    return d


def _inbox_path(seat: str) -> Path:
    return _seat_dir(seat) / "inbox.jsonl"


def _offset_path(seat: str) -> Path:
    return _seat_dir(seat) / "dispatch.offset"


def _lock_path(seat: str) -> Path:
    return _seat_dir(seat) / "dispatch.lock"


def _seat_dispatch_log(seat: str) -> Path:
    return _seat_dir(seat) / "dispatch.log"


def _runs_dir(seat: str) -> Path:
    d = _seat_dir(seat) / "runs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read_offset(seat: str) -> int:
    p = _offset_path(seat)
    if not p.is_file():
        return 0
    try:
        return max(0, int(p.read_text(encoding="utf-8").strip() or "0"))
    except ValueError:
        return 0


def _write_offset(seat: str, offset: int) -> None:
    p = _offset_path(seat)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(str(offset) + "\n", encoding="utf-8")
    tmp.replace(p)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # Zombies still pass kill(0); treat them as dead so locks can clear.
    try:
        with open(f"/proc/{pid}/status", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("State:"):
                    return not line.split(":", 1)[1].strip().startswith("Z")
    except OSError:
        return False
    return True


def _read_lock(seat: str) -> tuple[int | None, float | None]:
    """Return (pid, start_ts_epoch). Backward compatible with pid-only lock files."""
    p = _lock_path(seat)
    if not p.is_file():
        return None, None
    try:
        raw = p.read_text(encoding="utf-8").strip()
    except OSError:
        return None, None
    if not raw:
        return None, None
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    try:
        pid = int(lines[0].split()[0])
    except (ValueError, IndexError):
        return None, None
    start_ts: float | None = None
    if len(lines) >= 2:
        second = lines[1]
        try:
            start_ts = float(second)
        except ValueError:
            try:
                start_ts = datetime.fromisoformat(second.replace("Z", "+00:00")).timestamp()
            except ValueError:
                start_ts = None
    if start_ts is None:
        try:
            start_ts = p.stat().st_mtime
        except OSError:
            start_ts = None
    return pid, start_ts


def _read_lock_pid(seat: str) -> int | None:
    pid, _start = _read_lock(seat)
    return pid


def _clear_lock(seat: str) -> None:
    try:
        _lock_path(seat).unlink(missing_ok=True)
    except OSError:
        pass


def _kill_lock_pid(seat: str, pid: int, *, age: float) -> None:
    print(
        f"DISPATCH_LOCK_TTL_KILL seat={seat} pid={pid} age={age:.1f}s ttl={LOCK_TTL_SEC}",
        flush=True,
    )
    _append_seat_log(
        seat,
        f"{_now()} LOCK_TTL_KILL seat={seat} pid={pid} age={age:.1f}s ttl={LOCK_TTL_SEC}",
    )
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        _clear_lock(seat)
        return
    except PermissionError:
        pass
    deadline = time.time() + 2.0
    while time.time() < deadline:
        if not _pid_alive(pid):
            break
        time.sleep(0.1)
    if _pid_alive(pid):
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    child = _CHILDREN.pop(pid, None)
    if child is not None:
        _seat, proc, _meta = child
        try:
            proc.poll()
        except Exception:
            pass
    _clear_lock(seat)


def _seat_locked(seat: str) -> bool:
    pid, start_ts = _read_lock(seat)
    if pid is None:
        return False
    if not _pid_alive(pid):
        _clear_lock(seat)
        return False
    age = 0.0
    if start_ts is not None:
        age = max(0.0, time.time() - start_ts)
    else:
        try:
            age = max(0.0, time.time() - _lock_path(seat).stat().st_mtime)
        except OSError:
            age = 0.0
    if LOCK_TTL_SEC > 0 and age > LOCK_TTL_SEC:
        _kill_lock_pid(seat, pid, age=age)
        return False
    return True


def _write_lock(seat: str, pid: int) -> None:
    p = _lock_path(seat)
    tmp = p.with_suffix(".tmp")
    start = time.time()
    tmp.write_text(f"{pid}\n{start:.6f}\n", encoding="utf-8")
    tmp.replace(p)


def _append_seat_log(seat: str, line: str) -> None:
    with _seat_dispatch_log(seat).open("a", encoding="utf-8") as f:
        f.write(line.rstrip() + "\n")


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


def _compose_extra(task_id: str, context_id: str, text: str) -> str:
    return (
        f"A2A_TASK_ID={task_id}\n"
        f"A2A_CONTEXT={context_id}\n"
        "You were woken by the local A2A dispatch bus (persistent ACP inject when "
        "available). Prioritize this ping in EXTRA TURN INSTRUCTIONS: act on it, "
        "then print the required RESULT (or PARK_ACK / QA_*_RESULT) line. "
        "Do not call scripts/a2a/send.sh or a2a_send to ack the caller — print "
        "RESULT; duplex writes that line onto the A2A task and notifies the caller "
        "seat. Use send.sh only for new work pings to other seats. "
        "If you are on a persistent ACP seat daemon, idle for the next inject — "
        "do not exit the process. One-shot -p fallbacks may exit after RESULT.\n"
        "\n"
        "MESSAGE:\n"
        f"{text}\n"
    )


def _discover_seats(filter_seats: set[str] | None) -> list[str]:
    found: set[str] = set(_launch_seats()) | set(_skip_seats())
    if STATE_DIR.is_dir():
        for child in STATE_DIR.iterdir():
            if child.is_dir() and not child.name.startswith("."):
                found.add(child.name)
    seats = sorted(found)
    if filter_seats is not None:
        seats = [s for s in seats if s in filter_seats]
    return seats


def _read_new_records(seat: str) -> tuple[list[tuple[int, dict[str, Any]]], int]:
    """Return (list of (end_offset, record), current_file_size).

    end_offset is the byte position after each complete line.
    """
    path = _inbox_path(seat)
    if not path.is_file():
        return [], 0
    size = path.stat().st_size
    offset = _read_offset(seat)
    if offset > size:
        # Truncated/rotated inbox — restart from beginning
        offset = 0
    records: list[tuple[int, dict[str, Any]]] = []
    with path.open("rb") as f:
        f.seek(offset)
        while True:
            line_start = f.tell()
            raw = f.readline()
            if not raw:
                break
            if not raw.endswith(b"\n"):
                # Incomplete trailing line — wait for more
                break
            end = f.tell()
            try:
                text = raw.decode("utf-8")
                rec = json.loads(text)
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                print(
                    f"DISPATCH_WARN seat={seat} bad_json offset={line_start}: {e}",
                    file=sys.stderr,
                )
                # Skip corrupt line by advancing past it
                records.append((end, {"__corrupt__": True, "taskId": f"corrupt-{end}"}))
                continue
            if not isinstance(rec, dict):
                records.append((end, {"__corrupt__": True, "taskId": f"corrupt-{end}"}))
                continue
            records.append((end, rec))
    return records, size


def _daemon_pid_path(seat: str) -> Path:
    return _seat_dir(seat) / "daemon.pid"


def _daemon_healthy(seat: str) -> bool:
    """True when seat ACP daemon pid is alive (non-zombie) and acp.url exists."""
    sd = _seat_dir(seat)
    url = sd / "acp.url"
    secret = sd / "acp.secret"
    pid_path = sd / "daemon.pid"
    if not (url.is_file() and secret.is_file() and pid_path.is_file()):
        return False
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip().split()[0])
    except (ValueError, IndexError, OSError):
        return False
    return _pid_alive(pid)


def _studio_env() -> dict[str, str]:
    """Crash-safe overrides from .a2a-state/studio.env (GCS_* / GROK_USE_LEADER only)."""
    out: dict[str, str] = {}
    env_file = STATE_DIR / "studio.env"
    if not env_file.is_file():
        return out
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        if k in {"GCS_ACP_SEATS", "GROK_USE_LEADER"}:
            out[k] = v.strip().strip('"').strip("'")
    return out


def _acp_seat_allowlist() -> frozenset[str]:
    """Seats dispatch may auto-start. Default floor+ops (never the full registry)."""
    raw = os.environ.get("GCS_ACP_SEATS")
    if raw is None or not str(raw).strip():
        raw = _studio_env().get("GCS_ACP_SEATS", "floor,studio-ops")
    seats = {s.strip() for s in raw.split(",") if s.strip()}
    # GCS example registry names the ops seat "ops"; product floors use studio-ops.
    if "studio-ops" in seats:
        seats.add("ops")
    if "ops" in seats:
        seats.add("studio-ops")
    return frozenset(seats) - _skip_seats()


def _ensure_daemon(seat: str) -> bool:
    """Start seat daemon if needed. Returns True if healthy afterward."""
    if _daemon_healthy(seat):
        return True
    allow = _acp_seat_allowlist()
    if seat not in allow:
        print(
            f"DISPATCH_DAEMON_SKIP seat={seat} reason=not-in-GCS_ACP_SEATS",
            file=sys.stderr,
        )
        return False
    if not START_DAEMON.is_file():
        return False
    try:
        proc = subprocess.run(
            ["bash", str(START_DAEMON), seat],
            cwd=str(ROOT),
            env={**os.environ, "GCS_ROOT": str(ROOT), "GCS_A2A_STATE": str(STATE_DIR), "GCS_DIRECTOR_SEAT": seat},
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"DISPATCH_DAEMON_START_FAIL seat={seat} err={e}", file=sys.stderr)
        return False
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.returncode != 0:
        if proc.stderr:
            print(proc.stderr.rstrip(), file=sys.stderr)
        print(f"DISPATCH_DAEMON_START_FAIL seat={seat} rc={proc.returncode}", file=sys.stderr)
        return False
    # Brief settle
    for _ in range(20):
        if _daemon_healthy(seat):
            return True
        time.sleep(0.25)
    return _daemon_healthy(seat)


def _reap_finished() -> None:
    """Poll launched children; clear seat locks so the next inbox line can fire.

    Without this, exited launch-director/grok processes stay zombie (kill(0) still
    succeeds) and DISPATCH_BUSY stalls the studio. Only use Popen.poll() — do not
    also waitpid(-1), or we race the Popen wait machinery.
    """
    done: list[int] = []
    duplex = _duplex_mod()
    for pid, (seat, proc, meta) in list(_CHILDREN.items()):
        rc = proc.poll()
        if rc is None:
            continue
        done.append(pid)
        lock_pid = _read_lock_pid(seat)
        if lock_pid == pid:
            try:
                _lock_path(seat).unlink(missing_ok=True)
            except OSError:
                pass
        log_path = Path(str(meta.get("log_path") or ""))
        output = ""
        if log_path.is_file():
            try:
                output = log_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                output = ""
        if duplex is not None:
            rec = meta.get("record") if isinstance(meta.get("record"), dict) else {}
            try:
                duplex.duplex_from_output(
                    state_dir=STATE_DIR,
                    seat=seat,
                    record=rec,
                    output_text=output,
                )
            except Exception as e:  # noqa: BLE001 — reap must continue
                print(f"DISPATCH_DUPLEX_ERR seat={seat} err={e}", file=sys.stderr)
        _append_seat_log(
            seat,
            f"{_now()} EXIT seat={seat} pid={pid} rc={rc}",
        )
        print(f"DISPATCH_EXIT seat={seat} pid={pid} rc={rc}")
    for pid in done:
        _CHILDREN.pop(pid, None)


def _process_seat(seat: str, *, dry_run: bool) -> int:
    """Process pending inbox records for one seat. Returns launches started."""
    records, _size = _read_new_records(seat)
    if not records:
        return 0

    launched = 0
    for end_offset, rec in records:
        if rec.get("__corrupt__"):
            if not dry_run:
                _write_offset(seat, end_offset)
            continue

        task_id = str(rec.get("taskId") or "")
        context_id = str(rec.get("contextId") or "")
        text = _extract_text(rec.get("parts"))

        # Always advance past skipped, non-launch, or empty records.
        if seat in _skip_seats():
            print(f"DISPATCH_SKIP seat={seat} reason=skip-seat task={task_id}")
            if not dry_run:
                _write_offset(seat, end_offset)
            continue

        if seat not in _launch_seats():
            print(f"DISPATCH_SKIP seat={seat} reason=not-in-launch-map task={task_id}")
            if not dry_run:
                _write_offset(seat, end_offset)
            continue

        if not text:
            print(f"DISPATCH_SKIP seat={seat} reason=empty task={task_id}")
            if not dry_run:
                _write_offset(seat, end_offset)
            continue

        if _seat_locked(seat):
            print(
                f"DISPATCH_BUSY seat={seat} task={task_id} "
                f"(lock held; offset not advanced)"
            )
            # Do not advance — retry later. Stop processing further lines
            # for this seat so order is preserved.
            break

        extra = _compose_extra(task_id, context_id, text)

        if dry_run:
            mode = "acp-inject" if _daemon_healthy(seat) else "start-daemon+inject|fallback-p"
            print(
                f"DISPATCH_DRY_RUN seat={seat} task={task_id} context={context_id} "
                f"mode={mode} extra_chars={len(extra)}"
            )
            print("--- EXTRA BEGIN ---")
            print(extra.rstrip())
            print("--- EXTRA END ---")
            # dry-run must NOT advance offset
            # Only show first pending actionable record per seat per cycle
            break

        log_path = _runs_dir(seat) / f"{task_id or 'unknown'}.log"
        env = os.environ.copy()
        env["GCS_ROOT"] = str(ROOT)
        env["GCS_A2A_STATE"] = str(STATE_DIR)
        env["GCS_DIRECTOR_SEAT"] = seat
        env["PATH"] = str(Path.home() / ".grok" / "bin") + ":" + env.get("PATH", "")
        env["GCS_A2A_TASK_ID"] = task_id
        env["GCS_A2A_CONTEXT"] = context_id
        duplex = _duplex_mod()
        from_seat = ""
        if duplex is not None:
            try:
                from_seat = str(duplex.extract_caller(rec) or "")
            except Exception:
                from_seat = ""
        if from_seat:
            env["GCS_A2A_FROM"] = from_seat
        env["GCS_A2A_SEAT"] = seat

        try:
            log_f = log_path.open("w", encoding="utf-8")
        except OSError as e:
            print(f"DISPATCH_FAIL seat={seat} task={task_id} log_open: {e}", file=sys.stderr)
            break

        mode = "fallback-p"
        cmd: list[str]
        # Prefer persistent ACP inject
        if ACP_INJECT.is_file() and (_daemon_healthy(seat) or _ensure_daemon(seat)):
            if _daemon_healthy(seat):
                mode = "acp-inject"
                inject_timeout = INJECT_TIMEOUT_SEC
                if LOCK_TTL_SEC > 30:
                    inject_timeout = min(inject_timeout, LOCK_TTL_SEC - 30)
                inject_timeout = max(1.0, inject_timeout)
                cmd = [
                    sys.executable,
                    str(ACP_INJECT),
                    "--timeout",
                    str(inject_timeout),
                    seat,
                    extra,
                ]
            else:
                mode = "fallback-p"
                cmd = [str(LAUNCHER), seat, extra]
        else:
            mode = "fallback-p"
            cmd = [str(LAUNCHER), seat, extra]

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(ROOT),
                env=env,
                stdout=log_f,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as e:
            log_f.close()
            print(f"DISPATCH_FAIL seat={seat} task={task_id} launch: {e}", file=sys.stderr)
            break

        _write_lock(seat, proc.pid)
        _CHILDREN[proc.pid] = (
            seat,
            proc,
            {"record": rec, "log_path": str(log_path), "task_id": task_id},
        )
        _write_offset(seat, end_offset)
        _append_seat_log(
            seat,
            f"{_now()} LAUNCH seat={seat} task={task_id} mode={mode} pid={proc.pid} log={log_path}",
        )
        marker = "DISPATCH_ACP_INJECT" if mode == "acp-inject" else "DISPATCH_LAUNCH"
        print(
            f"{marker} seat={seat} task={task_id} mode={mode} pid={proc.pid} log={log_path}"
        )
        # Parent no longer needs the log handle; child owns the fd
        log_f.close()
        launched += 1
        # One concurrent launch/inject per seat
        break

    return launched


def run_cycle(seats: list[str], *, dry_run: bool) -> int:
    if not dry_run:
        _reap_finished()
    total = 0
    for seat in seats:
        total += _process_seat(seat, dry_run=dry_run)
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description="Grok Cloud Studio A2A inbox → seat dispatch")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process pending inbox lines once then exit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would launch; do not advance offsets or launch",
    )
    parser.add_argument(
        "--seats",
        default="",
        help="Comma-separated seat filter (e.g. qa-a,qa-b,audio)",
    )
    args = parser.parse_args()

    filter_seats: set[str] | None = None
    if args.seats.strip():
        filter_seats = {s.strip() for s in args.seats.split(",") if s.strip()}

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    seats = _discover_seats(filter_seats)
    print(
        f"DISPATCH_READY state={STATE_DIR} seats={','.join(seats) or '(none)'} "
        f"poll={POLL_SEC}s lock_ttl={LOCK_TTL_SEC}s inject_timeout={INJECT_TIMEOUT_SEC}s "
        f"once={int(args.once)} dry_run={int(args.dry_run)}"
    )

    if not LAUNCHER.is_file() and not ACP_INJECT.is_file():
        print(
            f"DISPATCH_FAIL missing launcher and acp_inject: {LAUNCHER} / {ACP_INJECT}",
            file=sys.stderr,
        )
        return 1

    stopping = False

    def _handle_signal(signum: int, _frame: Any) -> None:
        nonlocal stopping
        stopping = True
        print(f"DISPATCH_STOP signal={signum}")

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)
    # Wake the poll sleep when children exit so we reap promptly (no zombie pile).
    signal.signal(signal.SIGCHLD, lambda *_: None)

    if args.once:
        run_cycle(seats, dry_run=args.dry_run)
        return 0

    while not stopping:
        run_cycle(seats, dry_run=args.dry_run)
        # Re-discover in case new seat dirs appear
        seats = _discover_seats(filter_seats)
        # Sleep in small slices so signals stop promptly
        end = time.time() + POLL_SEC
        while not stopping and time.time() < end:
            time.sleep(min(0.25, max(0.0, end - time.time())))

    return 0


if __name__ == "__main__":
    sys.exit(main())
