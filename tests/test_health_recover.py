"""Live-service health_check.sh + recover.sh DR loop. No secrets, no Agent Kanban."""
from __future__ import annotations

import os
import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HEALTH = REPO / "health_check.sh"
RECOVER = REPO / "recover.sh"
SETUP = REPO / "setup.sh"
INSTALL = REPO / "install.sh"
DOCTOR = REPO / "doctor.sh"
WIPE = REPO / "docs" / "studio" / "WIPE.md"
README = REPO / "README.md"

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
        apply = subprocess.run(
            [
                "python3",
                str(REPO / "scripts" / "studio" / "apply_log.py"),
                "append",
                "--model",
                "BDD in Action",
                "--change",
                "IaC: health_check.sh live probes; Palemon: no game code",
            ],
            cwd=str(REPO),
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert apply.returncode == 0, apply.stdout + apply.stderr
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
