"""Live-service health_check.sh + recover.sh DR loop. No secrets, no Agent Kanban."""
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
HEALTH = REPO / "health_check.sh"
RECOVER = REPO / "recover.sh"
SETUP = REPO / "setup.sh"
INSTALL = REPO / "install.sh"
DOCTOR = REPO / "doctor.sh"
WIPE = REPO / "docs" / "studio" / "WIPE.md"
README = REPO / "README.md"
BUS = REPO / "scripts" / "a2a" / "start-studio-bus.sh"
STUDIO_ENV_EXAMPLE = REPO / "studio.env.example"
PAL25_FEATURE = REPO / "tests" / "features" / "pal25_recover_bot_bridge_off.feature"

PRIVATE_GAME = "atebites-hub/" + "palemon"


def _run(
    script: Path,
    args: list[str],
    env: dict[str, str],
    *,
    timeout: int = 20,
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
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": str(home),
        "GCS_ROOT": str(REPO),
        "GCS_A2A_STATE": str(state),
        "GCS_MIND_SEATS": "",
        "GCS_BOT_BIND_OPTIONAL": "1",
        "LC_ALL": "C",
        "TERM": "dumb",
        "CURSOR_API_KEY": "test-cursor-api-key-health-not-leaked",
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


def test_health_and_recover_scripts_exist() -> None:
    assert HEALTH.is_file(), "missing health_check.sh"
    assert RECOVER.is_file(), "missing recover.sh"


def test_install_chmods_health_and_recover() -> None:
    text = INSTALL.read_text(encoding="utf-8")
    assert '"$ROOT/health_check.sh"' in text
    assert '"$ROOT/recover.sh"' in text
    assert "chmod +x" in text


def test_doctor_lists_health_and_recover() -> None:
    text = DOCTOR.read_text(encoding="utf-8")
    assert "health_check.sh" in text
    assert "recover.sh" in text


def test_setup_ends_with_health_check() -> None:
    text = SETUP.read_text(encoding="utf-8")
    assert "health_check.sh" in text
    assert "GCS_SETUP_SKIP_HEALTH" in text
    idx_ok = text.rfind("SETUP_OK")
    idx_health = text.rfind("health_check.sh")
    assert idx_ok != -1 and idx_health != -1
    assert idx_health > idx_ok


def test_help_and_secret_free_no_ak() -> None:
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": "/tmp",
        "GCS_ROOT": str(REPO),
        "LC_ALL": "C",
        "TERM": "dumb",
        "CURSOR_API_KEY": "test-cursor-api-key-health-not-leaked",
    }
    for script, token in ((HEALTH, "HEALTH"), (RECOVER, "RECOVER")):
        proc = _run(script, ["--help"], env)
        blob = proc.stdout + proc.stderr
        assert proc.returncode == 0, blob
        assert "Usage" in blob or "--help" in blob or script.name in blob
        assert token.lower() in blob.lower() or script.name in blob
        assert "CURSOR_API_KEY=" not in blob
        assert "test-cursor-api-key-health-not-leaked" not in blob
        assert "TAILSCALE_AUTH_KEY=" not in blob

    for path in (HEALTH, RECOVER):
        text = path.read_text(encoding="utf-8")
        assert "agent-kanban" not in text
        assert "ak start" not in text
        assert "mint-floor-ops-worker" not in text
        assert "echo \"$CURSOR_API_KEY\"" not in text
        assert "echo $CURSOR_API_KEY" not in text
        assert "CURSOR_API_KEY=" not in text
        assert "TAILSCALE_AUTH_KEY=" not in text
        assert PRIVATE_GAME not in text
        assert "launch-cloud-extra-high" not in text
        assert "session/new" not in text
        assert "CLEANUP_WIPE" not in text
        assert "remint" not in text.lower() or "do not remint" in text.lower()


def test_recover_uses_official_scripts_without_daemons() -> None:
    text = RECOVER.read_text(encoding="utf-8")
    assert "start-studio-bus.sh start" in text
    assert "start-studio-bus.sh start --daemons" not in text
    assert "--daemons" not in text or "NO --daemons" in text or "no --daemons" in text.lower()
    assert "start-taskboard.sh" in text
    assert "mcp-http.sh" in text
    assert "RECOVER_OK" in text
    assert "health_check.sh" in text
    assert "acp_inject.py" not in text
    assert "launch-cloud-extra-high" not in text
    bus = BUS.read_text(encoding="utf-8")
    assert "GCS_BOT_BRIDGE" in bus
    assert "want_bot_bridge" in bus
    # recover must not force the bridge on (Bot seats stay standby).
    # Mentioning the opt-in knob in usage is allowed.
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assert "export GCS_BOT_BRIDGE=1" not in stripped
        assert not stripped.startswith("GCS_BOT_BRIDGE=1")
        assert "GCS_BOT_BRIDGE=${GCS_BOT_BRIDGE:-1}" not in stripped
        assert "start --daemons" not in stripped


def test_wipe_names_health_recover_dr_loop() -> None:
    wipe = WIPE.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    fold = " ".join(wipe.lower().split())
    assert "health_check.sh" in wipe
    assert "recover.sh" in wipe
    assert "dr loop" in fold or "disaster" in fold
    assert "health_check.sh" in readme or "recover.sh" in readme


def test_health_down_when_nothing_listens(tmp_path: Path) -> None:
    state = tmp_path / "a2a-state"
    state.mkdir(parents=True)
    env = _base_env(tmp_path, state)
    env["GCS_A2A_PORT"] = str(_free_port())
    env["GCS_TASKBOARD_UI_PORT"] = str(_free_port())
    env["GCS_TASKBOARD_MCP_PORT"] = str(_free_port())
    proc = _run(HEALTH, [], env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 2, blob
    assert "HEALTH_DOWN" in blob
    assert "HEALTH_OK" not in blob
    assert "test-cursor-api-key-health-not-leaked" not in blob


def test_health_ok_with_live_probes_tailscale_warn(tmp_path: Path) -> None:
    hub, hub_port = _serve()
    ui, ui_port = _serve()
    mcp, mcp_port = _serve()
    sleeper = subprocess.Popen(["sleep", "30"])
    try:
        state = tmp_path / "a2a-state"
        mind = state / "floor" / "mind"
        mind.mkdir(parents=True)
        (mind / "pid").write_text(f"{sleeper.pid}\n", encoding="utf-8")
        env = _base_env(tmp_path, state)
        env["GCS_MIND_SEATS"] = "floor"
        env["GCS_A2A_PORT"] = str(hub_port)
        env["GCS_TASKBOARD_UI_PORT"] = str(ui_port)
        env["GCS_TASKBOARD_MCP_PORT"] = str(mcp_port)
        env["PATH"] = "/usr/bin:/bin"
        proc = _run(HEALTH, [], env)
        blob = proc.stdout + proc.stderr
        assert proc.returncode == 0, blob
        assert "HEALTH_OK" in blob
        assert "HEALTH_DOWN" not in blob
        assert "WARN" in blob
        assert "tailscale" in blob.lower()
        assert "test-cursor-api-key-health-not-leaked" not in blob
    finally:
        sleeper.terminate()
        sleeper.wait(timeout=5)
        hub.shutdown()
        ui.shutdown()
        mcp.shutdown()


def test_health_degraded_when_board_down_hub_up(tmp_path: Path) -> None:
    hub, hub_port = _serve()
    mcp, mcp_port = _serve()
    try:
        state = tmp_path / "a2a-state"
        state.mkdir(parents=True)
        env = _base_env(tmp_path, state)
        env["GCS_A2A_PORT"] = str(hub_port)
        env["GCS_TASKBOARD_UI_PORT"] = str(_free_port())
        env["GCS_TASKBOARD_MCP_PORT"] = str(mcp_port)
        proc = _run(HEALTH, [], env)
        blob = proc.stdout + proc.stderr
        assert proc.returncode == 1, blob
        assert "HEALTH_DEGRADED" in blob
        assert "HEALTH_OK" not in blob
        assert "HEALTH_DOWN" not in blob
    finally:
        hub.shutdown()
        mcp.shutdown()


def test_health_degraded_when_mind_pid_dead(tmp_path: Path) -> None:
    hub, hub_port = _serve()
    ui, ui_port = _serve()
    mcp, mcp_port = _serve()
    dead = subprocess.Popen(["sleep", "0.05"])
    dead.wait(timeout=2)
    try:
        state = tmp_path / "a2a-state"
        mind = state / "floor" / "mind"
        mind.mkdir(parents=True)
        (mind / "pid").write_text(f"{dead.pid}\n", encoding="utf-8")
        env = _base_env(tmp_path, state)
        env["GCS_MIND_SEATS"] = "floor"
        env["GCS_A2A_PORT"] = str(hub_port)
        env["GCS_TASKBOARD_UI_PORT"] = str(ui_port)
        env["GCS_TASKBOARD_MCP_PORT"] = str(mcp_port)
        proc = _run(HEALTH, [], env)
        blob = proc.stdout + proc.stderr
        assert proc.returncode == 1, blob
        assert "HEALTH_DEGRADED" in blob
        assert "floor" in blob
    finally:
        hub.shutdown()
        ui.shutdown()
        mcp.shutdown()


def test_recover_does_not_delete_studio_env(tmp_path: Path) -> None:
    state = tmp_path / "a2a-state"
    state.mkdir(parents=True)
    studio = state / "studio.env"
    marker = "# keep-studio-env-recover\nGCS_MIND_SEATS=\n"
    studio.write_text(marker, encoding="utf-8")
    env = _base_env(tmp_path, state)
    env["GCS_RECOVER_DRY_RUN"] = "1"
    env["GCS_A2A_PORT"] = str(_free_port())
    env["GCS_TASKBOARD_UI_PORT"] = str(_free_port())
    env["GCS_TASKBOARD_MCP_PORT"] = str(_free_port())
    proc = _run(RECOVER, [], env)
    blob = proc.stdout + proc.stderr
    assert "RECOVER_OK" in blob, blob
    assert studio.is_file()
    assert studio.read_text(encoding="utf-8") == marker
    assert "test-cursor-api-key-health-not-leaked" not in blob
    assert PRIVATE_GAME not in blob
    assert "start-studio-bus.sh start --daemons" not in blob


def test_recover_restarts_only_what_is_down(tmp_path: Path) -> None:
    hub, hub_port = _serve()
    try:
        state = tmp_path / "a2a-state"
        state.mkdir(parents=True)
        env = _base_env(tmp_path, state)
        env["GCS_RECOVER_DRY_RUN"] = "1"
        env["GCS_A2A_PORT"] = str(hub_port)
        env["GCS_TASKBOARD_UI_PORT"] = str(_free_port())
        env["GCS_TASKBOARD_MCP_PORT"] = str(_free_port())
        proc = _run(RECOVER, [], env)
        blob = proc.stdout + proc.stderr
        assert "RECOVER_OK" in blob, blob
        assert "start-taskboard.sh" in blob
        assert "mcp-http.sh" in blob
        assert "start-studio-bus.sh" not in blob
    finally:
        hub.shutdown()


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


def _plant_leftover_bus_without_bot_bridge(
    state: Path,
) -> dict[str, subprocess.Popen[bytes]]:
    """Leftover hub/dispatch/shepherd so recover still starts the bus (HTTP hub is down)."""
    state.mkdir(parents=True, exist_ok=True)
    procs: dict[str, subprocess.Popen[bytes]] = {
        "hub": _spawn_sleep(),
        "dispatch": _spawn_sleep(),
        "shepherd": _spawn_sleep(),
    }
    _write_pid(state / "hub.pid", procs["hub"])
    _write_pid(state / "dispatch.pid", procs["dispatch"])
    _write_pid(state / "fleet-shepherd.pid", procs["shepherd"])
    (state / "dispatch.mind-seats").write_text("\n", encoding="utf-8")
    return procs


def _reap_bus_state(
    procs: dict[str, subprocess.Popen[bytes]], state: Path
) -> None:
    for name in ("hub", "dispatch", "fleet-shepherd", "bot-bridge"):
        _reap_pid(_pidfile_pid(state / f"{name}.pid"))
    for extra in ("ui.pid", "mcp-http.pid"):
        _reap_pid(_pidfile_pid(state / "taskboard" / extra))
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


def _recover_live_env(tmp_path: Path, state: Path) -> dict[str, str]:
    env = _base_env(tmp_path, state)
    env["PATH"] = os.environ.get("PATH", "/usr/bin:/bin")
    env["GCS_A2A_PORT"] = str(_free_port())
    env["GCS_TASKBOARD_UI_PORT"] = str(_free_port())
    env["GCS_TASKBOARD_MCP_PORT"] = str(_free_port())
    env.pop("GCS_BOT_BRIDGE", None)
    env.pop("GCS_START_SEAT_DAEMONS", None)
    return env


def test_pal25_feature_binds_recover_default_off() -> None:
    text = PAL25_FEATURE.read_text(encoding="utf-8")
    fold = " ".join(text.lower().split())
    assert PAL25_FEATURE.is_file()
    assert "pal-25" in fold
    assert "gcs_bot_bridge" in fold
    assert "recover.sh" in fold
    assert "bot-bridge" in fold
    assert "demonstrate" in fold and "theatre" in fold
    assert "--daemons" in text
    assert "STUDIO_BUS_BOT_BRIDGE_START" in text
    assert "STUDIO_BUS_BOT_BRIDGE_SKIP" in text


@pytest.mark.parametrize("bridge_value", [None, "", "0"], ids=["unset", "empty", "zero"])
def test_recover_does_not_start_bot_bridge_by_default(
    tmp_path: Path, bridge_value: str | None
) -> None:
    """PAL-25 21:11Z: recover/start without --daemons must not spawn bot-bridge."""
    state = tmp_path / "a2a-state"
    procs = _plant_leftover_bus_without_bot_bridge(state)
    env = _recover_live_env(tmp_path, state)
    if bridge_value is not None:
        env["GCS_BOT_BRIDGE"] = bridge_value
    else:
        assert "GCS_BOT_BRIDGE" not in env
    try:
        proc = _run(RECOVER, [], env, timeout=30)
        blob = proc.stdout + proc.stderr
        assert "RECOVER_OK" in blob, blob
        assert "start --daemons" not in blob, blob
        assert "STUDIO_BUS_BOT_BRIDGE_START" not in blob, blob
        assert "STUDIO_BUS_BOT_BRIDGE_SKIP" in blob, blob
        assert "standby" in blob.lower(), blob
        pid = _pidfile_pid(state / "bot-bridge.pid")
        assert not _pid_alive(pid), f"default recover spawned bot-bridge pid={pid}"
        live = _bot_bridge_pids_for_state(state)
        assert live == [], f"default recover left live bot-bridge pids={live}"
        studio = STUDIO_ENV_EXAMPLE.read_text(encoding="utf-8")
        assert "GCS_BOT_BRIDGE=0" in studio
    finally:
        _reap_bus_state(procs, state)
        for extra in _bot_bridge_pids_for_state(state):
            _reap_pid(extra)


def test_recover_starts_bot_bridge_when_gcs_bot_bridge_is_1(tmp_path: Path) -> None:
    """Opt-in still works. Demonstrate the opposite path, not a source-string theatre."""
    state = tmp_path / "a2a-state"
    procs = _plant_leftover_bus_without_bot_bridge(state)
    env = _recover_live_env(tmp_path, state)
    env["GCS_BOT_BRIDGE"] = "1"
    env["GCS_BOT_BRIDGE_POLL_SEC"] = "60"
    started_pid = 0
    try:
        proc = _run(RECOVER, [], env, timeout=30)
        blob = proc.stdout + proc.stderr
        assert "RECOVER_OK" in blob, blob
        assert "start --daemons" not in blob, blob
        assert "STUDIO_BUS_BOT_BRIDGE_START" in blob, blob
        assert "STUDIO_BUS_BOT_BRIDGE_SKIP" not in blob, blob
        started_pid = _pidfile_pid(state / "bot-bridge.pid")
        assert started_pid > 0
        assert _pid_alive(started_pid)
        live = _bot_bridge_pids_for_state(state)
        assert started_pid in live, f"opt-in recover pidfile={started_pid} live={live}"
    finally:
        if started_pid:
            _reap_pid(started_pid)
        _reap_bus_state(procs, state)
        for extra in _bot_bridge_pids_for_state(state):
            _reap_pid(extra)
