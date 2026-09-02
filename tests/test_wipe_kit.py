"""Wipe-ready studio kit: Palemon floor seats, taskboard host scripts, no AK.

Static + subprocess checks only. Does not start grok serve, Extra High, or Tailscale.
Never asserts secret values.
"""
from __future__ import annotations

import json
import os
import socket
import stat
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LIB = REPO / "scripts" / "a2a" / "lib.py"
BUS = REPO / "scripts" / "a2a" / "start-studio-bus.sh"
DOCTOR = REPO / "doctor.sh"
INSTALL = REPO / "install.sh"
README = REPO / "README.md"
WIPE = REPO / "docs" / "studio" / "WIPE.md"
MIND_DOC = REPO / "docs" / "studio" / "MIND.md"
CURSOR_MCP = REPO / ".cursor" / "mcp.json"
STUDIO_ENV_EXAMPLE = REPO / "studio.env.example"
DOT_ENV_EXAMPLE = REPO / ".env.example"
REGISTRY = REPO / "docs" / "a2a" / "registry.json"
TASKBOARD_DIR = REPO / "scripts" / "studio" / "taskboard"
RUN_MCP = TASKBOARD_DIR / "run-mcp.sh"
START_TB = TASKBOARD_DIR / "start-taskboard.sh"
MCP_HTTP = TASKBOARD_DIR / "mcp-http.sh"
MCP_GW = TASKBOARD_DIR / "mcp_http_gateway.py"
INSTALL_TB = TASKBOARD_DIR / "install-taskboard.sh"
TS_SERVE = TASKBOARD_DIR / "start-tailscale-serve.sh"
TB_README = TASKBOARD_DIR / "README.md"
CURSOR_GROK = REPO / "scripts" / "host" / "cursor-grok"
SOULS = REPO / "docs" / "studio" / "directors" / "souls"

PALEMON_MIND = (
    "floor-ops,studio-ops,floor,art,content,systems,qa-a,qa-b,audio,narrative"
)
PALEMON_ACP = "floor-ops,floor,studio-ops,art,content,systems"
LIVE_PORTS = {
    "floor": 8740,
    "floor-ops": 8753,
    "studio-ops": 8752,
    "art": 8746,
    "content": 8742,
    "systems": 8744,
    "qa-a": 8748,
    "qa-b": 8751,
    "audio": 8754,
    "narrative": 8755,
}

PRIVATE_GAME = "atebites-hub/" + "palemon"
_CREATURE_LORE = "Pok" + "emon"


def _write_exec(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_agent_kanban_tree_absent() -> None:
    assert not (REPO / "scripts" / "studio" / "agent-kanban").exists()
    assert not (REPO / "docs" / "studio" / "AGENT_KANBAN.md").exists()
    bus = BUS.read_text(encoding="utf-8")
    assert "agent-kanban" not in bus
    assert "ak start" not in bus or "never" in bus.lower()
    for path in (START_TB, MCP_HTTP, INSTALL_TB, TS_SERVE, MCP_GW):
        text = path.read_text(encoding="utf-8")
        assert "ak start" not in text
        assert "mint-floor-ops-worker" not in text


def test_wipe_kit_files_exist() -> None:
    for path in (
        WIPE,
        REPO / "setup.sh",
        REPO / "cleanup.sh",
        REPO / ".gitmodules",
        STUDIO_ENV_EXAMPLE,
        START_TB,
        MCP_HTTP,
        MCP_GW,
        INSTALL_TB,
        TS_SERVE,
        TB_README,
        TASKBOARD_DIR / "maintainer.sh",
        TASKBOARD_DIR / "health-taskboard.sh",
        RUN_MCP,
        CURSOR_MCP,
        MIND_DOC,
        CURSOR_GROK,
        REPO / "docs" / "a2a" / "cards" / "art.json",
        REPO / "docs" / "a2a" / "cards" / "floor-ops.json",
        REPO / "docs" / "a2a" / "cards" / "content.json",
        REPO / "docs" / "a2a" / "cards" / "systems.json",
        REPO / "docs" / "a2a" / "cards" / "studio-ops.json",
        REPO / "docs" / "a2a" / "cards" / "audio.json",
        REPO / "docs" / "a2a" / "cards" / "narrative.json",
        SOULS / "art" / "SOUL.md",
        SOULS / "content" / "SOUL.md",
        SOULS / "floor-ops" / "SOUL.md",
        SOULS / "systems" / "SOUL.md",
        SOULS / "audio" / "SOUL.md",
        SOULS / "narrative" / "SOUL.md",
    ):
        assert path.is_file(), f"missing {path.relative_to(REPO)}"


def test_bus_points_at_taskboard_or_wipe() -> None:
    bus = BUS.read_text(encoding="utf-8")
    assert "scripts/studio/taskboard/start-taskboard.sh" in bus or "docs/studio/WIPE.md" in bus
    assert "WIPE.md" in bus or "start-taskboard.sh" in bus
    assert "--daemons" in bus
    assert "15GB" in bus or "OOM" in bus or "full registry" in bus


def test_readme_points_at_wipe() -> None:
    text = README.read_text(encoding="utf-8")
    assert "WIPE.md" in text
    assert "Palemon studio wipe" in text or "studio wipe" in text.lower()
    assert "start-studio-bus.sh start" in text
    assert "setup.sh" in text
    assert "cleanup.sh" in text
    assert PRIVATE_GAME not in text


def test_studio_env_example_matches_live_knobs() -> None:
    text = STUDIO_ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "studio.env is sourced from $GCS_A2A_STATE/studio.env" in text or "GCS_A2A_STATE/studio.env" in text
    assert "not committed" in text.lower() or "do not commit" in text.lower()
    assert "GCS_MIND_SEATS=" in text
    assert "floor-ops" in text and "studio-ops" in text and "art" in text
    assert "content" in text and "systems" in text and "qa-a" in text and "qa-b" in text
    assert "audio" in text and "narrative" in text
    assert "GCS_ACP_SEATS=" in text
    assert "GCS_GROW_SEATS=" in text
    assert "GCS_WAKE_SEATS=" in text
    assert "GCS_MIND_PLUS_ACP_WAKE=0" in text
    assert "GROK_USE_LEADER=0" in text
    assert "GCS_ACP_INJECT_TIMEOUT=600" in text
    assert "GCS_WAKE_ACP_TIMEOUT=600" in text
    assert "GCS_ACP_ACCEPT_DEADLINE=120" in text
    assert "GCS_TICKER_SEC=600" in text
    assert "GCS_ACP_DEAD_STREAK=3" in text
    assert "palemon-floor-main" in text or "recovered-studio" in text.lower()
    assert "--daemons" in text
    assert "15GB" in text or "13-seat" in text
    assert PRIVATE_GAME not in text
    assert "CURSOR_API_KEY=" not in text or "CURSOR_API_KEY=\n" in text or "# CURSOR_API_KEY" in text
    assert "TAILSCALE_AUTH_KEY=" not in text or text.count("TAILSCALE_AUTH_KEY=") == 0
    # AK stays gone: omit or set 0. Never a bridge that reconnects Agent Kanban.
    if "PALEMON_AK_BRIDGE" in text:
        assert "PALEMON_AK_BRIDGE=0" in text
    # PAL-25: bot-bridge stays off unless opted in. wipe/recover must not resurrect it.
    assert "GCS_BOT_BRIDGE=0" in text


def test_dot_env_example_documents_eight_seat_mind_and_timeout_600() -> None:
    text = DOT_ENV_EXAMPLE.read_text(encoding="utf-8")
    assert PALEMON_MIND in text
    assert "GCS_ACP_INJECT_TIMEOUT=600" in text
    assert "GCS_ACP_SEATS=floor,studio-ops" in text


def test_mind_seats_keeps_eight_palemon_names() -> None:
    env = {
        **os.environ,
        "GCS_MIND_SEATS": PALEMON_MIND,
        "GCS_ROOT": str(REPO),
    }
    env.pop("GCS_SKIP_SEATS", None)
    proc = subprocess.run(
        ["python3", str(LIB), "mind-seats"],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, proc.stderr
    seats = {s.strip() for s in proc.stdout.splitlines() if s.strip()}
    wanted = {s.strip() for s in PALEMON_MIND.split(",")}
    assert wanted <= seats, f"dropped {wanted - seats}; got {seats}"
    assert "ops" not in wanted
    assert "studio-ops" in seats
    assert "floor-ops" in seats
    assert "donald" not in seats
    assert "orchestrator" not in seats


def test_launch_seats_keeps_first_class_palemon_names() -> None:
    env = {
        **os.environ,
        "GCS_ACP_SEATS": PALEMON_ACP,
        "GCS_ROOT": str(REPO),
    }
    proc = subprocess.run(
        ["python3", str(LIB), "launch-seats"],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, proc.stderr
    seats = [s.strip() for s in proc.stdout.splitlines() if s.strip()]
    wanted = [s.strip() for s in PALEMON_ACP.split(",")]
    assert seats == wanted, seats
    assert "ops" not in seats


def test_live_registry_ports_and_skip_seats() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    assert registry["skipSeats"] == ["orchestrator", "donald"]
    seats = registry["seats"]
    for name, port in LIVE_PORTS.items():
        assert name in seats, f"missing first-class seat {name}"
        assert int(seats[name]["acpPort"]) == port, name
    assert "ops" in seats
    assert "cloud" in seats
    got = subprocess.check_output(
        ["python3", str(LIB), "port", "studio-ops"],
        cwd=str(REPO),
        text=True,
    ).strip()
    assert got == "8752"
    floor_ops = subprocess.check_output(
        ["python3", str(LIB), "port", "floor-ops"],
        cwd=str(REPO),
        text=True,
    ).strip()
    assert floor_ops == "8753"


def test_souls_are_clean_room_no_pokemon() -> None:
    for seat in ("art", "content", "floor-ops", "systems", "audio", "narrative"):
        soul = (SOULS / seat / "SOUL.md").read_text(encoding="utf-8")
        assert seat.replace("-", " ") in soul.lower() or seat in soul.lower()
        assert _CREATURE_LORE.lower() not in soul.lower()
        assert "harbor" + "light" not in soul.lower()
        assert PRIVATE_GAME not in soul
    art = (SOULS / "art" / "SOUL.md").read_text(encoding="utf-8").lower()
    assert "higgsfield" in art
    assert "oauth" in art
    assert "donald" in art
    content = (SOULS / "content" / "SOUL.md").read_text(encoding="utf-8").lower()
    assert "clean-room" in content or "clean room" in content
    floor_ops = (SOULS / "floor-ops" / "SOUL.md").read_text(encoding="utf-8").lower()
    assert "unstick" in floor_ops or "ticket" in floor_ops
    assert "launch" in floor_ops
    systems = (SOULS / "systems" / "SOUL.md").read_text(encoding="utf-8").lower()
    assert "schema" in systems or "sim" in systems or "math" in systems
    audio = (SOULS / "audio" / "SOUL.md").read_text(encoding="utf-8").lower()
    assert "audio" in audio
    assert "launch-cloud-extra-high" in audio
    narrative = (SOULS / "narrative" / "SOUL.md").read_text(encoding="utf-8").lower()
    assert "narrative" in narrative
    assert "launch-cloud-extra-high" in narrative


def test_install_stays_secret_free_and_does_not_auto_install_host_bins() -> None:
    text = INSTALL.read_text(encoding="utf-8")
    assert "CURSOR_API_KEY=" not in text
    assert "curl https://cursor.com/install" not in text
    assert "brew install taskboard" not in text
    assert "brew tap" not in text
    assert "scripts/studio/taskboard" in text
    assert "WIPE.md" in text or "taskboard" in text


def test_doctor_warns_on_missing_host_bins_and_fails_on_ak() -> None:
    text = DOCTOR.read_text(encoding="utf-8")
    assert "WARN" in text
    assert "taskboard" in text
    assert "cursor-grok" in text or "agent" in text
    assert "agent-kanban" in text
    assert "FAIL" in text or "bad " in text
    assert ".cursor/mcp.json" in text
    assert "run-mcp.sh" in text
    assert ".gitmodules" in text


def test_wipe_doc_has_host_bootstrap_steps() -> None:
    text = WIPE.read_text(encoding="utf-8")
    assert "install.sh" in text
    assert "studio.env.example" in text
    assert "GCS_A2A_STATE" in text
    assert "cursor.com/install" in text
    assert "scripts/host/cursor-grok" in text
    assert "install-taskboard.sh" in text
    assert "start-taskboard.sh start" in text
    assert "mcp-http.sh start" in text
    assert "start-studio-bus.sh start" in text
    assert "--daemons" in text
    assert "402" in text
    assert "Higgsfield" in text or "higgsfield" in text
    assert "TAILSCALE" in text or "tailscale" in text
    assert PRIVATE_GAME not in text
    assert "CURSOR_API_KEY" in text
    assert "setup.sh" in text
    assert "cleanup.sh" in text
    assert "vendor/taskboard" in text
    assert "--recurse-submodules" in text
    assert "submodule update --init" in text


def test_install_taskboard_uses_brew_or_release_tarball_not_compile() -> None:
    text = INSTALL_TB.read_text(encoding="utf-8")
    assert "tcarac/taskboard" in text
    assert "v0.6.0" in text
    assert "brew tap tcarac/taskboard" in text
    assert "releases/download" in text
    assert "compile" in text.lower()
    assert "go build" not in text
    assert "make build" not in text
    assert "vendor/taskboard" in text


def test_tailscale_serve_script_is_secret_free_and_skippable() -> None:
    text = TS_SERVE.read_text(encoding="utf-8")
    assert "PALEMON_TAILSCALE_SERVE" in text
    assert "palemon-studio.panther-arctic.ts.net" in text
    assert "--set-path=/" in text
    assert "--set-path=/mcp" in text
    assert "3010" in text and "3011" in text
    assert "funnel" in text.lower()
    assert "TAILSCALE_AUTH_KEY=" not in text
    env = {
        "PATH": "/usr/bin:/bin",
        "PALEMON_TAILSCALE_SERVE": "0",
        "GCS_ROOT": str(REPO),
        "HOME": "/tmp",
        "LC_ALL": "C",
    }
    proc = subprocess.run(
        ["bash", str(TS_SERVE), "start"],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "SKIP" in blob
    assert "tskey" not in blob.lower()


def test_start_taskboard_uses_state_db_and_accepts_palemon_alias(
    tmp_path: Path,
) -> None:
    log = tmp_path / "tb.argv"
    fake = _write_exec(
        tmp_path / "bin" / "taskboard",
        "#!/bin/sh\n"
        f'echo "$@" >> "{log}"\n'
        'for a in "$@"; do\n'
        '  if [ "$a" = "--foreground" ]; then sleep 20; fi\n'
        "done\n",
    )
    state = tmp_path / "live-state"
    env = {
        "PATH": f"{fake.parent}:/usr/bin:/bin",
        "HOME": str(tmp_path / "home"),
        "GCS_ROOT": str(REPO),
        "PALEMON_A2A_STATE": str(state),
        "TASKBOARD_BIN": str(fake),
        "LC_ALL": "C",
        "TERM": "dumb",
    }
    env.pop("GCS_A2A_STATE", None)
    start = subprocess.run(
        ["bash", str(START_TB), "start"],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    blob = start.stdout + start.stderr
    assert start.returncode == 0, blob
    argv = log.read_text(encoding="utf-8") if log.is_file() else ""
    db = state / "taskboard" / "taskboard.db"
    assert "--db" in argv
    assert str(db) in argv
    assert "start" in argv
    assert "3010" in argv
    status = subprocess.run(
        ["bash", str(START_TB), "status"],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert status.returncode == 0, status.stdout + status.stderr
    subprocess.run(
        ["bash", str(START_TB), "stop"],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_mcp_http_gateway_proxies_stdio_child(tmp_path: Path) -> None:
    child = _write_exec(
        tmp_path / "fake-mcp.py",
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "def read():\n"
        "    headers = {}\n"
        "    while True:\n"
        "        raw = sys.stdin.buffer.readline()\n"
        "        if not raw:\n"
        "            return None\n"
        "        if raw in (b'\\r\\n', b'\\n'):\n"
        "            break\n"
        "        line = raw.decode().strip()\n"
        "        if ':' in line:\n"
        "            k, v = line.split(':', 1)\n"
        "            headers[k.strip().lower()] = v.strip()\n"
        "    n = int(headers.get('content-length') or '0')\n"
        "    body = sys.stdin.buffer.read(n) if n else b'{}'\n"
        "    return json.loads(body.decode())\n"
        "def write(obj):\n"
        "    blob = json.dumps(obj).encode()\n"
        "    sys.stdout.buffer.write(f'Content-Length: {len(blob)}\\r\\n\\r\\n'.encode() + blob)\n"
        "    sys.stdout.buffer.flush()\n"
        "while True:\n"
        "    msg = read()\n"
        "    if msg is None:\n"
        "        break\n"
        "    if msg.get('id') is None:\n"
        "        continue\n"
        "    write({'jsonrpc': '2.0', 'id': msg['id'], 'result': {'ok': True, 'method': msg.get('method')}})\n",
    )
    port = _free_port()
    log = tmp_path / "gw.log"
    proc = subprocess.Popen(
        [
            "python3",
            str(MCP_GW),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--bin",
            str(child),
            "--db",
            str(tmp_path / "taskboard.db"),
        ],
        cwd=str(REPO),
        stdout=log.open("w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.time() + 5
        health = None
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"{url}/health", timeout=0.3) as resp:
                    health = json.loads(resp.read().decode("utf-8"))
                    if health.get("ok"):
                        break
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
                time.sleep(0.05)
        assert health and health.get("ok") is True, log.read_text(encoding="utf-8") if log.is_file() else "no log"
        req = urllib.request.Request(
            f"{url}/mcp",
            data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        assert body["result"]["ok"] is True
        assert body["result"]["method"] == "initialize"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_cursor_grok_wrapper_pins_model_and_does_not_print_keys() -> None:
    text = CURSOR_GROK.read_text(encoding="utf-8")
    assert "cursor-grok-4.6-xhigh" in text
    assert "agent.env" in text
    assert "${HOME}/.local/bin" in text or "$HOME/.local/bin" in text
    assert "echo \"$CURSOR_API_KEY\"" not in text
    assert "echo $CURSOR_API_KEY" not in text
    assert "--model cursor-grok-4.6-xhigh" in text


def test_taskboard_readme_covers_wipe_board_start() -> None:
    text = TB_README.read_text(encoding="utf-8")
    assert "start-taskboard.sh" in text
    assert "mcp-http.sh" in text
    assert "3010" in text and "3011" in text
    assert "install-taskboard.sh" in text
    assert "Agent Kanban" in text or "ak" in text.lower()
    assert "ak start" not in text
    assert ".cursor/mcp.json" in text or "run-mcp.sh" in text
    assert "vendor/taskboard" in text or "submodule" in text.lower()


_TWO_CATALOG_NEEDLES = (
    "two catalogs",
    "inbox.jsonl",
    "mind/offset",
    "GROK_HOME",
    "Never fake a transfer",
    "ticket",
    "tb",
    "scripts/a2a/send.sh",
    "scripts/launch-cloud-extra-high.sh",
    "Higgsfield",
    "deliver_wake",
    "session/prompt",
    "Cursor Cloud",
    "Extra High",
    "Cursor Cloud API",
    "fast=false",
    "grok-4.6",
    "xhigh",
    "cursor-grok-4.6-xhigh",
    "one mailbox",
)


def _fold(text: str) -> str:
    return " ".join(text.split()).lower()


def test_two_runtime_mind_law_in_mind_and_wipe() -> None:
    mind = MIND_DOC.read_text(encoding="utf-8")
    wipe = WIPE.read_text(encoding="utf-8")
    assert "palemon" not in mind.lower()
    for label, text in (("MIND.md", mind), ("WIPE.md", wipe)):
        low = _fold(text)
        for needle in _TWO_CATALOG_NEEDLES:
            assert needle.lower() in low, f"{label} missing {needle!r}"
        assert "do not copy" in low, label
        assert "third python" in low, label
        assert "grow" in low, label
        assert "cursor catalog" in low, label
        assert "grok bot" in low, label
        assert "grok-only" in low or "grok only" in low, label
        assert PRIVATE_GAME not in text


def test_cursor_mcp_json_taskboard_stdio_no_ak_no_leaks() -> None:
    raw = CURSOR_MCP.read_text(encoding="utf-8")
    data = json.loads(raw)
    servers = data.get("mcpServers") or {}
    assert "taskboard" in servers, data
    assert "ak" not in servers
    assert "agent-kanban" not in servers
    spec = servers["taskboard"]
    blob = json.dumps(data)
    low = blob.lower()
    joined = " ".join(
        str(x) for x in ([spec.get("command", "")] + list(spec.get("args") or []))
    )
    assert "run-mcp.sh" in joined or "run-mcp.sh" in blob
    assert "scripts/studio/taskboard" in blob
    assert "agent-kanban" not in low
    assert "agent kanban" not in low
    assert PRIVATE_GAME not in blob
    assert "ts.net" not in low
    assert "CURSOR_API_KEY" not in blob
    assert "TAILSCALE_AUTH_KEY" not in blob
    assert "/workspace/" + "pale" + "mon" not in low
    env = spec.get("env") or {}
    for key in env:
        upper = str(key).upper()
        assert "KEY" not in upper
        assert "SECRET" not in upper
        assert "TOKEN" not in upper


def test_run_mcp_execs_taskboard_stdio(tmp_path: Path) -> None:
    log = tmp_path / "tb.argv"
    fake = _write_exec(
        tmp_path / "bin" / "taskboard",
        "#!/bin/sh\n"
        f'printf "%s\\n" "$@" >> "{log}"\n'
        "exit 0\n",
    )
    state = tmp_path / "live-state"
    env = {
        "PATH": f"{fake.parent}:/usr/bin:/bin",
        "HOME": str(tmp_path / "home"),
        "GCS_ROOT": str(REPO),
        "GCS_A2A_STATE": str(state),
        "TASKBOARD_BIN": str(fake),
        "LC_ALL": "C",
        "TERM": "dumb",
    }
    proc = subprocess.run(
        ["bash", str(RUN_MCP)],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    recorded = log.read_text(encoding="utf-8")
    assert "--db" in recorded
    assert "mcp" in recorded
    db = state / "taskboard" / "taskboard.db"
    assert str(db) in recorded
    assert PRIVATE_GAME not in blob
    assert "CURSOR_API_KEY=" not in blob
    assert "TAILSCALE_AUTH_KEY=" not in blob


GITMODULES = REPO / ".gitmodules"
VENDOR_TB = REPO / "vendor" / "taskboard"
TASKBOARD_DOC = REPO / "docs" / "studio" / "TASKBOARD.md"
COMMON_SH = TASKBOARD_DIR / "common.sh"
SETUP_SH = REPO / "setup.sh"
PINNED_TASKBOARD_TAG = "v0.6.0"


def _elf_or_macho(path: Path) -> bool:
    head = path.read_bytes()[:4]
    return head == b"\x7fELF" or head[:4] == b"\xcf\xfa\xed\xfe" or head[:4] == b"\xfe\xed\xfa\xcf"


def test_taskboard_gitmodules_pins_v060_not_main() -> None:
    assert GITMODULES.is_file(), "missing .gitmodules"
    text = GITMODULES.read_text(encoding="utf-8")
    assert "vendor/taskboard" in text
    assert "tcarac/taskboard" in text
    assert PINNED_TASKBOARD_TAG in text
    assert "branch = main" not in text
    assert "branch = master" not in text
    proc = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-s", "--", "vendor/taskboard"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "160000" in proc.stdout, blob
    assert "vendor/taskboard" in proc.stdout


def test_taskboard_submodule_checkout_is_v060() -> None:
    assert VENDOR_TB.is_dir(), "missing vendor/taskboard"
    gitdir = VENDOR_TB / ".git"
    assert gitdir.exists(), "vendor/taskboard is not an initialized submodule"
    proc = subprocess.run(
        ["git", "-C", str(VENDOR_TB), "describe", "--tags", "--exact-match"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert proc.stdout.strip() == PINNED_TASKBOARD_TAG


def test_taskboard_submodule_has_no_compiled_binary_blob() -> None:
    assert VENDOR_TB.is_dir()
    for path in VENDOR_TB.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        if ".git" in path.parts:
            continue
        if _elf_or_macho(path):
            raise AssertionError(f"compiled binary blob in submodule: {path}")
        if path.name == "taskboard" and path.stat().st_mode & stat.S_IXUSR:
            # Source pin may contain scripts; ELF/Mach-O already rejected.
            head = path.read_bytes()[:2]
            assert head == b"#!" or head[:1] == b"{", f"unexpected binary {path}"


def test_docs_and_setup_init_taskboard_submodule() -> None:
    wipe = WIPE.read_text(encoding="utf-8")
    doc = TASKBOARD_DOC.read_text(encoding="utf-8")
    setup = SETUP_SH.read_text(encoding="utf-8")
    common = COMMON_SH.read_text(encoding="utf-8")
    for label, text in (("WIPE.md", wipe), ("TASKBOARD.md", doc)):
        assert "vendor/taskboard" in text, label
        assert "--recurse-submodules" in text, label
        assert "submodule update --init" in text, label
        assert PINNED_TASKBOARD_TAG in text, label
        assert PRIVATE_GAME not in text
    assert "submodule update --init" in setup
    assert "vendor/taskboard" in setup
    assert "vendor/taskboard" in common
    assert "agent-kanban" not in setup
    assert "ak start" not in setup


def test_gcs_taskboard_bin_prefers_submodule_prebuilt(tmp_path: Path) -> None:
    kit = tmp_path / "kit"
    pre = kit / "vendor" / "taskboard" / "taskboard"
    _write_exec(pre, "#!/bin/sh\nexit 0\n")
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path / "home"),
        "GCS_ROOT": str(kit),
        "LC_ALL": "C",
        "TERM": "dumb",
    }
    script = (
        "set -euo pipefail\n"
        f"source {COMMON_SH}\n"
        "gcs_taskboard_bin\n"
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
    assert str(pre.resolve()) in proc.stdout.strip() or str(pre) in proc.stdout
    assert PRIVATE_GAME not in blob

