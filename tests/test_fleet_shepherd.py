"""fleet-shepherd leftover-shell skip, closed-leftover prune, and taskboard health.

Skip ACTIVE+FINISHED leftover shells so shepherd does not get_agent_run them.
Prune notified closed FINISHED/CANCELLED rows so they are not paged as live.
Each cycle also probes taskboard (DB file plus ticket list or HTTP /mcp) and
logs TASKBOARD_HEALTH_OK or TASKBOARD_HEALTH_FAIL. Does not clone occupancy
GCS #125/#132/#154, gcs-fleet-dedupe-notify-floor1747, seat stdio MCP,
Agent Kanban, bot-bridge, or New Bot.
"""
from __future__ import annotations

import importlib.util
import json
import socket
import stat
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parents[1]
SHEPHERD = REPO / "scripts" / "directors" / "fleet-shepherd.py"
BOT_BRIDGE = REPO / "scripts" / "a2a" / "bot-bridge.py"
ARCH = REPO / "docs" / "ARCHITECTURE.md"
TASKBOARD_DOC = REPO / "docs" / "studio" / "TASKBOARD.md"
CLOUD_README = REPO / "scripts" / "cloud" / "README.md"
PRUNE_FEATURE = REPO / "tests" / "features" / "fleet_ledger_prune_closed.feature"


def _load(name: str | None = None) -> ModuleType:
    unique = name or f"gcs_fleet_shepherd_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(unique, SHEPHERD)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[unique] = mod
    spec.loader.exec_module(mod)
    return mod


def _write_exec(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def _bind(mod: ModuleType, state: Path) -> None:
    state.mkdir(parents=True, exist_ok=True)
    mod.ROOT = REPO
    mod.STATE_DIR = state
    mod.LOG = state / "fleet-shepherd.log"
    mod.PID_FILE = state / "fleet-shepherd.pid"


def _plant(seat_dir: Path, rows: list[dict[str, Any]]) -> None:
    seat_dir.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    (seat_dir / "fleet.jsonl").write_text(text, encoding="utf-8")


def _load_jsonl(seat_dir: Path) -> list[dict[str, Any]]:
    path = seat_dir / "fleet.jsonl"
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        rec = json.loads(raw)
        if isinstance(rec, dict):
            out.append(rec)
    return out


def _base_env(monkeypatch, tmp_path: Path) -> Path:
    state = tmp_path / "a2a-state"
    state.mkdir(parents=True, exist_ok=True)
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("GCS_ROOT", str(REPO))
    monkeypatch.setenv("GCS_A2A_STATE", str(state))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setenv("CURSOR_API_KEY", "test-cursor-api-key-shepherd-health-not-leaked")
    monkeypatch.delenv("GCS_TASKBOARD_DB", raising=False)
    monkeypatch.delenv("TASKBOARD_DB", raising=False)
    monkeypatch.delenv("TASKBOARD_BIN", raising=False)
    monkeypatch.delenv("GCS_TASKBOARD_MCP_URL", raising=False)
    port = _free_port()
    monkeypatch.setenv("GCS_TASKBOARD_MCP_HOST", "127.0.0.1")
    monkeypatch.setenv("GCS_TASKBOARD_MCP_PORT", str(port))
    return state


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _fake_taskboard(tmp_path: Path, *, rc: int = 0) -> tuple[Path, Path]:
    log = tmp_path / "taskboard.argv"
    binary = _write_exec(
        tmp_path / "host-bin" / "taskboard",
        "#!/bin/sh\n"
        f'printf "%s\\n" "$*" >> "{log}"\n'
        f"exit {rc}\n",
    )
    return binary, log


class _McpHandler(BaseHTTPRequestHandler):
    mcp_ok = True
    health_ok = True
    posts: list[str]

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path == "/health" and type(self).health_ok:
            self._json(200, {"ok": True, "service": "gcs-taskboard-mcp-http"})
            return
        self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path.rstrip("/") or "/"
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        type(self).posts.append(raw.decode("utf-8", errors="replace"))
        if path == "/mcp" and type(self).mcp_ok:
            self._json(200, {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})
            return
        self._json(404, {"ok": False, "error": "not found"})

    def _json(self, status: int, payload: dict) -> None:
        blob = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)


def _serve_mcp(*, mcp_ok: bool = True, health_ok: bool = True) -> tuple[ThreadingHTTPServer, int, type]:
    posts: list[str] = []

    class Handler(_McpHandler):
        pass

    Handler.mcp_ok = mcp_ok
    Handler.health_ok = health_ok
    Handler.posts = posts
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, int(httpd.server_address[1]), Handler


def _log_text(mod: ModuleType) -> str:
    if not mod.LOG.is_file():
        return ""
    return mod.LOG.read_text(encoding="utf-8")


def test_missing_db_logs_taskboard_health_fail(tmp_path: Path, monkeypatch) -> None:
    state = _base_env(monkeypatch, tmp_path)
    binary, _argv = _fake_taskboard(tmp_path, rc=0)
    monkeypatch.setenv("TASKBOARD_BIN", str(binary))
    mod = _load()
    _bind(mod, state)
    n = mod._cycle()
    blob = _log_text(mod)
    assert n == 0
    assert "TASKBOARD_HEALTH_FAIL" in blob
    assert "TASKBOARD_HEALTH_OK" not in blob
    assert "test-cursor-api-key-shepherd-health-not-leaked" not in blob


def test_db_and_ticket_list_logs_ok(tmp_path: Path, monkeypatch) -> None:
    state = _base_env(monkeypatch, tmp_path)
    db = state / "taskboard" / "taskboard.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_bytes(b"")
    binary, argv = _fake_taskboard(tmp_path, rc=0)
    monkeypatch.setenv("TASKBOARD_BIN", str(binary))
    mod = _load()
    _bind(mod, state)
    n = mod._cycle()
    blob = _log_text(mod)
    recorded = argv.read_text(encoding="utf-8") if argv.is_file() else ""
    assert n == 0
    assert "TASKBOARD_HEALTH_OK" in blob
    assert "TASKBOARD_HEALTH_FAIL" not in blob
    assert f"--db {db} ticket list" in recorded
    assert "test-cursor-api-key-shepherd-health-not-leaked" not in blob


def test_db_and_http_mcp_logs_ok_when_ticket_fails(tmp_path: Path, monkeypatch) -> None:
    state = _base_env(monkeypatch, tmp_path)
    db = state / "taskboard" / "taskboard.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_bytes(b"")
    binary, _argv = _fake_taskboard(tmp_path, rc=1)
    monkeypatch.setenv("TASKBOARD_BIN", str(binary))
    httpd, port, handler = _serve_mcp(mcp_ok=True)
    monkeypatch.setenv("GCS_TASKBOARD_MCP_PORT", str(port))
    try:
        mod = _load()
        _bind(mod, state)
        n = mod._cycle()
        blob = _log_text(mod)
        assert n == 0
        assert "TASKBOARD_HEALTH_OK" in blob
        assert "TASKBOARD_HEALTH_FAIL" not in blob
        assert any("initialize" in p for p in handler.posts)
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_mcp_health_endpoint_is_not_enough(tmp_path: Path, monkeypatch) -> None:
    """GET /health is health_check.sh. Shepherd needs ticket list or HTTP /mcp."""
    state = _base_env(monkeypatch, tmp_path)
    db = state / "taskboard" / "taskboard.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_bytes(b"")
    binary, _argv = _fake_taskboard(tmp_path, rc=1)
    monkeypatch.setenv("TASKBOARD_BIN", str(binary))
    httpd, port, _handler = _serve_mcp(mcp_ok=False, health_ok=True)
    monkeypatch.setenv("GCS_TASKBOARD_MCP_PORT", str(port))
    try:
        mod = _load()
        _bind(mod, state)
        mod._cycle()
        blob = _log_text(mod)
        assert "TASKBOARD_HEALTH_FAIL" in blob
        assert "TASKBOARD_HEALTH_OK" not in blob
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_db_without_ticket_or_mcp_logs_fail(tmp_path: Path, monkeypatch) -> None:
    state = _base_env(monkeypatch, tmp_path)
    db = state / "taskboard" / "taskboard.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_bytes(b"")
    binary, _argv = _fake_taskboard(tmp_path, rc=1)
    monkeypatch.setenv("TASKBOARD_BIN", str(binary))
    mod = _load()
    _bind(mod, state)
    mod._cycle()
    blob = _log_text(mod)
    assert "TASKBOARD_HEALTH_FAIL" in blob
    assert "TASKBOARD_HEALTH_OK" not in blob


def test_custom_db_env_and_once_exit_zero(tmp_path: Path, monkeypatch) -> None:
    state = _base_env(monkeypatch, tmp_path)
    db = tmp_path / "custom.db"
    db.write_bytes(b"")
    monkeypatch.setenv("GCS_TASKBOARD_DB", str(db))
    binary, argv = _fake_taskboard(tmp_path, rc=0)
    monkeypatch.setenv("TASKBOARD_BIN", str(binary))
    mod = _load()
    _bind(mod, state)
    monkeypatch.setattr(sys, "argv", ["fleet-shepherd.py", "--once"])
    rc = mod.main()
    blob = _log_text(mod)
    recorded = argv.read_text(encoding="utf-8") if argv.is_file() else ""
    assert rc == 0
    assert "TASKBOARD_HEALTH_OK" in blob
    assert f"--db {db} ticket list" in recorded
    assert "SHEPHERD_ONCE" in blob


def test_health_probe_does_not_skip_orphan_cycle(tmp_path: Path, monkeypatch) -> None:
    state = _base_env(monkeypatch, tmp_path)
    db = state / "taskboard" / "taskboard.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_bytes(b"")
    binary, _argv = _fake_taskboard(tmp_path, rc=0)
    monkeypatch.setenv("TASKBOARD_BIN", str(binary))
    seat = state / "ops"
    seat.mkdir(parents=True, exist_ok=True)
    (seat / "fleet.jsonl").write_text(
        json.dumps(
            {
                "bc_id": "bc-orphan-health",
                "seat": "ops",
                "status": "open",
                "notified": False,
                "waiter_pid": None,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    mod = _load()
    _bind(mod, state)
    monkeypatch.setattr(mod, "_probe", lambda bc_id: None)
    n = mod._cycle()
    blob = _log_text(mod)
    assert n == 0
    assert "TASKBOARD_HEALTH_OK" in blob
    assert "SHEPHERD_ORPHAN_EMPTY" in blob
    assert "bc-orphan-health" in blob


def test_probe_exception_does_not_abort_orphan_cycle(tmp_path: Path, monkeypatch) -> None:
    """HTTP glitches must log TASKBOARD_HEALTH_FAIL and still walk orphans."""
    state = _base_env(monkeypatch, tmp_path)
    db = state / "taskboard" / "taskboard.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_bytes(b"")
    binary, _argv = _fake_taskboard(tmp_path, rc=1)
    monkeypatch.setenv("TASKBOARD_BIN", str(binary))
    seat = state / "ops"
    seat.mkdir(parents=True, exist_ok=True)
    (seat / "fleet.jsonl").write_text(
        json.dumps(
            {
                "bc_id": "bc-orphan-probe-exc",
                "seat": "ops",
                "status": "open",
                "notified": False,
                "waiter_pid": None,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    mod = _load()
    _bind(mod, state)

    def _boom() -> bool:
        raise ConnectionResetError("mcp reset")

    monkeypatch.setattr(mod, "_mcp_http_ok", _boom)
    monkeypatch.setattr(mod, "_probe", lambda bc_id: None)
    n = mod._cycle()
    blob = _log_text(mod)
    assert n == 0
    assert "TASKBOARD_HEALTH_FAIL" in blob
    assert "TASKBOARD_HEALTH_OK" not in blob
    assert "SHEPHERD_ORPHAN_EMPTY" in blob
    assert "bc-orphan-probe-exc" in blob
    assert "test-cursor-api-key-shepherd-health-not-leaked" not in blob


def test_once_missing_db_still_exits_zero(tmp_path: Path, monkeypatch) -> None:
    state = _base_env(monkeypatch, tmp_path)
    binary, _argv = _fake_taskboard(tmp_path, rc=0)
    monkeypatch.setenv("TASKBOARD_BIN", str(binary))
    mod = _load()
    _bind(mod, state)
    monkeypatch.setattr(sys, "argv", ["fleet-shepherd.py", "--once"])
    rc = mod.main()
    blob = _log_text(mod)
    assert rc == 0
    assert "TASKBOARD_HEALTH_FAIL" in blob
    assert "SHEPHERD_ONCE" in blob


def test_shepherd_does_not_probe_notified_closed_leftover(tmp_path: Path) -> None:
    """Closed+notified shells must not hit get_agent_run."""
    mod = _load()
    _bind(mod, tmp_path)
    _plant(
        tmp_path / "ops",
        [
            {
                "bc_id": "bc-closed",
                "seat": "ops",
                "status": "closed",
                "notified": True,
                "notified_by": "waiter",
                "run_status": "FINISHED",
                "waiter_pid": None,
            }
        ],
    )
    probes: list[str] = []
    notifies: list[str] = []
    mod._probe = lambda bc_id: probes.append(bc_id) or {  # type: ignore[assignment]
        "runStatus": "FINISHED",
        "agentStatus": "ACTIVE",
        "status": "FINISHED",
    }
    mod.notify_owner = lambda bc_id, payload, **kwargs: notifies.append(bc_id)  # type: ignore[assignment]

    assert mod._cycle() == 0
    assert probes == []
    assert notifies == []


def test_shepherd_does_not_probe_finished_open_leftover(tmp_path: Path) -> None:
    """Open orphan whose latest run is already FINISHED is leftover — no run GET."""
    mod = _load()
    _bind(mod, tmp_path)
    _plant(
        tmp_path / "ops",
        [
            {
                "bc_id": "bc-leftover",
                "seat": "ops",
                "status": "open",
                "notified": False,
                "run_status": "FINISHED",
                "agent_status": "ACTIVE",
                "waiter_pid": None,
            }
        ],
    )
    probes: list[str] = []
    notifies: list[str] = []
    mod._probe = lambda bc_id: probes.append(bc_id) or {  # type: ignore[assignment]
        "runStatus": "FINISHED",
        "agentStatus": "ACTIVE",
        "status": "FINISHED",
    }
    mod.notify_owner = lambda bc_id, payload, **kwargs: notifies.append(bc_id)  # type: ignore[assignment]

    assert mod._cycle() == 0
    assert probes == []
    assert notifies == []
    log = _log_text(mod)
    assert "SHEPHERD_SKIP leftover" in log
    assert "bc-leftover" in log


def test_shepherd_probes_live_orphan_without_finished_run(tmp_path: Path) -> None:
    """True orphans (no terminal run on the ledger) still get one result probe."""
    mod = _load()
    _bind(mod, tmp_path)
    _plant(
        tmp_path / "ops",
        [
            {
                "bc_id": "bc-live",
                "seat": "ops",
                "status": "open",
                "notified": False,
                "waiter_pid": None,
            }
        ],
    )
    probes: list[str] = []

    def _probe(bc_id: str) -> dict[str, Any]:
        probes.append(bc_id)
        return {
            "runStatus": "RUNNING",
            "agentStatus": "ACTIVE",
            "status": "RUNNING",
        }

    notified: list[str] = []
    mod._probe = _probe  # type: ignore[assignment]
    mod.notify_owner = lambda bc_id, payload, **kwargs: notified.append(bc_id)  # type: ignore[assignment]

    assert mod._cycle() == 0
    assert probes == ["bc-live"]
    assert notified == []


def test_shepherd_second_cycle_does_not_reprobe_finished(tmp_path: Path) -> None:
    """After a FINISHED probe, later cycles must not hammer get_agent_run."""
    mod = _load()
    _bind(mod, tmp_path)
    _plant(
        tmp_path / "ops",
        [
            {
                "bc_id": "bc-once",
                "seat": "ops",
                "status": "open",
                "notified": False,
                "waiter_pid": None,
            }
        ],
    )
    probes: list[str] = []

    def _probe(bc_id: str) -> dict[str, Any]:
        probes.append(bc_id)
        return {
            "runStatus": "FINISHED",
            "agentStatus": "ACTIVE",
            "status": "FINISHED",
            "prUrl": "https://example.test/pr/1",
            "name": "once",
            "url": "https://cursor.com/agents/bc-once",
        }

    def _notify_fail(bc_id: str, payload: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("A2A ping failed")

    mod._probe = _probe  # type: ignore[assignment]
    mod.notify_owner = _notify_fail  # type: ignore[assignment]

    assert mod._cycle() == 0
    assert probes == ["bc-once"]

    probes.clear()
    assert mod._cycle() == 0
    assert probes == [], "leftover FINISHED must not get_agent_run again"


def test_shepherd_skips_leftovers_while_probing_live_orphan(tmp_path: Path) -> None:
    """Same cycle: leftover FINISHED shells are skipped; a RUNNING orphan is probed."""
    mod = _load()
    _bind(mod, tmp_path)
    _plant(
        tmp_path / "ops",
        [
            {
                "bc_id": "bc-closed",
                "seat": "ops",
                "status": "closed",
                "notified": True,
                "notified_by": "waiter",
                "run_status": "FINISHED",
            },
            {
                "bc_id": "bc-leftover",
                "seat": "ops",
                "status": "open",
                "notified": False,
                "run_status": "FINISHED",
                "agent_status": "ACTIVE",
            },
            {
                "bc_id": "bc-live",
                "seat": "ops",
                "status": "open",
                "notified": False,
            },
        ],
    )
    probes: list[str] = []

    def _probe(bc_id: str) -> dict[str, Any]:
        probes.append(bc_id)
        return {
            "runStatus": "RUNNING",
            "agentStatus": "ACTIVE",
            "status": "RUNNING",
        }

    def _no_notify(*_a: Any, **_k: Any) -> None:
        raise AssertionError("shepherd must not notify leftovers or RUNNING orphans")

    mod._probe = _probe  # type: ignore[assignment]
    mod.notify_owner = _no_notify  # type: ignore[assignment]

    assert mod._cycle() == 0
    assert probes == ["bc-live"]


def test_shepherd_prunes_closed_finished_and_cancelled_keeps_running(
    tmp_path: Path,
) -> None:
    """Closed terminal leftovers leave the ledger; RUNNING is not cancelled."""
    mod = _load()
    _bind(mod, tmp_path)
    _plant(
        tmp_path / "ops",
        [
            {
                "bc_id": "bc-closed-finished",
                "seat": "ops",
                "status": "closed",
                "notified": True,
                "notified_by": "waiter",
                "run_status": "FINISHED",
                "waiter_pid": None,
            },
            {
                "bc_id": "bc-closed-cancelled",
                "seat": "ops",
                "status": "closed",
                "notified": True,
                "notified_by": "shepherd",
                "run_status": "CANCELLED",
                "waiter_pid": None,
            },
            {
                "bc_id": "bc-us-canceled",
                "seat": "ops",
                "status": "closed",
                "notified": True,
                "notified_by": "webhook",
                "run_status": "CANCELED",
                "waiter_pid": None,
            },
            {
                "bc_id": "bc-leftover",
                "seat": "ops",
                "status": "open",
                "notified": False,
                "run_status": "FINISHED",
                "agent_status": "ACTIVE",
                "waiter_pid": None,
            },
            {
                "bc_id": "bc-running",
                "seat": "ops",
                "status": "open",
                "notified": False,
                "run_status": "RUNNING",
                "waiter_pid": None,
            },
        ],
    )
    probes: list[str] = []
    notifies: list[str] = []
    cancels: list[str] = []

    def _probe(bc_id: str) -> dict[str, Any]:
        probes.append(bc_id)
        return {
            "runStatus": "RUNNING",
            "agentStatus": "ACTIVE",
            "status": "RUNNING",
        }

    def _notify(bc_id: str, payload: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        notifies.append(bc_id)
        raise AssertionError("shepherd must not page closed leftovers as live")

    mod._probe = _probe  # type: ignore[assignment]
    mod.notify_owner = _notify  # type: ignore[assignment]
    mod.cancel_agent = lambda bc_id: cancels.append(bc_id)  # type: ignore[attr-defined]

    assert mod._cycle() == 0
    remaining = {row["bc_id"] for row in _load_jsonl(tmp_path / "ops")}
    assert remaining == {"bc-leftover", "bc-running"}
    assert "bc-closed-finished" not in remaining
    assert "bc-closed-cancelled" not in remaining
    assert "bc-us-canceled" not in remaining
    assert probes == ["bc-running"]
    assert notifies == []
    assert cancels == []
    log = _log_text(mod)
    assert "SHEPHERD_PRUNE" in log
    assert "bc-closed-finished" in log
    assert "bc-closed-cancelled" in log
    assert "Bot CloudAgent" not in log
    assert "Emerald" not in log


def test_shepherd_does_not_probe_notified_closed_after_prune(
    tmp_path: Path,
) -> None:
    """Closed leftovers are gone after one cycle — not skipped as live pages."""
    mod = _load()
    _bind(mod, tmp_path)
    _plant(
        tmp_path / "ops",
        [
            {
                "bc_id": "bc-closed",
                "seat": "ops",
                "status": "closed",
                "notified": True,
                "notified_by": "waiter",
                "run_status": "FINISHED",
                "waiter_pid": None,
            }
        ],
    )
    probes: list[str] = []

    def _probe(bc_id: str) -> dict[str, Any]:
        probes.append(bc_id)
        return {
            "runStatus": "FINISHED",
            "agentStatus": "ACTIVE",
            "status": "FINISHED",
        }

    def _no_notify(bc_id: str, payload: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("closed leftover must not be notified")

    mod._probe = _probe  # type: ignore[assignment]
    mod.notify_owner = _no_notify  # type: ignore[assignment]

    assert mod._cycle() == 0
    assert probes == []
    assert _load_jsonl(tmp_path / "ops") == []


def test_prune_feature_binds_shepherd_and_ledger() -> None:
    text = PRUNE_FEATURE.read_text(encoding="utf-8")
    assert "prune closed leftover" in text
    assert "FINISHED" in text
    assert "CANCELLED" in text
    assert "RUNNING" in text
    assert "gcs-fleet-dedupe-notify-floor1747" in text
    assert "Bot CloudAgent" in text


def test_scope_does_not_clone_siblings_or_reconnect_ak() -> None:
    text = SHEPHERD.read_text(encoding="utf-8")
    assert "is_leftover_shell" in text
    assert "SHEPHERD_SKIP leftover" in text
    assert "prune_closed_leftovers" in text
    assert "SHEPHERD_PRUNE" in text
    assert "agent-kanban" not in text
    assert "ak start" not in text
    assert "Black Swan" not in text
    assert "bot-bridge" not in text
    assert "Bot CloudAgent" not in text
    assert "GROK_HOME" not in text
    assert "install-grok-mcp" not in text
    assert "mcp_servers.taskboard" not in text
    assert "list --running" not in text
    assert "TASK_STATE_COMPLETED" not in text
    assert "occupancy-count" not in text
    assert BOT_BRIDGE.is_file()


def test_docs_name_taskboard_health_tokens() -> None:
    arch = ARCH.read_text(encoding="utf-8")
    board = TASKBOARD_DOC.read_text(encoding="utf-8")
    cloud = CLOUD_README.read_text(encoding="utf-8")
    blob = arch + "\n" + board + "\n" + cloud
    assert "TASKBOARD_HEALTH_OK" in blob
    assert "TASKBOARD_HEALTH_FAIL" in blob
    assert "ticket list" in blob
    assert "/mcp" in blob
    assert "fleet-shepherd" in blob.lower() or "fleet-shepherd.py" in blob
    assert "skip ACTIVE+FINISHED leftovers" in arch
    assert "does not `get_agent_run`" in cloud
    assert "paged as live" in (arch + "\n" + cloud).lower()
    assert "prune_closed_leftovers" in cloud
    assert "ak start" not in board or "do not" in board.lower()
    if "Black Swan" in blob:
        assert "never" in blob.lower()
