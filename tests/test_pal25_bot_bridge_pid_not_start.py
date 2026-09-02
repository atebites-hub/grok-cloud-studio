"""PAL-25 remaining (beat1849): leftover bot-bridge.pid is not a default start.

#74 covers missing-pidfile spawn skip (unset/0/empty → STUDIO_BUS_BOT_BRIDGE_SKIP).
This file is the leftover-pid / kill-after-RECOVER gap: a live bot-bridge.pid
must not stay up after recover/start when GCS_BOT_BRIDGE is not 1.
STUDIO_BUS_BOT_BRIDGE_ALREADY is not a default start. When GCS_BOT_BRIDGE=1,
recover/start must not remint that live pid (same pid, ALREADY, no START).

Distinct from leftover:
  GCS #36 (default keep-alive of leftover live pid)
  GCS #74 / #108 (missing pidfile spawn skip)
  GCS #77 (stale/dead pidfile tombstone)
  GCS #131 (beat1740 leftover-pid eviction)

Never Bot CloudAgent. Never print credentials. Agent Kanban stays gone.
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

import pytest

REPO = Path(__file__).resolve().parents[1]
RECOVER = REPO / "recover.sh"
BUS = REPO / "scripts" / "a2a" / "start-studio-bus.sh"
FEATURE = REPO / "tests" / "features" / "pal25_bot_bridge_pid_not_start.feature"
PRIVATE_GAME = "atebites-hub/" + "palemon"
SECRET = "test-cursor-api-key-health-not-leaked"


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


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


def _base_env(tmp_path: Path, state: Path) -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "GCS_ROOT": str(REPO),
        "GCS_A2A_STATE": str(state),
        "GCS_MIND_SEATS": "",
        "GCS_BOT_BIND_OPTIONAL": "1",
        "GCS_START_SEAT_DAEMONS": "0",
        "LC_ALL": "C",
        "TERM": "dumb",
        "CURSOR_API_KEY": SECRET,
    }


def _recover_env(tmp_path: Path, state: Path) -> dict[str, str]:
    env = _base_env(tmp_path, state)
    env["GCS_A2A_PORT"] = str(_free_port())
    env["GCS_TASKBOARD_UI_PORT"] = str(_free_port())
    env["GCS_TASKBOARD_MCP_PORT"] = str(_free_port())
    env.pop("GCS_BOT_BRIDGE", None)
    return env


def _spawn_sleep() -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        ["sleep", "60"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _write_pid(path: Path, proc: subprocess.Popen[bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{proc.pid}\n", encoding="utf-8")


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


def _plant_leftover_bus_with_bot_bridge(
    state: Path,
) -> dict[str, subprocess.Popen[bytes]]:
    """Leftover hub/dispatch/shepherd plus a live bot-bridge.pid (sleep stand-in)."""
    state.mkdir(parents=True, exist_ok=True)
    procs: dict[str, subprocess.Popen[bytes]] = {
        "hub": _spawn_sleep(),
        "dispatch": _spawn_sleep(),
        "shepherd": _spawn_sleep(),
        "bot-bridge": _spawn_sleep(),
    }
    _write_pid(state / "hub.pid", procs["hub"])
    _write_pid(state / "dispatch.pid", procs["dispatch"])
    _write_pid(state / "fleet-shepherd.pid", procs["shepherd"])
    _write_pid(state / "bot-bridge.pid", procs["bot-bridge"])
    (state / "dispatch.mind-seats").write_text("\n", encoding="utf-8")
    return procs


def _reap_bus_state(
    procs: dict[str, subprocess.Popen[bytes]], state: Path
) -> None:
    for name in ("hub", "dispatch", "fleet-shepherd", "bot-bridge"):
        _reap_pid(_pidfile_pid(state / f"{name}.pid"))
    for proc in procs.values():
        _reap_proc(proc)


def _bot_bridge_py_pids_for_state(state: Path) -> list[int]:
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


def _assert_secret_free(blob: str) -> None:
    assert SECRET not in blob
    assert "CURSOR_API_KEY=" not in blob
    assert "TAILSCALE_AUTH_KEY=" not in blob
    assert PRIVATE_GAME not in blob
    assert "agent-kanban" not in blob.lower()
    assert "ak start" not in blob


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


def _assert_leftover_not_default_start(
    blob: str,
    leftover_pid: int,
    state: Path,
    leftover_proc: subprocess.Popen[bytes],
) -> None:
    """Kill-after-RECOVER must not still be required."""
    assert "STUDIO_BUS_BOT_BRIDGE_START" not in blob, blob
    assert "STUDIO_BUS_BOT_BRIDGE_ALREADY" not in blob, blob
    assert leftover_proc.poll() is not None, (
        f"leftover bot-bridge pid={leftover_pid} still live after default recover/start"
    )
    assert not _pid_alive(leftover_pid), f"leftover pid={leftover_pid} still alive"
    pidfile = _pidfile_pid(state / "bot-bridge.pid")
    assert not _pid_alive(pidfile), f"pidfile still names a live process pid={pidfile}"
    live_py = _bot_bridge_py_pids_for_state(state)
    assert live_py == [], f"default path left live bot-bridge.py pids={live_py}"


def test_feature_binds_leftover_pid_not_a_default_start() -> None:
    text = FEATURE.read_text(encoding="utf-8")
    fold = " ".join(text.lower().split())
    assert FEATURE.is_file()
    assert "pal-25" in fold
    assert "leftover bot-bridge.pid is not a default start" in fold
    assert "must not restart a live bot-bridge pid" in fold
    assert "recover.sh" in fold
    assert "start-studio-bus.sh" in fold
    assert "gcs_bot_bridge=1" in fold
    assert "studio_bus_bot_bridge_already" in fold
    assert "demonstrate" in fold and "theatre" in fold
    bus = BUS.read_text(encoding="utf-8")
    assert "want_bot_bridge" in bus
    recover = RECOVER.read_text(encoding="utf-8")
    assert "start-studio-bus.sh start --daemons" not in recover
    for line in recover.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assert "export GCS_BOT_BRIDGE=1" not in stripped
        assert not stripped.startswith("GCS_BOT_BRIDGE=1")
        assert "GCS_BOT_BRIDGE=${GCS_BOT_BRIDGE:-1}" not in stripped


@pytest.mark.parametrize("bridge_value", [None, "", "0"], ids=["unset", "empty", "zero"])
def test_recover_leftover_pid_is_not_a_default_start(
    tmp_path: Path, bridge_value: str | None
) -> None:
    state = tmp_path / "a2a-state"
    procs = _plant_leftover_bus_with_bot_bridge(state)
    leftover = int(procs["bot-bridge"].pid)
    env = _recover_env(tmp_path, state)
    if bridge_value is not None:
        env["GCS_BOT_BRIDGE"] = bridge_value
    else:
        assert "GCS_BOT_BRIDGE" not in env
    try:
        proc = _run(RECOVER, [], env, timeout=30)
        blob = proc.stdout + proc.stderr
        assert "RECOVER_OK" in blob, blob
        _assert_secret_free(blob)
        _assert_leftover_not_default_start(
            blob, leftover, state, procs["bot-bridge"]
        )
        assert (
            "STUDIO_BUS_BOT_BRIDGE_SKIP" in blob
            or "RECOVER_BOT_BRIDGE_EVICT" in blob
        ), blob
    finally:
        _reap_bus_state(procs, state)
        for extra in _bot_bridge_py_pids_for_state(state):
            _reap_pid(extra)


def test_recover_evicts_leftover_bot_bridge_when_hub_http_is_up(
    tmp_path: Path,
) -> None:
    """Bus already up must still not leave leftover Bot wake after RECOVER_OK."""
    hub, hub_port = _serve()
    state = tmp_path / "a2a-state"
    procs = _plant_leftover_bus_with_bot_bridge(state)
    leftover = int(procs["bot-bridge"].pid)
    env = _recover_env(tmp_path, state)
    env["GCS_A2A_PORT"] = str(hub_port)
    try:
        proc = _run(RECOVER, [], env, timeout=30)
        blob = proc.stdout + proc.stderr
        assert "RECOVER_OK" in blob, blob
        assert "start-studio-bus.sh" not in blob, blob
        _assert_secret_free(blob)
        assert procs["bot-bridge"].poll() is not None, blob
        assert not _pid_alive(leftover), f"leftover pid={leftover} still alive"
        assert "STUDIO_BUS_BOT_BRIDGE_START" not in blob, blob
        assert "STUDIO_BUS_BOT_BRIDGE_ALREADY" not in blob, blob
    finally:
        hub.shutdown()
        _reap_bus_state(procs, state)
        for extra in _bot_bridge_py_pids_for_state(state):
            _reap_pid(extra)


@pytest.mark.parametrize("bridge_value", [None, "", "0"], ids=["unset", "empty", "zero"])
def test_start_leftover_pid_is_not_studio_bus_already(
    tmp_path: Path, bridge_value: str | None
) -> None:
    state = tmp_path / "a2a-state"
    procs = _plant_leftover_bus_with_bot_bridge(state)
    leftover = int(procs["bot-bridge"].pid)
    env = _base_env(tmp_path, state)
    env["PATH"] = os.environ.get("PATH", "/usr/bin:/bin")
    if bridge_value is not None:
        env["GCS_BOT_BRIDGE"] = bridge_value
    else:
        env.pop("GCS_BOT_BRIDGE", None)
    try:
        proc = _run(BUS, ["start"], env, timeout=25)
        blob = proc.stdout + proc.stderr
        assert proc.returncode == 0, blob
        _assert_secret_free(blob)
        _assert_leftover_not_default_start(
            blob, leftover, state, procs["bot-bridge"]
        )
        assert "STUDIO_BUS_BOT_BRIDGE_SKIP" in blob, blob
        assert "STUDIO_BUS_BOT_BRIDGE_STOP" in blob, blob
    finally:
        _reap_bus_state(procs, state)
        for extra in _bot_bridge_py_pids_for_state(state):
            _reap_pid(extra)


def test_opt_in_start_does_not_restart_live_bot_bridge_pid(tmp_path: Path) -> None:
    """GCS_BOT_BRIDGE=1 keeps the leftover live pid. Remint is a bug."""
    state = tmp_path / "a2a-state"
    procs = _plant_leftover_bus_with_bot_bridge(state)
    leftover = int(procs["bot-bridge"].pid)
    env = _base_env(tmp_path, state)
    env["PATH"] = os.environ.get("PATH", "/usr/bin:/bin")
    env["GCS_BOT_BRIDGE"] = "1"
    env["GCS_BOT_BRIDGE_POLL_SEC"] = "60"
    try:
        proc = _run(BUS, ["start"], env, timeout=25)
        blob = proc.stdout + proc.stderr
        assert proc.returncode == 0, blob
        _assert_secret_free(blob)
        assert "STUDIO_BUS_BOT_BRIDGE_ALREADY" in blob, blob
        assert f"pid={leftover}" in blob, blob
        assert "STUDIO_BUS_BOT_BRIDGE_START" not in blob, blob
        assert "STUDIO_BUS_BOT_BRIDGE_STOP" not in blob, blob
        assert "STUDIO_BUS_BOT_BRIDGE_SKIP" not in blob, blob
        assert procs["bot-bridge"].poll() is None
        assert _pid_alive(leftover)
        assert _pidfile_pid(state / "bot-bridge.pid") == leftover
        live_py = _bot_bridge_py_pids_for_state(state)
        assert live_py == [], f"opt-in reminted bot-bridge.py pids={live_py}"
    finally:
        _reap_bus_state(procs, state)
        for extra in _bot_bridge_py_pids_for_state(state):
            _reap_pid(extra)


def test_opt_in_recover_does_not_restart_live_bot_bridge_pid(tmp_path: Path) -> None:
    state = tmp_path / "a2a-state"
    procs = _plant_leftover_bus_with_bot_bridge(state)
    leftover = int(procs["bot-bridge"].pid)
    env = _recover_env(tmp_path, state)
    env["GCS_BOT_BRIDGE"] = "1"
    env["GCS_BOT_BRIDGE_POLL_SEC"] = "60"
    try:
        proc = _run(RECOVER, [], env, timeout=30)
        blob = proc.stdout + proc.stderr
        assert "RECOVER_OK" in blob, blob
        _assert_secret_free(blob)
        assert "RECOVER_BOT_BRIDGE_EVICT" not in blob, blob
        assert "STUDIO_BUS_BOT_BRIDGE_START" not in blob, blob
        assert "STUDIO_BUS_BOT_BRIDGE_STOP" not in blob, blob
        assert "STUDIO_BUS_BOT_BRIDGE_ALREADY" in blob, blob
        assert procs["bot-bridge"].poll() is None
        assert _pid_alive(leftover)
        assert _pidfile_pid(state / "bot-bridge.pid") == leftover
    finally:
        _reap_bus_state(procs, state)
        for extra in _bot_bridge_py_pids_for_state(state):
            _reap_pid(extra)
