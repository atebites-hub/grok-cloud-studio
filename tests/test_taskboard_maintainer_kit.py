"""Host tcarac/taskboard maintainer kit: start / health / docs.

Distinct from fleet-shepherd health probes (GCS #112) and seat stdio MCP
(GCS #100). GET /health is not a usable board. Never reconnect Agent Kanban.
Never print secrets. Palemon Linear is Living Sky (LIV), not Black Swan.
"""
from __future__ import annotations

import json
import socket
import stat
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parents[1]
FEATURE = REPO / "tests" / "features" / "taskboard_maintainer_kit.feature"
TASKBOARD_DIR = REPO / "scripts" / "studio" / "taskboard"
MAINTAINER = TASKBOARD_DIR / "maintainer.sh"
HEALTH_TB = TASKBOARD_DIR / "health-taskboard.sh"
START_TB = TASKBOARD_DIR / "start-taskboard.sh"
MCP_HTTP = TASKBOARD_DIR / "mcp-http.sh"
TB_README = TASKBOARD_DIR / "README.md"
TASKBOARD_DOC = REPO / "docs" / "studio" / "TASKBOARD.md"
WIPE = REPO / "docs" / "studio" / "WIPE.md"
DOCTOR = REPO / "doctor.sh"
SHEPHERD = REPO / "scripts" / "directors" / "fleet-shepherd.py"
INSTALL_GROK_MCP = REPO / "scripts" / "directors" / "install-grok-mcp.sh"
DASHBOARD_README = REPO / "scripts" / "studio" / "dashboard" / "README.md"
STUDIO_OPS_SOUL = REPO / "docs" / "studio" / "directors" / "souls" / "studio-ops" / "SOUL.md"
STUDIO_OPS_MEMORY = REPO / "docs" / "studio" / "directors" / "souls" / "studio-ops" / "MEMORY.md"
CURSOR_MCP = REPO / ".cursor" / "mcp.json"

PRIVATE_GAME = "atebites-hub/" + "palemon"
LEAK_KEY = "test-cursor-api-key-maintainer-not-leaked"
ULID_SAMPLE = "01ARZ3NDEKTSV4RRFFQ69G5FAV"


def _write_exec(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _base_env(tmp_path: Path, state: Path, *, extra_path: str = "") -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    return {
        "PATH": extra_path or "/usr/bin:/bin",
        "HOME": str(home),
        "GCS_ROOT": str(REPO),
        "GCS_A2A_STATE": str(state),
        "LC_ALL": "C",
        "TERM": "dumb",
        "CURSOR_API_KEY": LEAK_KEY,
    }


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


class _GetOkHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path in ("/", "/health"):
            body = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


class _McpPostHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path in ("/", "/health"):
            body = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path not in ("/", "/mcp"):
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length") or "0")
        if length:
            self.rfile.read(length)
        body = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "result": {"ok": True, "method": "initialize"}}
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


def _serve(handler: type[BaseHTTPRequestHandler]) -> tuple[ThreadingHTTPServer, int]:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, int(httpd.server_address[1])


def _plant_db(state: Path) -> Path:
    db = state / "taskboard" / "taskboard.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_bytes(b"")
    return db


def _fake_ticket_list(tmp_path: Path, *, ok: bool = True) -> tuple[Path, Path]:
    log = tmp_path / "taskboard.argv"
    rc = "0" if ok else "1"
    binary = _write_exec(
        tmp_path / "bin" / "taskboard",
        "#!/bin/sh\n"
        f'echo "$@" >> "{log}"\n'
        'case " $* " in\n'
        f'  *" ticket list "*) exit {rc} ;;\n'
        "esac\n"
        "exit 1\n",
    )
    return binary, log


def test_feature_binds_start_health_docs() -> None:
    assert FEATURE.is_file(), "missing tests/features/taskboard_maintainer_kit.feature"
    text = FEATURE.read_text(encoding="utf-8")
    assert "start / health / docs" in text or "start, health" in text.lower()
    assert "GET /health" in text
    assert "GCS #112" in text or "#112" in text
    assert "GCS #100" in text or "#100" in text
    assert "Agent Kanban" in text
    assert "Living Sky" in text
    assert "Black Swan" in text
    assert "Bot CloudAgent" in text
    assert "Hermes" in text or "hermes" in text.lower()


def test_maintainer_kit_scripts_exist_and_are_executable() -> None:
    for path in (MAINTAINER, HEALTH_TB, START_TB, MCP_HTTP):
        assert path.is_file(), f"missing {path.relative_to(REPO)}"
        assert path.stat().st_mode & stat.S_IXUSR, f"not executable: {path}"


def test_kit_does_not_twin_shepherd_or_seat_mcp() -> None:
    shepherd = SHEPHERD.read_text(encoding="utf-8")
    assert "TASKBOARD_HEALTH" not in shepherd
    assert "_probe_taskboard_health" not in shepherd
    for path in (MAINTAINER, HEALTH_TB):
        text = path.read_text(encoding="utf-8")
        assert "install-grok-mcp" not in text
        assert "mcp-seats" not in text
        assert "GROK_HOME/config.toml" not in text
        assert "ak start" not in text or "gone" in text.lower() or "not" in text.lower()
        assert "mint-floor-ops-worker" not in text
        assert "vendor/hermes" not in text
        assert "Bot CloudAgent" not in text or "Never Bot" in text or "never" in text.lower()
        assert "echo \"$CURSOR_API_KEY\"" not in text
        assert "echo $CURSOR_API_KEY" not in text
        assert "LINEAR_API_KEY=" not in text or "LINEAR_API_KEY=\n" in text
        assert PRIVATE_GAME not in text
    grok_mcp = INSTALL_GROK_MCP.read_text(encoding="utf-8")
    assert "health-taskboard.sh" not in grok_mcp
    assert "maintainer.sh" not in grok_mcp
    cursor = CURSOR_MCP.read_text(encoding="utf-8")
    assert "maintainer.sh" not in cursor
    assert "health-taskboard.sh" not in cursor


def test_help_is_secret_free() -> None:
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": "/tmp",
        "GCS_ROOT": str(REPO),
        "LC_ALL": "C",
        "TERM": "dumb",
        "CURSOR_API_KEY": LEAK_KEY,
    }
    for script in (MAINTAINER, HEALTH_TB):
        proc = _run(script, ["--help"], env)
        blob = proc.stdout + proc.stderr
        assert proc.returncode == 0, blob
        assert "Usage" in blob or script.name in blob
        assert LEAK_KEY not in blob
        assert "CURSOR_API_KEY=" not in blob
        assert "TAILSCALE_AUTH_KEY=" not in blob
        assert "ak start" not in blob or "gone" in blob.lower() or "not" in blob.lower()
        assert PRIVATE_GAME not in blob


def test_health_fails_when_db_missing(tmp_path: Path) -> None:
    state = tmp_path / "a2a-state"
    state.mkdir(parents=True)
    env = _base_env(tmp_path, state)
    env["GCS_TASKBOARD_UI_PORT"] = str(_free_port())
    env["GCS_TASKBOARD_MCP_PORT"] = str(_free_port())
    proc = _run(HEALTH_TB, [], env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 1, blob
    assert "TASKBOARD_HEALTH_FAIL" in blob
    assert "missing-db" in blob
    assert "TASKBOARD_HEALTH_OK" not in blob
    assert LEAK_KEY not in blob


def test_health_fails_when_only_get_health(tmp_path: Path) -> None:
    state = tmp_path / "a2a-state"
    db = _plant_db(state)
    ui, ui_port = _serve(_GetOkHandler)
    mcp, mcp_port = _serve(_GetOkHandler)
    binary, log = _fake_ticket_list(tmp_path, ok=False)
    try:
        env = _base_env(tmp_path, state)
        env["TASKBOARD_BIN"] = str(binary)
        env["GCS_TASKBOARD_UI_PORT"] = str(ui_port)
        env["GCS_TASKBOARD_MCP_PORT"] = str(mcp_port)
        proc = _run(HEALTH_TB, [], env)
        blob = proc.stdout + proc.stderr
        assert proc.returncode == 1, blob
        assert "TASKBOARD_HEALTH_FAIL" in blob
        assert "TASKBOARD_HEALTH_OK" not in blob
        assert str(db) in blob or "db=" in blob
        assert LEAK_KEY not in blob
        if log.is_file():
            argv = log.read_text(encoding="utf-8")
            assert "ticket" in argv and "list" in argv
    finally:
        ui.shutdown()
        mcp.shutdown()


def test_health_ok_when_db_and_ticket_list(tmp_path: Path) -> None:
    state = tmp_path / "a2a-state"
    db = _plant_db(state)
    ui, ui_port = _serve(_GetOkHandler)
    binary, log = _fake_ticket_list(tmp_path, ok=True)
    try:
        env = _base_env(tmp_path, state)
        env["TASKBOARD_BIN"] = str(binary)
        env["GCS_TASKBOARD_UI_PORT"] = str(ui_port)
        env["GCS_TASKBOARD_MCP_PORT"] = str(_free_port())
        proc = _run(HEALTH_TB, [], env)
        blob = proc.stdout + proc.stderr
        assert proc.returncode == 0, blob
        assert "TASKBOARD_HEALTH_OK" in blob
        assert "TASKBOARD_HEALTH_FAIL" not in blob
        argv = log.read_text(encoding="utf-8")
        assert "--db" in argv
        assert str(db) in argv
        assert "ticket" in argv
        assert "list" in argv
        assert LEAK_KEY not in blob
        assert PRIVATE_GAME not in blob
    finally:
        ui.shutdown()


def test_health_ok_when_db_and_post_mcp(tmp_path: Path) -> None:
    state = tmp_path / "a2a-state"
    _plant_db(state)
    ui, ui_port = _serve(_GetOkHandler)
    mcp, mcp_port = _serve(_McpPostHandler)
    try:
        env = _base_env(tmp_path, state)
        env.pop("TASKBOARD_BIN", None)
        env["GCS_TASKBOARD_UI_PORT"] = str(ui_port)
        env["GCS_TASKBOARD_MCP_PORT"] = str(mcp_port)
        proc = _run(HEALTH_TB, [], env)
        blob = proc.stdout + proc.stderr
        assert proc.returncode == 0, blob
        assert "TASKBOARD_HEALTH_OK" in blob
        assert "TASKBOARD_HEALTH_FAIL" not in blob
        assert "mcp=ok" in blob or "POST" in blob or "/mcp" in blob
        assert LEAK_KEY not in blob
    finally:
        ui.shutdown()
        mcp.shutdown()


def test_health_fails_when_ui_down_even_if_ticket_list(tmp_path: Path) -> None:
    state = tmp_path / "a2a-state"
    _plant_db(state)
    binary, _log = _fake_ticket_list(tmp_path, ok=True)
    env = _base_env(tmp_path, state)
    env["TASKBOARD_BIN"] = str(binary)
    env["GCS_TASKBOARD_UI_PORT"] = str(_free_port())
    env["GCS_TASKBOARD_MCP_PORT"] = str(_free_port())
    proc = _run(HEALTH_TB, [], env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 1, blob
    assert "TASKBOARD_HEALTH_FAIL" in blob
    assert "ui-down" in blob or "ui=down" in blob
    assert "TASKBOARD_HEALTH_OK" not in blob


def test_health_and_start_refuse_agent_kanban(tmp_path: Path) -> None:
    kit = tmp_path / "kit"
    ak = kit / "scripts" / "studio" / "agent-kanban"
    ak.mkdir(parents=True)
    (ak / "mint-floor-ops-worker.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    state = tmp_path / "a2a-state"
    _plant_db(state)
    env = _base_env(tmp_path, state)
    env["GCS_ROOT"] = str(kit)
    env["GCS_TASKBOARD_UI_PORT"] = str(_free_port())
    env["GCS_TASKBOARD_MCP_PORT"] = str(_free_port())
    health = _run(HEALTH_TB, [], env)
    hblob = health.stdout + health.stderr
    assert health.returncode == 1, hblob
    assert "AK_REFUSE" in hblob
    assert "TASKBOARD_HEALTH_FAIL" in hblob
    assert "agent-kanban" in hblob
    assert "mint-floor-ops-worker" not in hblob
    start = _run(MAINTAINER, ["start"], env)
    sblob = start.stdout + start.stderr
    assert start.returncode != 0, sblob
    assert "AK_REFUSE" in sblob
    assert "mint-floor-ops-worker" not in sblob
    assert LEAK_KEY not in hblob + sblob


def test_maintainer_start_delegates_to_ui_and_mcp(tmp_path: Path) -> None:
    log = tmp_path / "tb.argv"
    fake = _write_exec(
        tmp_path / "bin" / "taskboard",
        "#!/bin/sh\n"
        f'echo "$@" >> "{log}"\n'
        'for a in "$@"; do\n'
        '  if [ "$a" = "--foreground" ] || [ "$a" = "mcp" ]; then sleep 20; fi\n'
        "done\n",
    )
    state = tmp_path / "a2a-state"
    env = _base_env(tmp_path, state, extra_path=f"{fake.parent}:/usr/bin:/bin")
    env["TASKBOARD_BIN"] = str(fake)
    env["GCS_TASKBOARD_UI_PORT"] = str(_free_port())
    env["GCS_TASKBOARD_MCP_PORT"] = str(_free_port())
    try:
        start = _run(MAINTAINER, ["start"], env, timeout=15)
        blob = start.stdout + start.stderr
        assert start.returncode == 0, blob
        assert "TASKBOARD_UI_START" in blob or "TASKBOARD_UI_ALREADY" in blob
        assert "TASKBOARD_MCP_HTTP_START" in blob or "TASKBOARD_MCP_HTTP_ALREADY" in blob
        argv = log.read_text(encoding="utf-8") if log.is_file() else ""
        db = state / "taskboard" / "taskboard.db"
        assert "--db" in argv
        assert str(db) in argv
        assert "start" in argv
        status = _run(MAINTAINER, ["status"], env)
        sblob = status.stdout + status.stderr
        assert "TASKBOARD_UI_STATUS" in sblob
        assert "TASKBOARD_MCP_HTTP_STATUS" in sblob
        assert LEAK_KEY not in blob
        assert PRIVATE_GAME not in blob
        assert "ak start" not in blob
    finally:
        _run(MAINTAINER, ["stop"], env)


def test_maintainer_docs_points_at_kit_and_living_sky(tmp_path: Path) -> None:
    state = tmp_path / "a2a-state"
    state.mkdir(parents=True)
    env = _base_env(tmp_path, state)
    proc = _run(MAINTAINER, ["docs"], env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    fold = blob.lower()
    assert "TASKBOARD.md" in blob
    assert "WIPE.md" in blob
    assert "start-taskboard.sh" in blob
    assert "health-taskboard.sh" in blob
    assert "Living Sky" in blob or "livingsky" in fold
    assert "LIV" in blob
    assert "Black Swan" in blob
    assert "Agent Kanban" in blob or "agent-kanban" in fold
    assert "#112" in blob or "fleet-shepherd" in blob
    assert "#100" in blob or "stdio MCP" in blob or "GROK_HOME" in blob
    assert "v0.6.0" in blob
    assert LEAK_KEY not in blob
    assert "CURSOR_API_KEY=" not in blob
    assert "TAILSCALE_AUTH_KEY=" not in blob
    assert "ak start" not in blob or "gone" in blob.lower() or "not" in blob.lower()
    assert PRIVATE_GAME not in blob
    assert ULID_SAMPLE not in blob or "ULID" in blob


def test_docs_cover_maintainer_kit_and_stay_secret_free() -> None:
    tb = TASKBOARD_DOC.read_text(encoding="utf-8")
    wipe = WIPE.read_text(encoding="utf-8")
    readme = TB_README.read_text(encoding="utf-8")
    soul = STUDIO_OPS_SOUL.read_text(encoding="utf-8")
    memory = STUDIO_OPS_MEMORY.read_text(encoding="utf-8")
    dash = DASHBOARD_README.read_text(encoding="utf-8")
    doctor = DOCTOR.read_text(encoding="utf-8")
    for label, text in (
        ("TASKBOARD.md", tb),
        ("WIPE.md", wipe),
        ("taskboard README", readme),
    ):
        assert "maintainer.sh" in text, label
        assert "health-taskboard.sh" in text, label
        assert "start-taskboard.sh" in text, label
        assert "GET /health" in text or "GET `/health`" in text, label
        assert "Agent Kanban" in text or "agent-kanban" in text.lower(), label
        assert "ak start" not in text or "not run" in text.lower() or "gone" in text.lower()
        assert PRIVATE_GAME not in text
        assert "Living Sky" in text or "livingsky" in text.lower(), label
        assert "Black Swan" in text, label
        assert "CURSOR_API_KEY=" not in text or "never" in text.lower()
    assert "fleet-shepherd" in tb or "#112" in tb
    assert "GROK_HOME" in tb
    assert "LEGACY" in dash
    assert "health-taskboard.sh" in doctor
    assert "maintainer.sh" in doctor
    assert "maintainer" in soul.lower() or "taskboard" in soul.lower()
    assert "health-taskboard.sh" in memory or "maintainer.sh" in memory
    assert "linear.app/livingsky" in tb or "Livingsky" in tb
    assert "Hermes" not in tb or "never" in tb.lower()
    for path in (MAINTAINER, HEALTH_TB, START_TB, MCP_HTTP, TB_README):
        text = path.read_text(encoding="utf-8")
        assert "scripts/studio/agent-kanban" not in text or "gone" in text.lower() or "gone" in text


def test_health_check_studio_dr_is_not_this_kit() -> None:
    """Studio-wide health_check.sh stays the DR loop; this kit is board-only."""
    health_check = (REPO / "health_check.sh").read_text(encoding="utf-8")
    recover = (REPO / "recover.sh").read_text(encoding="utf-8")
    assert "health-taskboard.sh" not in health_check
    assert "maintainer.sh" not in recover
    assert "start-taskboard.sh" in recover
    assert "mcp-http.sh" in recover
