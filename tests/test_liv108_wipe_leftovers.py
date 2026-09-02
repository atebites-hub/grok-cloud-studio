"""LIV-108: GCS wipe leftovers (Tailscale in setup, recover/systemd, WIPE.md path).

Static + subprocess checks only. Does not start grok serve, Extra High, or
a real Tailscale node. Agent Kanban stays gone. Never asserts secret values.
"""
from __future__ import annotations

import os
import socket
import stat
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SETUP = REPO / "setup.sh"
CLEANUP = REPO / "cleanup.sh"
RECOVER = REPO / "recover.sh"
HEALTH = REPO / "health_check.sh"
INSTALL = REPO / "install.sh"
DOCTOR = REPO / "doctor.sh"
WIPE = REPO / "docs" / "studio" / "WIPE.md"
AGENTS = REPO / "AGENTS.md"
README = REPO / "README.md"
COMMON = REPO / "scripts" / "studio" / "taskboard" / "common.sh"
TS_SERVE = REPO / "scripts" / "studio" / "taskboard" / "start-tailscale-serve.sh"
SYSTEMD_DIR = REPO / "scripts" / "studio" / "systemd"
SYSTEMD_INSTALL = SYSTEMD_DIR / "install-systemd.sh"
SYSTEMD_SERVICE_IN = SYSTEMD_DIR / "gcs-recover.service.in"
SYSTEMD_TIMER_IN = SYSTEMD_DIR / "gcs-recover.timer.in"

PRIVATE_GAME = "atebites-hub/" + "palemon"
CANONICAL_WIPE = "docs/studio/WIPE.md"


def _write_exec(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


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
        "GCS_BOT_BIND_OPTIONAL": "1",
        "LC_ALL": "C",
        "TERM": "dumb",
        "CURSOR_API_KEY": "test-cursor-api-key-liv108-not-leaked",
    }


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


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


def test_setup_starts_optional_tailscale_serve() -> None:
    text = SETUP.read_text(encoding="utf-8")
    assert "start-tailscale-serve.sh" in text
    assert "start-tailscale-serve.sh start --daemons" not in text
    start_idx = text.find("start-tailscale-serve.sh")
    skip_idx = text.find("GCS_SETUP_SKIP_START")
    assert start_idx != -1 and skip_idx != -1
    assert "PALEMON_TAILSCALE_SERVE" in text or "start-tailscale-serve.sh" in text
    assert "agent-kanban" not in text
    assert "TAILSCALE_AUTH_KEY=" not in text


def test_cleanup_stops_tailscale_serve() -> None:
    text = CLEANUP.read_text(encoding="utf-8")
    assert "start-tailscale-serve.sh" in text
    assert "stop" in text
    assert "agent-kanban" not in text
    assert "TAILSCALE_AUTH_KEY=" not in text


def test_canonical_wipe_md_path_not_stale_layouts() -> None:
    assert WIPE.is_file()
    assert not (REPO / "WIPE.md").exists()
    assert not (REPO / "docs" / "WIPE.md").exists()
    wipe = WIPE.read_text(encoding="utf-8")
    assert CANONICAL_WIPE in wipe
    assert "$GCS_ROOT/docs/studio/WIPE.md" in wipe or "`docs/studio/WIPE.md`" in wipe
    for path in (AGENTS, README, DOCTOR, INSTALL, SETUP, CLEANUP, RECOVER, HEALTH):
        text = path.read_text(encoding="utf-8")
        if "WIPE.md" not in text:
            continue
        assert CANONICAL_WIPE in text, f"{path.name} missing canonical {CANONICAL_WIPE}"
        stale = text.replace(CANONICAL_WIPE, "")
        assert "docs/WIPE.md" not in stale, f"{path.name} still has stale docs/WIPE.md"


def test_gcs_wipe_doc_helper_resolves_studio_path(tmp_path: Path) -> None:
    kit = tmp_path / "kit"
    (kit / "docs" / "studio").mkdir(parents=True)
    (kit / "docs" / "studio" / "WIPE.md").write_text("# wipe\n", encoding="utf-8")
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path / "home"),
        "GCS_ROOT": str(kit),
        "LC_ALL": "C",
        "TERM": "dumb",
    }
    script = (
        "set -euo pipefail\n"
        f"source {COMMON}\n"
        "gcs_wipe_doc\n"
    )
    proc = subprocess.run(
        ["bash", "-c", script],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    got = proc.stdout.strip()
    assert got.endswith("docs/studio/WIPE.md")
    assert str(kit / "docs" / "studio" / "WIPE.md") in got
    assert "docs/WIPE.md" not in got.replace("docs/studio/WIPE.md", "")
    assert PRIVATE_GAME not in blob


def test_wipe_doc_covers_setup_tailscale_and_systemd_recover() -> None:
    text = WIPE.read_text(encoding="utf-8")
    fold = " ".join(text.lower().split())
    assert "start-tailscale-serve.sh" in text
    assert "setup.sh" in text
    assert "scripts/studio/systemd" in text
    assert "install-systemd.sh" in text
    assert "gcs-recover.service" in text
    assert "systemctl" in fold or "systemd" in fold
    assert "--daemons" in text
    assert "agent kanban" in fold or "agent-kanban" in fold
    assert PRIVATE_GAME not in text


def test_systemd_templates_exist_and_stay_crash_safe() -> None:
    assert SYSTEMD_DIR.is_dir()
    assert SYSTEMD_INSTALL.is_file()
    assert SYSTEMD_SERVICE_IN.is_file()
    assert SYSTEMD_TIMER_IN.is_file()
    for path in (SYSTEMD_INSTALL, SYSTEMD_SERVICE_IN, SYSTEMD_TIMER_IN):
        text = path.read_text(encoding="utf-8")
        assert "agent-kanban" not in text
        assert "ak start" not in text
        assert "mint-floor-ops-worker" not in text
        assert "TAILSCALE_AUTH_KEY=" not in text
        assert "CURSOR_API_KEY=" not in text
        assert PRIVATE_GAME not in text
        assert "--daemons" not in text or "NO --daemons" in text
    service = SYSTEMD_SERVICE_IN.read_text(encoding="utf-8")
    assert "recover.sh" in service
    assert "Type=oneshot" in service
    assert "@GCS_ROOT@" in service
    assert "@GCS_A2A_STATE@" in service
    assert CANONICAL_WIPE in service or "WIPE.md" in service
    timer = SYSTEMD_TIMER_IN.read_text(encoding="utf-8")
    assert "gcs-recover.service" in timer
    assert "OnBootSec" in timer


def test_install_and_doctor_list_systemd_leftovers() -> None:
    install = INSTALL.read_text(encoding="utf-8")
    doctor = DOCTOR.read_text(encoding="utf-8")
    assert "scripts/studio/systemd/install-systemd.sh" in install
    assert "scripts/studio/systemd" in doctor
    assert "gcs-recover.service.in" in doctor
    assert "install-systemd.sh" in doctor


def test_recover_does_not_start_systemd_ak_units() -> None:
    text = RECOVER.read_text(encoding="utf-8")
    assert "start-tailscale-serve.sh" in text
    assert "agent-kanban" not in text
    assert "systemctl start" not in text
    assert "systemctl enable" not in text
    assert "--daemons" not in text or "NO --daemons" in text
    assert "launch-cloud-extra-high" not in text


def test_install_systemd_dry_run_renders_units(tmp_path: Path) -> None:
    dest = tmp_path / "systemd" / "user"
    state = tmp_path / "a2a-state"
    state.mkdir(parents=True)
    env = _base_env(tmp_path, state)
    env["GCS_SYSTEMD_DEST"] = str(dest)
    env["GCS_SYSTEMD_DRY_RUN"] = "1"
    proc = _run(SYSTEMD_INSTALL, [], env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "SYSTEMD_DRY" in blob or "SYSTEMD_OK" in blob
    service = dest / "gcs-recover.service"
    timer = dest / "gcs-recover.timer"
    assert service.is_file(), blob
    assert timer.is_file(), blob
    rendered = service.read_text(encoding="utf-8")
    assert str(REPO) in rendered
    assert str(state) in rendered
    assert "recover.sh" in rendered
    assert "@GCS_ROOT@" not in rendered
    assert "--daemons" not in rendered
    assert "agent-kanban" not in rendered
    assert "test-cursor-api-key-liv108-not-leaked" not in blob
    assert PRIVATE_GAME not in blob
    assert PRIVATE_GAME not in rendered


def test_install_systemd_skip_flag(tmp_path: Path) -> None:
    dest = tmp_path / "systemd" / "user"
    state = tmp_path / "a2a-state"
    state.mkdir(parents=True)
    env = _base_env(tmp_path, state)
    env["GCS_SYSTEMD_DEST"] = str(dest)
    env["GCS_SYSTEMD"] = "0"
    proc = _run(SYSTEMD_INSTALL, [], env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "SKIP" in blob
    assert not (dest / "gcs-recover.service").exists()


def test_recover_starts_tailscale_when_binary_present(tmp_path: Path) -> None:
    log = tmp_path / "ts.argv"
    fake = _write_exec(
        tmp_path / "bin" / "tailscale",
        "#!/bin/sh\n"
        f'printf "%s\\n" "$@" >> "{log}"\n'
        "exit 0\n",
    )
    hub, hub_port = _serve()
    try:
        state = tmp_path / "a2a-state"
        state.mkdir(parents=True)
        env = _base_env(tmp_path, state)
        env["PATH"] = f"{fake.parent}:/usr/bin:/bin"
        env["GCS_RECOVER_DRY_RUN"] = "1"
        env["GCS_A2A_PORT"] = str(hub_port)
        env["GCS_TASKBOARD_UI_PORT"] = str(_free_port())
        env["GCS_TASKBOARD_MCP_PORT"] = str(_free_port())
        proc = _run(RECOVER, [], env)
        blob = proc.stdout + proc.stderr
        assert "RECOVER_OK" in blob, blob
        assert "start-tailscale-serve.sh" in blob
        assert "start-studio-bus.sh start --daemons" not in blob
        assert "test-cursor-api-key-liv108-not-leaked" not in blob
        assert "TAILSCALE_AUTH_KEY=" not in blob
    finally:
        hub.shutdown()


def test_recover_skips_tailscale_when_serve_off(tmp_path: Path) -> None:
    fake = _write_exec(
        tmp_path / "bin" / "tailscale",
        "#!/bin/sh\nexit 0\n",
    )
    hub, hub_port = _serve()
    try:
        state = tmp_path / "a2a-state"
        state.mkdir(parents=True)
        env = _base_env(tmp_path, state)
        env["PATH"] = f"{fake.parent}:/usr/bin:/bin"
        env["GCS_RECOVER_DRY_RUN"] = "1"
        env["PALEMON_TAILSCALE_SERVE"] = "0"
        env["GCS_A2A_PORT"] = str(hub_port)
        env["GCS_TASKBOARD_UI_PORT"] = str(_free_port())
        env["GCS_TASKBOARD_MCP_PORT"] = str(_free_port())
        proc = _run(RECOVER, [], env)
        blob = proc.stdout + proc.stderr
        assert "RECOVER_OK" in blob, blob
        assert "start-tailscale-serve.sh" not in blob
    finally:
        hub.shutdown()


def test_setup_invokes_tailscale_script_when_start_not_skipped(
    tmp_path: Path,
) -> None:
    """setup.sh must call start-tailscale-serve.sh after board/bus when starting."""
    text = SETUP.read_text(encoding="utf-8")
    bus_idx = text.find("start-studio-bus.sh")
    ts_idx = text.find("start-tailscale-serve.sh")
    assert bus_idx != -1 and ts_idx != -1
    assert ts_idx > bus_idx
    assert "GCS_SETUP_SKIP_START" in text
    env = _base_env(tmp_path, tmp_path / "a2a-state")
    env["GCS_SETUP_SKIP_INSTALL"] = "1"
    env["GCS_SETUP_SKIP_SUBMODULE"] = "1"
    env["GCS_SETUP_SKIP_START"] = "1"
    env["GCS_SETUP_SKIP_DOCTOR"] = "1"
    env["GCS_SETUP_SKIP_HEALTH"] = "1"
    proc = _run(SETUP, [], env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "SETUP_OK" in blob
    assert "start-tailscale-serve.sh" not in blob
    key = os.environ.get("CURSOR_API_KEY", "")
    if key:
        assert key not in blob
    assert "test-cursor-api-key-liv108-not-leaked" not in blob
