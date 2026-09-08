"""PAL-25 class remaining (beat1610): hub /health stay-up, leftover dispatch lives.

#145 / beat1849 covers leftover bot-bridge.pid eviction. This file is the
hub-already-up gap: recover.sh must not call start-studio-bus.sh when hub
GET /health is already 200 (live layout GCS_A2A_STATE=/workspace/palemon/.a2a-state).
studio.env GCS_MIND_SEATS would otherwise recycle leftover dispatch
(STUDIO_BUS_DISPATCH_RECYCLE). Bot-bridge stays off (spare). Isolated tmp
state only — never the live Palemon path.

Never Bot CloudAgent. Never print credentials. Agent Kanban stays gone.
Do not steal PAL-8/11/12/16. Do not remint leftover #165/#167/#168.
"""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
RECOVER = REPO / "recover.sh"
FEATURE = REPO / "tests" / "features" / "pal25_hub_health_nobridge.feature"
LIVE_PALEMON_STATE = Path("/workspace/palemon/.a2a-state")
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


def _http_ok(url: str) -> bool:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            status = int(getattr(resp, "status", 200) or 200)
        return 200 <= status < 300
    except (OSError, urllib.error.URLError, ValueError):
        return False


def _base_env(tmp_path: Path, state: Path) -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "GCS_ROOT": str(REPO),
        "GCS_A2A_STATE": str(state),
        "GCS_MIND_SEATS": "",
        "GCS_BOT_BIND_OPTIONAL": "1",
        "GCS_START_SEAT_DAEMONS": "0",
        "PALEMON_AK_BRIDGE": "0",
        "PALEMON_TAILSCALE_SERVE": "0",
        "LC_ALL": "C",
        "TERM": "dumb",
        "CURSOR_API_KEY": SECRET,
    }
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


def _plant_leftover_bus(
    state: Path, *, bot_bridge: bool
) -> dict[str, subprocess.Popen[bytes]]:
    """Leftover hub/dispatch/shepherd; optional live bot-bridge.pid stand-in."""
    state.mkdir(parents=True, exist_ok=True)
    procs: dict[str, subprocess.Popen[bytes]] = {
        "hub": _spawn_sleep(),
        "dispatch": _spawn_sleep(),
        "shepherd": _spawn_sleep(),
    }
    _write_pid(state / "hub.pid", procs["hub"])
    _write_pid(state / "dispatch.pid", procs["dispatch"])
    _write_pid(state / "fleet-shepherd.pid", procs["shepherd"])
    # Empty persist is the recycle trap vs palemon studio.env GCS_MIND_SEATS.
    (state / "dispatch.mind-seats").write_text("\n", encoding="utf-8")
    if bot_bridge:
        procs["bot-bridge"] = _spawn_sleep()
        _write_pid(state / "bot-bridge.pid", procs["bot-bridge"])
    (state / "studio.env").write_text(
        "GCS_MIND_SEATS=floor,studio-ops\n"
        "GCS_BOT_BRIDGE=0\n"
        "GCS_START_SEAT_DAEMONS=0\n"
        "PALEMON_AK_BRIDGE=0\n"
        "PALEMON_TAILSCALE_SERVE=0\n",
        encoding="utf-8",
    )
    return procs


def _reap_bus_state(
    procs: dict[str, subprocess.Popen[bytes]], state: Path
) -> None:
    for name in ("hub", "dispatch", "fleet-shepherd", "bot-bridge", "webhook"):
        _reap_pid(_pidfile_pid(state / f"{name}.pid"))
    for seat in ("floor", "studio-ops"):
        _reap_pid(_pidfile_pid(state / seat / "mind" / "pid"))
        _reap_pid(_pidfile_pid(state / seat / "wake.pid"))
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


def _assert_isolated_from_live_palemon(state: Path) -> None:
    resolved = state.resolve()
    assert resolved != LIVE_PALEMON_STATE.resolve()
    assert LIVE_PALEMON_STATE.as_posix() not in str(resolved)
    assert str(resolved) != "/workspace/palemon/.a2a-state"


def test_feature_binds_hub_health_nobridge_beat1610() -> None:
    text = FEATURE.read_text(encoding="utf-8")
    fold = " ".join(text.lower().split())
    assert FEATURE.is_file()
    assert "pal-25" in fold
    assert "beat1610" in fold or "gcs-hub-health-nobridge" in fold
    assert "hub" in fold and "/health" in fold
    assert "leftover dispatch" in fold
    assert "bot-bridge stays off" in fold
    assert "recover.sh" in fold
    assert "start-studio-bus.sh" in fold
    assert "/workspace/palemon/.a2a-state" in text
    assert "pal-8" in fold
    recover = RECOVER.read_text(encoding="utf-8")
    assert "start-studio-bus.sh start --daemons" not in recover
    assert "when hub /health is already up" in recover.lower()
    for line in recover.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assert "export GCS_BOT_BRIDGE=1" not in stripped
        assert not stripped.startswith("GCS_BOT_BRIDGE=1")
        assert "GCS_BOT_BRIDGE=${GCS_BOT_BRIDGE:-1}" not in stripped


@pytest.mark.parametrize("bridge_value", [None, "", "0"], ids=["unset", "empty", "zero"])
def test_recover_hub_up_keeps_leftover_dispatch_and_skips_bot_bridge(
    tmp_path: Path, bridge_value: str | None
) -> None:
    """Live Palemon recover: hub+taskboard stay up; leftover dispatch lives."""
    state = tmp_path / "palemon" / ".a2a-state"
    _assert_isolated_from_live_palemon(state)
    hub, hub_port = _serve()
    board, board_port = _serve()
    mcp, mcp_port = _serve()
    procs = _plant_leftover_bus(state, bot_bridge=True)
    leftover_disp = int(procs["dispatch"].pid)
    leftover_hub = int(procs["hub"].pid)
    leftover_bridge = int(procs["bot-bridge"].pid)
    env = _base_env(tmp_path, state)
    env["GCS_A2A_PORT"] = str(hub_port)
    env["GCS_TASKBOARD_UI_PORT"] = str(board_port)
    env["GCS_TASKBOARD_MCP_PORT"] = str(mcp_port)
    if bridge_value is not None:
        env["GCS_BOT_BRIDGE"] = bridge_value
    else:
        env.pop("GCS_BOT_BRIDGE", None)
        assert "GCS_BOT_BRIDGE" not in env
    try:
        assert _http_ok(f"http://127.0.0.1:{hub_port}/health")
        assert _http_ok(f"http://127.0.0.1:{board_port}/")
        proc = _run(RECOVER, [], env, timeout=30)
        blob = proc.stdout + proc.stderr
        assert "RECOVER_OK" in blob, blob
        _assert_secret_free(blob)
        assert "start-studio-bus.sh" not in blob, blob
        assert "STUDIO_BUS_DISPATCH_RECYCLE" not in blob, blob
        assert "STUDIO_BUS_DISPATCH_START" not in blob, blob
        assert "STUDIO_BUS_BOT_BRIDGE_START" not in blob, blob
        assert "STUDIO_BUS_BOT_BRIDGE_ALREADY" not in blob, blob
        assert "start-taskboard.sh" not in blob, blob
        assert procs["dispatch"].poll() is None, blob
        assert _pid_alive(leftover_disp), f"leftover dispatch pid={leftover_disp} dead"
        assert _pidfile_pid(state / "dispatch.pid") == leftover_disp
        assert procs["hub"].poll() is None, blob
        assert _pid_alive(leftover_hub)
        assert _http_ok(f"http://127.0.0.1:{hub_port}/health")
        assert _http_ok(f"http://127.0.0.1:{board_port}/")
        # poll() reaps the SIGTERM zombie before kill(pid,0) can look live.
        assert procs["bot-bridge"].poll() is not None, blob
        assert not _pid_alive(leftover_bridge), f"leftover bot-bridge pid={leftover_bridge} still alive"
        live_py = _bot_bridge_py_pids_for_state(state)
        assert live_py == [], f"default recover left live bot-bridge.py pids={live_py}"
        assert not _pid_alive(_pidfile_pid(state / "bot-bridge.pid"))
        assert "RECOVER_BOT_BRIDGE_EVICT" in blob, blob
    finally:
        hub.shutdown()
        board.shutdown()
        mcp.shutdown()
        _reap_bus_state(procs, state)
        for extra in _bot_bridge_py_pids_for_state(state):
            _reap_pid(extra)


def test_recover_hub_up_does_not_launch_bot_bridge_without_pidfile(
    tmp_path: Path,
) -> None:
    """Default-off spawn skip when hub is already up (no leftover pidfile)."""
    state = tmp_path / "palemon" / ".a2a-state"
    _assert_isolated_from_live_palemon(state)
    hub, hub_port = _serve()
    board, board_port = _serve()
    mcp, mcp_port = _serve()
    procs = _plant_leftover_bus(state, bot_bridge=False)
    leftover_disp = int(procs["dispatch"].pid)
    env = _base_env(tmp_path, state)
    env["GCS_A2A_PORT"] = str(hub_port)
    env["GCS_TASKBOARD_UI_PORT"] = str(board_port)
    env["GCS_TASKBOARD_MCP_PORT"] = str(mcp_port)
    env.pop("GCS_BOT_BRIDGE", None)
    try:
        proc = _run(RECOVER, [], env, timeout=30)
        blob = proc.stdout + proc.stderr
        assert "RECOVER_OK" in blob, blob
        _assert_secret_free(blob)
        assert "STUDIO_BUS_BOT_BRIDGE_START" not in blob, blob
        assert "start-studio-bus.sh" not in blob, blob
        assert procs["dispatch"].poll() is None, blob
        assert _pid_alive(leftover_disp)
        assert not (state / "bot-bridge.pid").is_file() or not _pid_alive(
            _pidfile_pid(state / "bot-bridge.pid")
        )
        live_py = _bot_bridge_py_pids_for_state(state)
        assert live_py == [], f"default recover spawned bot-bridge pids={live_py}"
        assert _http_ok(f"http://127.0.0.1:{hub_port}/health")
        assert _http_ok(f"http://127.0.0.1:{board_port}/")
    finally:
        hub.shutdown()
        board.shutdown()
        mcp.shutdown()
        _reap_bus_state(procs, state)
        for extra in _bot_bridge_py_pids_for_state(state):
            _reap_pid(extra)


def test_recover_does_not_target_live_palemon_a2a_state_path(tmp_path: Path) -> None:
    """Ship-gate tests must not point recover at the live Palemon state dir."""
    state = tmp_path / "palemon" / ".a2a-state"
    state.mkdir(parents=True, exist_ok=True)
    env = _base_env(tmp_path, state)
    _assert_isolated_from_live_palemon(Path(env["GCS_A2A_STATE"]))
    recover = RECOVER.read_text(encoding="utf-8")
    for line in recover.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assert "/workspace/palemon/.a2a-state" not in stripped
    if LIVE_PALEMON_STATE.is_dir():
        before = sorted(p.name for p in LIVE_PALEMON_STATE.iterdir())
        hub, hub_port = _serve()
        env["GCS_A2A_PORT"] = str(hub_port)
        env["GCS_TASKBOARD_UI_PORT"] = str(_free_port())
        env["GCS_TASKBOARD_MCP_PORT"] = str(_free_port())
        try:
            _run(RECOVER, [], env, timeout=20)
        finally:
            hub.shutdown()
        after = sorted(p.name for p in LIVE_PALEMON_STATE.iterdir())
        assert after == before
