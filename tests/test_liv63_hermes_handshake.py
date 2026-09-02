"""LIV-63 remaining: studio-mind handshake after grok plugin install --trust.

Unique --name gcs-liv63-hermes-handshake-beat1849. Executable binding for
tests/features/liv63_hermes_handshake.feature.

grok plugin install --trust copies plugins/studio-mind into seat GROK_HOME.
The copied server.py is off the repo tree. Stamp GROK_HOME/gcs-root so
imports resolve. Initialize is not shutdown: notifications/initialized
then tools/list must run on the same stdio pid.

Does not vendor Hermes. Does not land harvest #26/#28. Does not restack
cloud_list into mind.py. Does not twin leftover
gcs-liv63-hermes-remaining-beat1849. Does not remint ship-gate #117.

BDD: demonstrate, don't theatre. No LGTM without evidence.
"""
from __future__ import annotations

import importlib.util
import json
import os
import select
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
FEATURE = REPO / "tests" / "features" / "liv63_hermes_handshake.feature"
PLUGIN_DIR = REPO / "plugins" / "studio-mind"
SERVER = PLUGIN_DIR / "server.py"
MCP_JSON = PLUGIN_DIR / "mcp.json"
PLUGIN_JSON = PLUGIN_DIR / "plugin.json"
GCS_MCP = REPO / "scripts" / "mcp" / "gcs_mcp.py"
MIND_PY = REPO / "scripts" / "directors" / "mind.py"
SEAT_COMMON = REPO / "scripts" / "directors" / "seat-daemon-common.sh"
MIND_LOOP = REPO / "scripts" / "directors" / "seat-mind-loop.sh"
MIND_DOC = REPO / "docs" / "studio" / "MIND.md"
GITMODULES = REPO / ".gitmodules"
PRIVATE_GAME = "atebites-hub/" + "palemon"
TWIN_REMAINING_NAME = "gcs-liv63-hermes-remaining-beat1849"
THIS_NAME = "gcs-liv63-hermes-handshake-beat1849"

HARVEST_MARKERS = (
    "format_mail_turn",
    "filter_inbound_mail",
    "MAIL_MAX_CHARS",
    "mind/heartbeat",
    "defang",
    "mail envelope",
)
PR47_RESTACK = ("cloud_list", "cloud_followup", "cloud_result", "cloud_status")
SCENARIO_BINDINGS = {
    "Off-tree GROK_HOME copy reads gcs-root and stays open": (
        "test_off_tree_grok_home_copy_initialize_stays_open"
    ),
    "initialize is not shutdown": (
        "test_content_length_initialize_does_not_close_stdio"
    ),
    "NDJSON initialize without GCS_MCP_NDJSON still handshakes": (
        "test_ndjson_initialize_without_env_does_not_close"
    ),
    "plugin install stamps GROK_HOME/gcs-root": (
        "test_install_studio_mind_plugin_stamps_gcs_root"
    ),
}


def _gherkin_scenarios(text: str) -> list[str]:
    titles: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("Scenario:"):
            titles.append(stripped[len("Scenario:") :].strip())
    return titles


def _write_exec(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def _clean_env(tmp_path: Path, extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "HOME": str(tmp_path / "home"),
        "LANG": "C",
        "LC_ALL": "C",
        "TERM": "dumb",
        "PYTHONUNBUFFERED": "1",
    }
    (tmp_path / "home").mkdir(parents=True, exist_ok=True)
    if extra:
        env.update(extra)
    return env


def _spawn(argv: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        argv,
        cwd=str(cwd),
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )


def _reap(proc: subprocess.Popen[bytes]) -> bytes:
    if proc.poll() is None:
        proc.kill()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass
    try:
        err = proc.stderr.read() if proc.stderr is not None else b""
    except OSError:
        err = b""
    return err


def _write_frame(
    proc: subprocess.Popen[bytes], obj: dict[str, Any], *, ndjson: bool
) -> None:
    assert proc.stdin is not None
    blob = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    if ndjson:
        proc.stdin.write(blob + b"\n")
    else:
        header = f"Content-Length: {len(blob)}\r\n\r\n".encode("ascii")
        proc.stdin.write(header + blob)
    proc.stdin.flush()


def _read_exact(proc: subprocess.Popen[bytes], n: int, deadline: float) -> bytes:
    assert proc.stdout is not None
    buf = b""
    while len(buf) < n:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"body timeout have={len(buf)} want={n}")
        ready, _, _ = select.select([proc.stdout], [], [], remaining)
        if not ready:
            continue
        chunk = proc.stdout.read(n - len(buf))
        if not chunk:
            raise ConnectionError(
                f"eof reading body have={len(buf)} want={n} poll={proc.poll()}"
            )
        buf += chunk
    return buf


def _read_frame(proc: subprocess.Popen[bytes], timeout: float = 3.0) -> dict[str, Any]:
    """Read one MCP frame: Content-Length or a single NDJSON object line."""
    assert proc.stdout is not None
    deadline = time.monotonic() + timeout
    buf = b""
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            err = b""
            if proc.poll() is not None and proc.stderr is not None:
                err = proc.stderr.read()
            raise TimeoutError(
                f"handshake frame timeout poll={proc.poll()} buf={buf[:200]!r} err={err[:800]!r}"
            )
        ready, _, _ = select.select([proc.stdout], [], [], remaining)
        if not ready:
            continue
        byte = proc.stdout.read(1)
        if not byte:
            err = b""
            if proc.poll() is not None and proc.stderr is not None:
                err = proc.stderr.read()
            raise ConnectionError(
                f"stdio closed during handshake poll={proc.poll()} buf={buf[:200]!r} err={err[:1200]!r}"
            )
        buf += byte
        if buf.lstrip().startswith(b"{") and buf.endswith(b"\n"):
            return json.loads(buf.decode("utf-8"))
        if buf.endswith(b"\r\n\r\n") or (
            buf.endswith(b"\n\n") and b"content-length:" in buf.lower()
        ):
            break
    headers_map: dict[str, str] = {}
    for raw in buf.splitlines():
        line = raw.decode("utf-8", errors="replace").strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers_map[key.strip().lower()] = value.strip()
    length = int(headers_map.get("content-length") or "0")
    body = _read_exact(proc, length, deadline) if length else b"{}"
    return json.loads(body.decode("utf-8"))


def _assert_alive(proc: subprocess.Popen[bytes]) -> None:
    rc = proc.poll()
    if rc is not None:
        err = b""
        if proc.stderr is not None:
            err = proc.stderr.read()
        raise AssertionError(
            f"MCP stdio closed after initialize rc={rc} stderr={err[:1200]!r}"
        )


def _initialize_msg(req_id: int = 1) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "gcs-test-beat1849", "version": "1.0.0"},
        },
    }


def _assert_initialize_result(reply: dict[str, Any], *, server_name: str) -> None:
    assert reply.get("jsonrpc") == "2.0"
    assert "error" not in reply, reply
    result = reply["result"]
    assert result["protocolVersion"]
    assert result["serverInfo"]["name"] == server_name
    assert "tools" in result.get("capabilities", {})


def test_bdd_feature_is_the_remaining_liv63_handshake_example() -> None:
    assert FEATURE.is_file(), FEATURE
    text = FEATURE.read_text(encoding="utf-8")
    assert text.startswith(
        "Feature: studio-mind handshake after grok plugin install --trust"
    )
    low = text.lower()
    for needle in (
        "liv-63",
        "handshake",
        "gcs-root",
        "plugin install",
        "--trust",
        "initialize",
        "beat1849",
        "#26",
        "#28",
        "cloud_list",
        "nousresearch/hermes-agent",
        THIS_NAME,
        TWIN_REMAINING_NAME,
        "don't theatre",
        "bot cloudagent",
    ):
        assert needle in low, needle
    assert PRIVATE_GAME not in text
    titles = _gherkin_scenarios(text)
    assert titles == list(SCENARIO_BINDINGS)
    defined = set(globals())
    for title, fn_name in SCENARIO_BINDINGS.items():
        assert fn_name in defined, (title, fn_name)


def test_do_not_twin_remaining_beat1849_or_vendor_hermes() -> None:
    blob = FEATURE.read_text(encoding="utf-8") + "\n" + Path(__file__).read_text(
        encoding="utf-8"
    )
    assert THIS_NAME in blob
    assert TWIN_REMAINING_NAME in blob
    assert "do not twin" in blob.lower()
    assert not (REPO / "vendor" / "hermes-agent").exists()
    assert not (REPO / "vendor" / "hermes").exists()
    modules = GITMODULES.read_text(encoding="utf-8")
    assert "hermes-agent" not in modules
    assert "tcarac/taskboard" in modules
    mind = MIND_PY.read_text(encoding="utf-8")
    for marker in HARVEST_MARKERS:
        assert marker not in mind, marker
    assert "message_agent.py" not in mind
    assert "cloud_list" not in mind
    assert "cloud_followup" not in mind
    spec = importlib.util.spec_from_file_location("gcs_liv63_handshake_mind", MIND_PY)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    plugins = set(mod.PLUGINS)
    assert plugins == {"ticket", "a2a_send", "cloud_launch"}
    for restack in PR47_RESTACK:
        assert restack not in plugins, restack
    assert THIS_NAME != TWIN_REMAINING_NAME


def test_studio_mind_manifest_is_plugin_install_not_chrome_devtools() -> None:
    plugin = json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))
    mcp = json.loads(MCP_JSON.read_text(encoding="utf-8"))
    assert plugin["name"] == "studio-mind"
    servers = mcp["mcpServers"]
    assert "studio-mind" in servers
    assert "chrome-devtools" not in json.dumps(mcp)
    spec = servers["studio-mind"]
    args = spec.get("args") or []
    assert "server.py" in args
    assert "-u" in args, "copied MCP must run python3 -u so initialize is not buffered"
    loop = MIND_LOOP.read_text(encoding="utf-8")
    common = SEAT_COMMON.read_text(encoding="utf-8")
    assert "install_studio_mind_plugin" in loop
    assert "plugin install" in common
    assert "--trust" in common
    assert "studio-mind" in common
    assert "gcs-root" in common
    assert "chrome-devtools" not in loop
    doc = MIND_DOC.read_text(encoding="utf-8")
    assert "plugin install" in doc
    assert "studio-mind" in doc
    assert "gcs-root" in doc
    assert "initialize" in doc.lower()
    assert "fast=false" in doc
    assert "grok-4.6" in doc
    assert "xhigh" in doc
    assert "cloud_list" not in MIND_PY.read_text(encoding="utf-8")


def test_content_length_initialize_does_not_close_stdio(tmp_path: Path) -> None:
    env = _clean_env(tmp_path, {"GCS_ROOT": str(REPO)})
    proc = _spawn(["python3", "-u", str(SERVER)], cwd=REPO, env=env)
    try:
        _write_frame(proc, _initialize_msg(), ndjson=False)
        reply = _read_frame(proc)
        _assert_initialize_result(reply, server_name="studio-mind")
        _assert_alive(proc)
        _write_frame(
            proc,
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            ndjson=False,
        )
        time.sleep(0.15)
        _assert_alive(proc)
        assert proc.stdout is not None
        ready, _, _ = select.select([proc.stdout], [], [], 0.05)
        assert ready == [], "initialized notification must not emit a JSON-RPC reply"
        _write_frame(
            proc,
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            ndjson=False,
        )
        listed = _read_frame(proc)
        names = {t["name"] for t in listed["result"]["tools"]}
        assert names == {"ticket", "a2a_send", "cloud_launch"}
        assert "chrome-devtools" not in names
        assert "cloud_list" not in names
        _assert_alive(proc)
        _write_frame(proc, {"jsonrpc": "2.0", "id": 3, "method": "ping"}, ndjson=False)
        ping = _read_frame(proc)
        assert ping.get("id") == 3
        _assert_alive(proc)
    finally:
        _reap(proc)


def test_ndjson_initialize_without_env_does_not_close(tmp_path: Path) -> None:
    """Grok may speak NDJSON. Default framing is Content-Length; still handshake."""
    env = _clean_env(tmp_path, {"GCS_ROOT": str(REPO)})
    assert "GCS_MCP_NDJSON" not in env
    proc = _spawn(["python3", "-u", str(SERVER)], cwd=REPO, env=env)
    try:
        _write_frame(proc, _initialize_msg(), ndjson=True)
        reply = _read_frame(proc, timeout=2.5)
        _assert_initialize_result(reply, server_name="studio-mind")
        _assert_alive(proc)
        _write_frame(
            proc,
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            ndjson=True,
        )
        time.sleep(0.1)
        _assert_alive(proc)
        _write_frame(
            proc,
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            ndjson=True,
        )
        listed = _read_frame(proc, timeout=2.5)
        names = {t["name"] for t in listed["result"]["tools"]}
        assert names == {"ticket", "a2a_send", "cloud_launch"}
        assert "cloud_list" not in names
        _assert_alive(proc)
    finally:
        _reap(proc)


def test_off_tree_grok_home_copy_initialize_stays_open(tmp_path: Path) -> None:
    """grok plugin install copies studio-mind off the repo tree into GROK_HOME."""
    grok_home = tmp_path / "grok-home"
    dest = grok_home / "plugins" / "studio-mind-deadbeef"
    shutil.copytree(PLUGIN_DIR, dest)
    (grok_home / "gcs-root").write_text(str(REPO) + "\n", encoding="utf-8")
    env = _clean_env(tmp_path, {"GROK_HOME": str(grok_home)})
    assert "GCS_ROOT" not in env
    proc = _spawn(["python3", "-u", str(dest / "server.py")], cwd=dest, env=env)
    try:
        _write_frame(proc, _initialize_msg(), ndjson=False)
        reply = _read_frame(proc)
        _assert_initialize_result(reply, server_name="studio-mind")
        _assert_alive(proc)
        _write_frame(
            proc,
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            ndjson=False,
        )
        listed = _read_frame(proc)
        names = {t["name"] for t in listed["result"]["tools"]}
        assert names == {"ticket", "a2a_send", "cloud_launch"}
        assert "cloud_list" not in names
        _assert_alive(proc)
    finally:
        _reap(proc)


def test_install_studio_mind_plugin_stamps_gcs_root(tmp_path: Path) -> None:
    log = tmp_path / "plugin.argv"
    grok = _write_exec(
        tmp_path / "fake-bin" / "grok",
        "#!/bin/sh\n"
        f'printf "%s\\n" "$@" >> "{log}"\n'
        'printf "GROK_HOME=%s\\n" "$GROK_HOME" >> '
        f'"{log}.env"\n'
        "exit 0\n",
    )
    grok_home = tmp_path / "grok-home"
    env = _clean_env(
        tmp_path,
        {
            "PATH": f"{grok.parent}:/usr/bin:/bin",
            "GCS_ROOT": str(REPO),
            "GCS_A2A_STATE": str(tmp_path / "a2a-state"),
            "GROK_HOME": str(grok_home),
            "TASKBOARD_BIN": str(
                _write_exec(tmp_path / "host-bin" / "taskboard", "#!/bin/sh\nexit 0\n")
            ),
        },
    )
    script = r"""
set -euo pipefail
source scripts/directors/seat-daemon-common.sh
install_studio_mind_plugin floor
"""
    proc = subprocess.run(
        ["bash", "-c", script],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "MIND_PLUGIN_OK" in blob
    stamp = grok_home / "gcs-root"
    assert stamp.is_file(), blob
    assert stamp.read_text(encoding="utf-8").strip() == str(REPO)
    argv = log.read_text(encoding="utf-8")
    assert "plugin" in argv and "install" in argv
    assert "--trust" in argv
    assert "studio-mind" in argv
    assert "chrome-devtools" not in argv


def test_install_stamps_gcs_root_even_when_grok_is_missing(tmp_path: Path) -> None:
    """Handshake pointer is independent of grok being on PATH."""
    grok_home = tmp_path / "grok-home"
    env = _clean_env(
        tmp_path,
        {
            "PATH": "/usr/bin:/bin",
            "GCS_ROOT": str(REPO),
            "GCS_A2A_STATE": str(tmp_path / "a2a-state"),
            "GROK_HOME": str(grok_home),
        },
    )
    script = r"""
set -euo pipefail
source scripts/directors/seat-daemon-common.sh
install_studio_mind_plugin floor
"""
    proc = subprocess.run(
        ["bash", "-c", script],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "MIND_PLUGIN_SKIP" in blob
    assert "no-grok" in blob or "reason=no-grok" in blob
    stamp = grok_home / "gcs-root"
    assert stamp.is_file(), blob
    assert stamp.read_text(encoding="utf-8").strip() == str(REPO)


def test_gcs_mcp_content_length_initialize_does_not_close(tmp_path: Path) -> None:
    env = _clean_env(tmp_path, {"GCS_ROOT": str(REPO)})
    proc = _spawn(
        ["python3", "-u", str(GCS_MCP), "--plane", "a2a"],
        cwd=REPO,
        env=env,
    )
    try:
        _write_frame(proc, _initialize_msg(), ndjson=False)
        reply = _read_frame(proc)
        _assert_initialize_result(reply, server_name="gcs-mcp")
        _assert_alive(proc)
        _write_frame(
            proc,
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            ndjson=False,
        )
        time.sleep(0.1)
        _assert_alive(proc)
        _write_frame(
            proc,
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            ndjson=False,
        )
        listed = _read_frame(proc)
        names = {t["name"] for t in listed["result"]["tools"]}
        assert names == {"a2a_list_seats", "a2a_send"}
        _assert_alive(proc)
    finally:
        _reap(proc)


def test_gcs_mcp_keeps_cloud_list_on_cloud_plane() -> None:
    """Handshake must not restack/remove Extra High cloud_list from gcs_mcp."""
    src = GCS_MCP.read_text(encoding="utf-8")
    assert "cloud_list" in src
    assert "list_helper" in src
    env = {**os.environ, "GCS_ROOT": str(REPO), "GCS_MCP_NDJSON": "1"}
    msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    proc = subprocess.run(
        ["python3", str(GCS_MCP), "--plane", "cloud", "--ndjson"],
        cwd=str(REPO),
        input=json.dumps(msg) + "\n",
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    reply = json.loads(proc.stdout.splitlines()[0])
    names = {t["name"] for t in reply["result"]["tools"]}
    assert "cloud_list" in names
    assert "cloud_launch" in names
