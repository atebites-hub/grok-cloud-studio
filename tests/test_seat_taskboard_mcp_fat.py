"""Factory acceptance for seat taskboard stdio MCP (GROK_HOME, not Cursor).

Law: isolated GROK_HOME/config.toml registers
`taskboard --db $GCS_TASKBOARD_DB mcp`. Cursor `${workspaceFolder}` never
expands under grok. Two catalogs. Do not clone PAL-45 Linear MCP
(#46/#79). Never Bot CloudAgent (skipSeats). Living Sky LIV is the Linear
workspace — not this catalog.

Fake binary / fake MCP stdio only. No live grok serve. No live Linear.
No live ticket moves.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
LIB = REPO / "scripts" / "a2a" / "lib.py"
SETUP = REPO / "setup.sh"
INSTALL_GROK_MCP = REPO / "scripts" / "directors" / "install-grok-mcp.sh"
SEAT_GROK_MCP = REPO / "scripts" / "directors" / "seat_grok_mcp.py"
DOCTOR = REPO / "doctor.sh"
FEATURE = REPO / "tests" / "bdd" / "seat_taskboard_stdio_mcp.feature"
CURSOR_MCP = REPO / ".cursor" / "mcp.json"
TASKBOARD_DOC = REPO / "docs" / "studio" / "TASKBOARD.md"
WIPE = REPO / "docs" / "studio" / "WIPE.md"
AGENTS = REPO / "AGENTS.md"
MIND_DOC = REPO / "docs" / "studio" / "MIND.md"

WORKSPACE_FOLDER_TOKEN = "${" + "workspaceFolder}"
BOT_SKIP = ("donald", "orchestrator")
PALEMON_MIND = (
    "floor-ops,studio-ops,floor,art,content,systems,qa-a,qa-b,audio,narrative"
)
PALEMON_ACP = "floor-ops,floor,studio-ops,art,content,systems"
MIND_ONLY = ("qa-a", "qa-b", "audio", "narrative")

_FAKE_MCP_PY = r"""#!/usr/bin/env python3
import json
import sys

log = sys.argv[0] + ".argv"
with open(log, "a", encoding="utf-8") as fh:
    fh.write(" ".join(sys.argv[1:]) + "\n")

def reply(msg, result):
    out = {"jsonrpc": "2.0", "id": msg.get("id"), "result": result}
    sys.stdout.write(json.dumps(out) + "\n")
    sys.stdout.flush()

for raw in sys.stdin:
    line = raw.strip()
    if not line:
        continue
    msg = json.loads(line)
    method = msg.get("method")
    if method == "initialize":
        reply(
            msg,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "taskboard", "version": "0.6.0"},
            },
        )
    elif method == "tools/list":
        reply(
            msg,
            {
                "tools": [
                    {
                        "name": "taskboard_ticket_list",
                        "description": "list tickets",
                        "inputSchema": {"type": "object"},
                    }
                ]
            },
        )
    elif method == "notifications/initialized":
        continue
    else:
        err = {
            "jsonrpc": "2.0",
            "id": msg.get("id"),
            "error": {"code": -32601, "message": str(method)},
        }
        sys.stdout.write(json.dumps(err) + "\n")
        sys.stdout.flush()
"""


def _write_exec(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def _lib_env(tmp_path: Path, extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in {
            "GCS_ACP_SEATS",
            "GCS_MIND_SEATS",
            "GCS_GROW_SEATS",
            "GCS_WAKE_SEATS",
            "GROK_HOME",
            "GCS_TASKBOARD_DB",
            "TASKBOARD_DB",
            "TASKBOARD_BIN",
        }
    }
    env.update(
        {
            "GCS_ROOT": str(REPO),
            "GCS_A2A_STATE": str(tmp_path / "a2a-state"),
            "HOME": str(tmp_path / "home"),
            "LC_ALL": "C",
            "TERM": "dumb",
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        }
    )
    if extra:
        env.update(extra)
    return env


def _lib_cmd(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(LIB), *args],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )


def _mcp_seats(env: dict[str, str]) -> list[str]:
    proc = _lib_cmd(["mcp-seats"], env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]


def test_bdd_feature_binds_fat_scenarios() -> None:
    assert FEATURE.is_file(), "missing tests/bdd/seat_taskboard_stdio_mcp.feature"
    text = FEATURE.read_text(encoding="utf-8")
    assert "GROK_HOME" in text
    assert "config.toml" in text
    assert "--db" in text and "mcp" in text
    assert "workspaceFolder" in text
    assert "Linear MCP" in text or "linear" in text.lower()
    assert "mcp-seats" in text
    assert "skipSeats" in text or "orchestrator" in text
    assert "Living Sky" in text or "LIV" in text
    for title in (
        "mcp-seats is the union of launch seats and mind seats minus skipSeats",
        "Factory setup writes absolute stdio MCP without starting serve",
        "Written command speaks stdio JSON-RPC tools/list",
        "GROK_HOME catalog has taskboard stdio and no workspaceFolder",
        "Cursor catalog is a second catalog, not the grok serve config",
    ):
        assert title in text, title


def test_mcp_seats_cli_unions_mind_and_launch_excludes_bot(tmp_path: Path) -> None:
    env = _lib_env(
        tmp_path,
        {"GCS_ACP_SEATS": PALEMON_ACP, "GCS_MIND_SEATS": PALEMON_MIND},
    )
    seats = _mcp_seats(env)
    launch = [
        ln.strip()
        for ln in _lib_cmd(["launch-seats"], env).stdout.splitlines()
        if ln.strip()
    ]
    mind = [
        ln.strip()
        for ln in _lib_cmd(["mind-seats"], env).stdout.splitlines()
        if ln.strip()
    ]
    skipped = [
        ln.strip()
        for ln in _lib_cmd(["skip-seats"], env).stdout.splitlines()
        if ln.strip()
    ]
    assert set(seats) == set(launch) | set(mind)
    for name in MIND_ONLY:
        assert name in seats, name
    for name in BOT_SKIP:
        assert name not in seats
        assert name in skipped or name in ("donald", "orchestrator")
    assert "donald" not in seats
    assert "orchestrator" not in seats
    usage = _lib_cmd(["-h"], env)
    assert usage.returncode == 2
    assert "mcp-seats" in usage.stderr


def test_install_grok_mcp_default_uses_mcp_seats_not_acp_subset(
    tmp_path: Path,
) -> None:
    binary = _write_exec(
        tmp_path / "host-bin" / "taskboard",
        "#!/bin/sh\nexit 0\n",
    )
    env = _lib_env(
        tmp_path,
        {
            "GCS_ACP_SEATS": PALEMON_ACP,
            "GCS_MIND_SEATS": PALEMON_MIND,
            "TASKBOARD_BIN": str(binary),
            "PATH": f"{binary.parent}:/usr/bin:/bin",
        },
    )
    (tmp_path / "home").mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["bash", str(INSTALL_GROK_MCP)],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "grok agent serve" not in blob
    state = tmp_path / "a2a-state"
    db = state / "taskboard" / "taskboard.db"
    for seat in (*MIND_ONLY, "floor", "systems"):
        cfg = state / seat / "grok-home" / "config.toml"
        assert cfg.is_file(), f"missing {seat} GROK_HOME MCP\n{blob}"
        parsed = tomllib.loads(cfg.read_text(encoding="utf-8"))
        tb = parsed["mcp_servers"]["taskboard"]
        assert Path(tb["command"]).resolve() == binary.resolve()
        assert tb["args"] == ["--db", str(db.resolve()), "mcp"]
        assert parsed["compat"]["cursor"]["mcps"] is False
        linear = parsed.get("mcp_servers", {}).get("linear")
        if linear is not None:
            assert "mcp.linear.app" in str(linear.get("url") or "")
            header_blob = json.dumps(linear.get("headers") or {})
            assert "${LINEAR_API_KEY}" in header_blob
            assert "lin_api_" not in header_blob
        raw = cfg.read_text(encoding="utf-8")
        assert WORKSPACE_FOLDER_TOKEN not in raw
        assert "lin_api_" not in raw
    for seat in BOT_SKIP:
        cfg = state / seat / "grok-home" / "config.toml"
        assert not cfg.is_file(), f"Bot CloudAgent seat {seat} must not get MCP"


def test_setup_skip_start_still_writes_mcp_catalogs(tmp_path: Path) -> None:
    binary = _write_exec(
        tmp_path / "host-bin" / "taskboard",
        "#!/bin/sh\nexit 0\n",
    )
    state = tmp_path / "a2a-state"
    env = _lib_env(
        tmp_path,
        {
            "TASKBOARD_BIN": str(binary),
            "GCS_SETUP_SKIP_INSTALL": "1",
            "GCS_SETUP_SKIP_SUBMODULE": "1",
            "GCS_SETUP_SKIP_START": "1",
            "GCS_SETUP_SKIP_DOCTOR": "1",
            "GCS_SETUP_SKIP_HEALTH": "1",
            "GCS_BOT_BIND_OPTIONAL": "1",
            "PATH": f"{binary.parent}:/usr/bin:/bin",
        },
    )
    proc = subprocess.run(
        ["bash", str(SETUP)],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "SETUP_OK" in blob
    assert "grok agent serve" not in blob
    setup_src = SETUP.read_text(encoding="utf-8")
    assert "install-grok-mcp.sh" in setup_src
    assert "start-studio-bus.sh start --daemons" not in setup_src
    cfg = state / "qa-a" / "grok-home" / "config.toml"
    assert cfg.is_file(), blob
    parsed = tomllib.loads(cfg.read_text(encoding="utf-8"))
    assert parsed["mcp_servers"]["taskboard"]["args"][-1] == "mcp"
    linear = parsed.get("mcp_servers", {}).get("linear")
    if linear is not None:
        assert "${LINEAR_API_KEY}" in json.dumps(linear.get("headers") or {})
    assert not (state / "orchestrator" / "grok-home" / "config.toml").is_file()
    assert not (state / "donald" / "grok-home" / "config.toml").is_file()


def test_written_stdio_mcp_answers_tools_list(tmp_path: Path) -> None:
    fake = _write_exec(tmp_path / "host-bin" / "taskboard", _FAKE_MCP_PY)
    env = _lib_env(
        tmp_path,
        {
            "TASKBOARD_BIN": str(fake),
            "GROK_HOME": str(tmp_path / "grok-home"),
            "PATH": f"{fake.parent}:/usr/bin:/bin",
        },
    )
    proc = subprocess.run(
        [
            "bash",
            "-c",
            "set -euo pipefail; source scripts/directors/seat-daemon-common.sh; "
            "install_seat_grok_mcp floor",
        ],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    cfg = Path(env["GROK_HOME"]) / "config.toml"
    parsed = tomllib.loads(cfg.read_text(encoding="utf-8"))
    spec = parsed["mcp_servers"]["taskboard"]
    argv = [spec["command"], *spec["args"]]
    assert spec["args"][0] == "--db"
    assert spec["args"][2] == "mcp"
    payload = (
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "gcs-fat", "version": "1"},
                },
            }
        )
        + "\n"
        + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        + "\n"
    )
    child = subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        stdout, stderr = child.communicate(input=payload, timeout=5)
    except subprocess.TimeoutExpired:
        child.kill()
        pytest.fail("fake taskboard MCP hung")
    assert child.returncode == 0, stderr
    lines = [json.loads(ln) for ln in stdout.splitlines() if ln.strip()]
    assert any(row.get("id") == 1 and "result" in row for row in lines), stdout
    listed = next(row for row in lines if row.get("id") == 2)
    names = {t["name"] for t in listed["result"]["tools"]}
    assert "taskboard_ticket_list" in names
    argv_log = Path(str(fake) + ".argv")
    recorded = argv_log.read_text(encoding="utf-8") if argv_log.is_file() else ""
    db = tmp_path / "a2a-state" / "taskboard" / "taskboard.db"
    assert "--db" in recorded
    assert "mcp" in recorded
    assert str(db.resolve()) in recorded or str(db) in recorded
    assert WORKSPACE_FOLDER_TOKEN not in recorded


def test_grok_home_factory_keeps_taskboard_stdio_two_catalogs() -> None:
    """Factory unique slice is mcp-seats write. Linear HTTP may exist from main."""
    text = SEAT_GROK_MCP.read_text(encoding="utf-8")
    assert "mcp_servers.taskboard" in text
    assert WORKSPACE_FOLDER_TOKEN not in text
    cursor = json.loads(CURSOR_MCP.read_text(encoding="utf-8"))
    servers = cursor.get("mcpServers") or {}
    assert "taskboard" in servers
    blob = json.dumps(cursor)
    assert "lin_api_" not in blob
    assert "CURSOR_API_KEY" not in blob
    joined = " ".join(str(x) for x in servers["taskboard"].get("args") or [])
    assert "run-mcp.sh" in joined or "run-mcp.sh" in blob


def test_docs_and_doctor_name_factory_grok_home_mcp() -> None:
    doctor = DOCTOR.read_text(encoding="utf-8")
    assert "scripts/directors/install-grok-mcp.sh" in doctor
    setup = SETUP.read_text(encoding="utf-8")
    assert "install-grok-mcp.sh" in setup
    installer = INSTALL_GROK_MCP.read_text(encoding="utf-8")
    assert "mcp-seats" in installer
    assert "LAUNCH_SEATS[@]" not in installer.split("if [[ ${#seats[@]} -eq 0 ]]", 1)[1]
    blob = "\n".join(
        p.read_text(encoding="utf-8")
        for p in (TASKBOARD_DOC, WIPE, AGENTS, MIND_DOC)
    )
    assert "GROK_HOME" in blob
    assert "config.toml" in blob
    assert "taskboard" in blob.lower()
    assert "mcp" in blob.lower()
    assert WORKSPACE_FOLDER_TOKEN in blob
    low = blob.lower()
    assert "never" in low
    assert "two catalog" in low or "two catalogs" in low
