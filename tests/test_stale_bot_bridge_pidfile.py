"""Hive stale membership: leftover bot-bridge.pid is not a live daemon.

Complementary to GCS #74 (GCS_BOT_BRIDGE default-off when the pidfile is
missing). This file plants a dead pid in bot-bridge.pid and runs recover.sh
and doctor.sh. Do not restack tests/test_health_recover.py.
"""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RECOVER = REPO / "recover.sh"
DOCTOR = REPO / "doctor.sh"
HEALTH = REPO / "health_check.sh"
HEALTH_LIB = REPO / "scripts" / "studio" / "health-lib.sh"
BUS = REPO / "scripts" / "a2a" / "start-studio-bus.sh"
FEATURE = REPO / "tests" / "features" / "stale_bot_bridge_pidfile.feature"
WIPE = REPO / "docs" / "studio" / "WIPE.md"


def _run(
    script: Path,
    args: list[str],
    env: dict[str, str],
    *,
    timeout: int = 30,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(script), *args],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _base_env(tmp_path: Path, state: Path) -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    path = os.environ.get("PATH", "/usr/bin:/bin")
    if "/usr/bin" not in path.split(":"):
        path = f"{path}:/usr/bin:/bin"
    return {
        "PATH": path,
        "HOME": str(home),
        "GCS_ROOT": str(REPO),
        "GCS_A2A_STATE": str(state),
        "GCS_MIND_SEATS": "",
        "GCS_BOT_BIND_OPTIONAL": "1",
        "GCS_START_SEAT_DAEMONS": "0",
        "LC_ALL": "C",
        "TERM": "dumb",
        "CURSOR_API_KEY": "test-cursor-api-key-stale-pid-not-leaked",
    }


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        if path in ("/health", "/"):
            body = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


def _serve() -> tuple[ThreadingHTTPServer, int]:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _HealthHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, int(httpd.server_address[1])


def _spawn_sleep() -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        ["sleep", "60"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _write_pid(path: Path, pid: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{pid}\n", encoding="utf-8")


def _pidfile_pid(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        return int(path.read_text(encoding="utf-8").strip().split()[0])
    except (OSError, ValueError, IndexError):
        return 0


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _reap_pid(pid: int) -> None:
    if pid <= 0:
        return
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        return
    for _ in range(20):
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.05)


def _reap_proc(proc: subprocess.Popen[bytes] | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.kill()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        pass


def _dead_pid() -> int:
    """Return a pid that is not running (Hive leftover membership)."""
    proc = subprocess.Popen(
        ["sleep", "30"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    pid = int(proc.pid)
    proc.kill()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        _reap_pid(pid)
    assert not _pid_alive(pid), f"expected dead pid still alive: {pid}"
    return pid


def _plant_leftover_bus(state: Path) -> dict[str, subprocess.Popen[bytes]]:
    """Leftover hub/dispatch/shepherd so recover still starts the bus (HTTP hub down)."""
    state.mkdir(parents=True, exist_ok=True)
    procs: dict[str, subprocess.Popen[bytes]] = {
        "hub": _spawn_sleep(),
        "dispatch": _spawn_sleep(),
        "shepherd": _spawn_sleep(),
    }
    _write_pid(state / "hub.pid", procs["hub"].pid)
    _write_pid(state / "dispatch.pid", procs["dispatch"].pid)
    _write_pid(state / "fleet-shepherd.pid", procs["shepherd"].pid)
    (state / "dispatch.mind-seats").write_text("\n", encoding="utf-8")
    return procs


def _reap_bus_state(
    procs: dict[str, subprocess.Popen[bytes]], state: Path
) -> None:
    for name in ("hub", "dispatch", "fleet-shepherd", "bot-bridge"):
        _reap_pid(_pidfile_pid(state / f"{name}.pid"))
    for proc in procs.values():
        _reap_proc(proc)


def _bot_bridge_pids_for_state(state: Path) -> list[int]:
    """Live python bot-bridge.py processes whose environ points at this GCS_A2A_STATE."""
    marker = str(state.resolve())
    hits: list[int] = []
    proc_root = Path("/proc")
    if not proc_root.is_dir():
        return hits
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            cmdline = (entry / "cmdline").read_bytes().replace(b"\x00", b" ")
        except OSError:
            continue
        if b"bot-bridge.py" not in cmdline:
            continue
        try:
            environ = (entry / "environ").read_bytes()
        except OSError:
            continue
        if marker.encode("utf-8") not in environ:
            continue
        hits.append(int(entry.name))
    return hits


def test_stale_membership_feature_binds_recover_and_doctor() -> None:
    text = FEATURE.read_text(encoding="utf-8")
    fold = " ".join(text.lower().split())
    assert FEATURE.is_file()
    assert "stale" in fold
    assert "bot-bridge.pid" in fold
    assert "recover.sh" in fold
    assert "doctor.sh" in fold
    assert "not a live daemon" in fold or "not liveness" in fold
    assert "STUDIO_BUS_BOT_BRIDGE_START" in text
    assert "health_check.sh" in fold
    assert "bot-bridge.standby" in fold or "standby" in fold
    assert "resurrect" in fold
    wipe = WIPE.read_text(encoding="utf-8")
    assert "bot-bridge.pid" in wipe
    assert "stale" in wipe.lower()
    assert "bot-bridge.standby" in wipe
    lib = HEALTH_LIB.read_text(encoding="utf-8")
    assert "gcs_sweep_stale_bot_bridge_pidfile" in lib
    assert "bot-bridge.standby" in lib
    recover = RECOVER.read_text(encoding="utf-8")
    assert "gcs_sweep_stale_bot_bridge_pidfile" in recover
    doctor = DOCTOR.read_text(encoding="utf-8")
    assert "gcs_sweep_stale_bot_bridge_pidfile" in doctor
    health = HEALTH.read_text(encoding="utf-8")
    assert "gcs_sweep_stale_bot_bridge_pidfile" in health
    bus = BUS.read_text(encoding="utf-8")
    assert "STUDIO_BUS_BOT_BRIDGE_STALE" in bus
    assert "bot-bridge.standby" in bus
    assert "pidfile is not liveness" in bus or "not liveness" in bus


def test_doctor_removes_stale_bot_bridge_pidfile_and_does_not_start(
    tmp_path: Path,
) -> None:
    state = tmp_path / "a2a-state"
    state.mkdir(parents=True)
    dead = _dead_pid()
    pidfile = state / "bot-bridge.pid"
    _write_pid(pidfile, dead)
    assert pidfile.is_file()
    env = _base_env(tmp_path, state)
    try:
        proc = _run(DOCTOR, [], env, timeout=40)
        blob = proc.stdout + proc.stderr
        assert not pidfile.is_file(), f"doctor left stale pidfile pid={dead} out={blob}"
        assert (state / "bot-bridge.standby").is_file(), blob
        assert "STALE_PIDFILE" in blob, blob
        assert "bot-bridge.pid" in blob, blob
        assert str(dead) in blob, blob
        assert "STUDIO_BUS_BOT_BRIDGE_START" not in blob, blob
        live = _bot_bridge_pids_for_state(state)
        assert live == [], f"doctor started bot-bridge pids={live} out={blob}"
        assert "test-cursor-api-key-stale-pid-not-leaked" not in blob
    finally:
        for extra in _bot_bridge_pids_for_state(state):
            _reap_pid(extra)
        if pidfile.is_file():
            pidfile.unlink()


def test_doctor_keeps_live_bot_bridge_pidfile(tmp_path: Path) -> None:
    state = tmp_path / "a2a-state"
    sleeper = _spawn_sleep()
    pidfile = state / "bot-bridge.pid"
    _write_pid(pidfile, sleeper.pid)
    (state / "bot-bridge.standby").write_text("pid=ghost\n", encoding="utf-8")
    env = _base_env(tmp_path, state)
    try:
        proc = _run(DOCTOR, [], env, timeout=40)
        blob = proc.stdout + proc.stderr
        assert pidfile.is_file(), blob
        assert _pidfile_pid(pidfile) == sleeper.pid
        assert sleeper.poll() is None
        assert "STALE_PIDFILE" not in blob, blob
        assert not (state / "bot-bridge.standby").is_file(), blob
        live = _bot_bridge_pids_for_state(state)
        assert live == [], f"doctor started bot-bridge pids={live}"
    finally:
        _reap_proc(sleeper)
        if pidfile.is_file():
            pidfile.unlink()
        standby = state / "bot-bridge.standby"
        if standby.is_file():
            standby.unlink()


def test_recover_removes_stale_bot_bridge_pidfile_and_does_not_start(
    tmp_path: Path,
) -> None:
    """Dead pidfile + recover that starts the bus must not resurrect bot-bridge."""
    state = tmp_path / "a2a-state"
    procs = _plant_leftover_bus(state)
    dead = _dead_pid()
    pidfile = state / "bot-bridge.pid"
    _write_pid(pidfile, dead)
    env = _base_env(tmp_path, state)
    env["GCS_A2A_PORT"] = str(_free_port())
    ui, ui_port = _serve()
    mcp, mcp_port = _serve()
    env["GCS_TASKBOARD_UI_PORT"] = str(ui_port)
    env["GCS_TASKBOARD_MCP_PORT"] = str(mcp_port)
    try:
        proc = _run(RECOVER, [], env, timeout=40)
        blob = proc.stdout + proc.stderr
        assert "RECOVER_OK" in blob, blob
        assert "STUDIO_BUS_BOT_BRIDGE_START" not in blob, blob
        assert not pidfile.is_file(), f"recover left stale pidfile pid={dead} out={blob}"
        assert (state / "bot-bridge.standby").is_file(), blob
        assert "STUDIO_BUS_BOT_BRIDGE_STALE" in blob or "STALE_PIDFILE" in blob, blob
        live = _bot_bridge_pids_for_state(state)
        assert live == [], f"recover started bot-bridge pids={live} out={blob}"
        assert "test-cursor-api-key-stale-pid-not-leaked" not in blob
        assert "agent-kanban" not in blob.lower()
    finally:
        _reap_bus_state(procs, state)
        for extra in _bot_bridge_pids_for_state(state):
            _reap_pid(extra)
        ui.shutdown()
        mcp.shutdown()


def test_recover_sweeps_stale_pidfile_when_hub_already_up(tmp_path: Path) -> None:
    """recover.sh must drop stale membership even when it does not start the bus."""
    hub, hub_port = _serve()
    ui, ui_port = _serve()
    mcp, mcp_port = _serve()
    state = tmp_path / "a2a-state"
    state.mkdir(parents=True)
    dead = _dead_pid()
    pidfile = state / "bot-bridge.pid"
    _write_pid(pidfile, dead)
    env = _base_env(tmp_path, state)
    env["GCS_A2A_PORT"] = str(hub_port)
    env["GCS_TASKBOARD_UI_PORT"] = str(ui_port)
    env["GCS_TASKBOARD_MCP_PORT"] = str(mcp_port)
    try:
        proc = _run(RECOVER, [], env, timeout=40)
        blob = proc.stdout + proc.stderr
        assert "RECOVER_OK" in blob, blob
        assert "start-studio-bus.sh" not in blob
        assert "STUDIO_BUS_BOT_BRIDGE_START" not in blob, blob
        assert not pidfile.is_file(), f"recover left stale pidfile pid={dead} out={blob}"
        assert (state / "bot-bridge.standby").is_file(), blob
        assert "STALE_PIDFILE" in blob, blob
        live = _bot_bridge_pids_for_state(state)
        assert live == [], f"recover started bot-bridge pids={live} out={blob}"
    finally:
        for extra in _bot_bridge_pids_for_state(state):
            _reap_pid(extra)
        if pidfile.is_file():
            pidfile.unlink()
        hub.shutdown()
        ui.shutdown()
        mcp.shutdown()


def test_recover_keeps_live_bot_bridge_pidfile(tmp_path: Path) -> None:
    hub, hub_port = _serve()
    ui, ui_port = _serve()
    mcp, mcp_port = _serve()
    state = tmp_path / "a2a-state"
    sleeper = _spawn_sleep()
    pidfile = state / "bot-bridge.pid"
    _write_pid(pidfile, sleeper.pid)
    env = _base_env(tmp_path, state)
    env["GCS_A2A_PORT"] = str(hub_port)
    env["GCS_TASKBOARD_UI_PORT"] = str(ui_port)
    env["GCS_TASKBOARD_MCP_PORT"] = str(mcp_port)
    try:
        proc = _run(RECOVER, [], env, timeout=40)
        blob = proc.stdout + proc.stderr
        assert "RECOVER_OK" in blob, blob
        assert pidfile.is_file(), blob
        assert _pidfile_pid(pidfile) == sleeper.pid
        assert sleeper.poll() is None
        assert "STALE_PIDFILE" not in blob, blob
        live = _bot_bridge_pids_for_state(state)
        assert live == [], f"recover started bot-bridge pids={live}"
    finally:
        _reap_proc(sleeper)
        if pidfile.is_file():
            pidfile.unlink()
        hub.shutdown()
        ui.shutdown()
        mcp.shutdown()


def test_host_start_after_stale_eviction_does_not_resurrect(tmp_path: Path) -> None:
    """Eviction must stick. Watchdog/host start after a ghost pidfile must not rejoin."""
    state = tmp_path / "a2a-state"
    procs = _plant_leftover_bus(state)
    dead = _dead_pid()
    pidfile = state / "bot-bridge.pid"
    standby = state / "bot-bridge.standby"
    _write_pid(pidfile, dead)
    env = _base_env(tmp_path, state)
    env["GCS_A2A_PORT"] = str(_free_port())
    try:
        first = _run(BUS, ["start"], env, timeout=25)
        blob1 = first.stdout + first.stderr
        assert first.returncode == 0, blob1
        assert "STUDIO_BUS_BOT_BRIDGE_START" not in blob1, blob1
        assert "STUDIO_BUS_BOT_BRIDGE_STALE" in blob1, blob1
        assert not pidfile.is_file(), blob1
        assert standby.is_file(), blob1
        assert _bot_bridge_pids_for_state(state) == [], blob1

        second = _run(BUS, ["start"], env, timeout=25)
        blob2 = second.stdout + second.stderr
        assert second.returncode == 0, blob2
        assert "STUDIO_BUS_BOT_BRIDGE_START" not in blob2, blob2
        assert "STUDIO_BUS_BOT_BRIDGE_STALE" in blob2, blob2
        assert not pidfile.is_file(), blob2
        assert standby.is_file(), blob2
        live = _bot_bridge_pids_for_state(state)
        assert live == [], f"second start resurrected bot-bridge pids={live} out={blob2}"
    finally:
        _reap_bus_state(procs, state)
        for extra in _bot_bridge_pids_for_state(state):
            _reap_pid(extra)


def test_health_check_sweeps_stale_bot_bridge_pidfile(tmp_path: Path) -> None:
    hub, hub_port = _serve()
    ui, ui_port = _serve()
    mcp, mcp_port = _serve()
    state = tmp_path / "a2a-state"
    state.mkdir(parents=True)
    dead = _dead_pid()
    pidfile = state / "bot-bridge.pid"
    _write_pid(pidfile, dead)
    env = _base_env(tmp_path, state)
    env["GCS_A2A_PORT"] = str(hub_port)
    env["GCS_TASKBOARD_UI_PORT"] = str(ui_port)
    env["GCS_TASKBOARD_MCP_PORT"] = str(mcp_port)
    try:
        proc = _run(HEALTH, [], env, timeout=20)
        blob = proc.stdout + proc.stderr
        assert proc.returncode == 0, blob
        assert "HEALTH_OK" in blob, blob
        assert "STALE_PIDFILE" in blob, blob
        assert not pidfile.is_file(), blob
        assert (state / "bot-bridge.standby").is_file(), blob
        assert "STUDIO_BUS_BOT_BRIDGE_START" not in blob, blob
        live = _bot_bridge_pids_for_state(state)
        assert live == [], f"health_check started bot-bridge pids={live}"
    finally:
        for extra in _bot_bridge_pids_for_state(state):
            _reap_pid(extra)
        if pidfile.is_file():
            pidfile.unlink()
        hub.shutdown()
        ui.shutdown()
        mcp.shutdown()


def test_bus_status_evicts_stale_bot_bridge_pidfile(tmp_path: Path) -> None:
    state = tmp_path / "a2a-state"
    procs = _plant_leftover_bus(state)
    dead = _dead_pid()
    pidfile = state / "bot-bridge.pid"
    _write_pid(pidfile, dead)
    env = _base_env(tmp_path, state)
    try:
        proc = _run(BUS, ["status"], env, timeout=15)
        blob = proc.stdout + proc.stderr
        assert "STUDIO_BUS_BOT_BRIDGE_STALE" in blob, blob
        assert "STUDIO_BUS_BOT_BRIDGE_START" not in blob, blob
        assert not pidfile.is_file(), blob
        assert (state / "bot-bridge.standby").is_file(), blob
        assert "bot_bridge=down pid=none" in blob, blob
        live = _bot_bridge_pids_for_state(state)
        assert live == [], f"status started bot-bridge pids={live}"
    finally:
        _reap_bus_state(procs, state)
        for extra in _bot_bridge_pids_for_state(state):
            _reap_pid(extra)


def test_host_start_after_doctor_sweep_does_not_resurrect(tmp_path: Path) -> None:
    """Doctor eviction must stick when watchdog later runs start-studio-bus.sh start."""
    state = tmp_path / "a2a-state"
    procs = _plant_leftover_bus(state)
    dead = _dead_pid()
    pidfile = state / "bot-bridge.pid"
    standby = state / "bot-bridge.standby"
    _write_pid(pidfile, dead)
    env = _base_env(tmp_path, state)
    env["GCS_A2A_PORT"] = str(_free_port())
    try:
        doc = _run(DOCTOR, [], env, timeout=40)
        blob_d = doc.stdout + doc.stderr
        assert "STALE_PIDFILE" in blob_d, blob_d
        assert not pidfile.is_file(), blob_d
        assert standby.is_file(), blob_d
        assert _bot_bridge_pids_for_state(state) == [], blob_d

        started = _run(BUS, ["start"], env, timeout=25)
        blob = started.stdout + started.stderr
        assert started.returncode == 0, blob
        assert "STUDIO_BUS_BOT_BRIDGE_START" not in blob, blob
        assert "STUDIO_BUS_BOT_BRIDGE_STALE" in blob, blob
        assert not pidfile.is_file(), blob
        assert standby.is_file(), blob
        live = _bot_bridge_pids_for_state(state)
        assert live == [], f"host start after doctor resurrected bot-bridge pids={live} out={blob}"
        assert "test-cursor-api-key-stale-pid-not-leaked" not in blob
        assert "test-cursor-api-key-stale-pid-not-leaked" not in blob_d
    finally:
        _reap_bus_state(procs, state)
        for extra in _bot_bridge_pids_for_state(state):
            _reap_pid(extra)
