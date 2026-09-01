"""Ship-gate FAT: bus / recover / doctor never reconnect Agent Kanban.

Runtime evidence (honey-pot `ak`/`ama` on PATH + PALEMON_AK_BRIDGE refuse).
Board stays tcarac/taskboard. Do not reintroduce scripts/studio/agent-kanban.

Distinct from wipe-kit GCS #94 and seat taskboard stdio MCP GCS #100.
Never Bot CloudAgent. Extra High pin stays grok-4.6 xhigh fast=false.
Palemon Linear is Living Sky (LIV), not Black Swan.
"""
from __future__ import annotations

import json
import re
import socket
import stat
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BUS = REPO / "scripts" / "a2a" / "start-studio-bus.sh"
RECOVER = REPO / "recover.sh"
DOCTOR = REPO / "doctor.sh"
LAUNCH = REPO / "scripts" / "launch-cloud-extra-high.sh"
REGISTRY = REPO / "docs" / "a2a" / "registry.json"
FEATURE = REPO / "tests" / "bdd" / "no_ak_reconnect.feature"
AK_TREE = REPO / "scripts" / "studio" / "agent-kanban"
NO_AK = REPO / "scripts" / "studio" / "no-ak.sh"

FAKE_KEY = "test-cursor-api-key-no-ak-not-leaked"
PRIVATE_GAME = "atebites-hub/" + "palemon"
_INVOKE_AK = re.compile(
    r"(?:^|[\s;&|`(])(?:ak|ama)\s+(start|create|up|serve|connect)\b"
)


def _write_exec(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _noncomment(src: str) -> str:
    return "\n".join(
        line for line in src.splitlines() if line.strip() and not line.strip().startswith("#")
    )


def _honeypot(tmp_path: Path) -> tuple[Path, Path]:
    log = tmp_path / "ak-honeypot.log"
    log.write_text("", encoding="utf-8")
    bindir = tmp_path / "honeypot-bin"
    script = (
        "#!/bin/sh\n"
        f'printf "%s\\n" "$0 $*" >> "{log}"\n'
        "exit 0\n"
    )
    for name in ("ak", "ama", "agent-kanban"):
        _write_exec(bindir / name, script)
    return bindir, log


def _base_env(
    tmp_path: Path,
    state: Path,
    *,
    extra_path: str = "",
) -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    path = extra_path if extra_path else "/usr/bin:/bin"
    return {
        "PATH": path,
        "HOME": str(home),
        "GCS_ROOT": str(REPO),
        "GCS_A2A_STATE": str(state),
        "GCS_MIND_SEATS": "",
        "GCS_START_SEAT_DAEMONS": "0",
        "GCS_BOT_BIND_OPTIONAL": "1",
        "LC_ALL": "C",
        "TERM": "dumb",
        "CURSOR_API_KEY": FAKE_KEY,
    }


def _run(
    script: Path,
    args: list[str],
    env: dict[str, str],
    *,
    timeout: int = 25,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(script), *args],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _stop_bus(env: dict[str, str]) -> None:
    subprocess.run(
        ["bash", str(BUS), "stop"],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )


def _assert_secret_free(blob: str) -> None:
    assert FAKE_KEY not in blob
    assert "CURSOR_API_KEY=" not in blob
    assert PRIVATE_GAME not in blob


def _assert_no_ak_exec(log: Path) -> None:
    text = log.read_text(encoding="utf-8") if log.is_file() else ""
    assert text.strip() == "", text


def test_feature_names_bus_recover_doctor_and_living_sky() -> None:
    text = FEATURE.read_text(encoding="utf-8")
    low = text.lower()
    assert FEATURE.is_file()
    assert "start-studio-bus.sh" in text
    assert "recover.sh" in text
    assert "doctor.sh" in text
    assert "tcarac/taskboard" in low
    assert "agent kanban" in low
    assert "palemon_ak_bridge" in low
    assert "living sky" in low
    assert "black swan" in low
    assert "never bot cloudagent" in low
    assert "grok-4.6" in text
    assert "fast=false" in text
    assert "#94" in text
    assert "#100" in text


def test_agent_kanban_tree_stays_absent() -> None:
    assert not AK_TREE.exists()
    assert not (REPO / "docs" / "studio" / "AGENT_KANBAN.md").exists()


def test_scripts_source_refuse_helper_and_do_not_invoke_ak() -> None:
    helper = NO_AK.read_text(encoding="utf-8")
    assert "gcs_refuse_agent_kanban" in helper
    assert "PALEMON_AK_BRIDGE" in helper
    assert "agent-kanban" in helper
    assert "tcarac/taskboard" in helper or "taskboard" in helper.lower()
    for path in (BUS, RECOVER, DOCTOR):
        text = path.read_text(encoding="utf-8")
        assert "no-ak.sh" in text, path.name
        assert "gcs_refuse_agent_kanban" in text, path.name
        body = _noncomment(text)
        assert _INVOKE_AK.search(body) is None, path.name
        assert "mint-floor-ops-worker" not in text
        assert "AMA-401" not in text
        assert "ak create task" not in text
    recover = RECOVER.read_text(encoding="utf-8")
    doctor = DOCTOR.read_text(encoding="utf-8")
    assert "start --daemons" not in recover or "NO --daemons" in recover
    assert "launch-cloud-extra-high" not in recover
    assert "bash \"$ROOT/scripts/launch-cloud-extra-high.sh\"" not in doctor
    assert "CLOUD_LAUNCH" not in doctor


def test_bus_start_does_not_exec_ak_when_honeypot_on_path(tmp_path: Path) -> None:
    bindir, log = _honeypot(tmp_path)
    state = tmp_path / "a2a-state"
    state.mkdir()
    env = _base_env(tmp_path, state, extra_path=f"{bindir}:/usr/bin:/bin")
    env["GCS_A2A_PORT"] = str(_free_port())
    try:
        proc = _run(BUS, ["start"], env)
        blob = proc.stdout + proc.stderr
        assert proc.returncode == 0, blob
        assert "STUDIO_BUS_READY" in blob
        assert "AK_REFUSE" not in blob
        _assert_secret_free(blob)
        _assert_no_ak_exec(log)
        assert not AK_TREE.exists()
        assert "ak start" not in blob.lower() or "never" in blob.lower()
    finally:
        _stop_bus(env)


def test_bus_start_refuses_palemon_ak_bridge(tmp_path: Path) -> None:
    bindir, log = _honeypot(tmp_path)
    state = tmp_path / "a2a-state"
    state.mkdir()
    env = _base_env(tmp_path, state, extra_path=f"{bindir}:/usr/bin:/bin")
    env["PALEMON_AK_BRIDGE"] = "1"
    env["GCS_A2A_PORT"] = str(_free_port())
    try:
        proc = _run(BUS, ["start"], env)
        blob = proc.stdout + proc.stderr
        assert proc.returncode != 0, blob
        assert "AK_REFUSE" in blob
        assert "Agent Kanban" in blob or "agent kanban" in blob.lower()
        assert "STUDIO_BUS_READY" not in blob
        assert "STUDIO_BUS_HUB_START" not in blob
        _assert_secret_free(blob)
        _assert_no_ak_exec(log)
        assert not (state / "hub.pid").is_file()
    finally:
        _stop_bus(env)


def test_bus_start_refuses_studio_env_ak_bridge(tmp_path: Path) -> None:
    bindir, log = _honeypot(tmp_path)
    state = tmp_path / "a2a-state"
    state.mkdir()
    (state / "studio.env").write_text("PALEMON_AK_BRIDGE=1\nGCS_MIND_SEATS=\n", encoding="utf-8")
    env = _base_env(tmp_path, state, extra_path=f"{bindir}:/usr/bin:/bin")
    env.pop("PALEMON_AK_BRIDGE", None)
    env["GCS_A2A_PORT"] = str(_free_port())
    try:
        proc = _run(BUS, ["start"], env)
        blob = proc.stdout + proc.stderr
        assert proc.returncode != 0, blob
        assert "AK_REFUSE" in blob
        assert "STUDIO_BUS_READY" not in blob
        _assert_no_ak_exec(log)
    finally:
        _stop_bus(env)


def test_bus_help_works_when_bridge_on(tmp_path: Path) -> None:
    env = _base_env(tmp_path, tmp_path / "a2a-state")
    env["PALEMON_AK_BRIDGE"] = "1"
    proc = _run(BUS, ["--help"], env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "Usage" in blob or "start-studio-bus.sh" in blob
    _assert_secret_free(blob)


def test_recover_does_not_exec_ak_when_honeypot_on_path(tmp_path: Path) -> None:
    bindir, log = _honeypot(tmp_path)
    state = tmp_path / "a2a-state"
    state.mkdir()
    env = _base_env(tmp_path, state, extra_path=f"{bindir}:/usr/bin:/bin")
    env["GCS_RECOVER_DRY_RUN"] = "1"
    env["GCS_A2A_PORT"] = str(_free_port())
    env["GCS_TASKBOARD_UI_PORT"] = str(_free_port())
    env["GCS_TASKBOARD_MCP_PORT"] = str(_free_port())
    proc = _run(RECOVER, [], env)
    blob = proc.stdout + proc.stderr
    # recover.sh prints RECOVER_OK then re-runs health_check (exit 0/1/2).
    assert "RECOVER_OK" in blob, blob
    assert "start-studio-bus.sh start --daemons" not in blob
    assert "start-taskboard.sh" in blob or "mcp-http.sh" in blob or "start-studio-bus.sh" in blob
    _assert_secret_free(blob)
    _assert_no_ak_exec(log)
    assert not AK_TREE.exists()


def test_recover_refuses_palemon_ak_bridge(tmp_path: Path) -> None:
    bindir, log = _honeypot(tmp_path)
    state = tmp_path / "a2a-state"
    state.mkdir()
    env = _base_env(tmp_path, state, extra_path=f"{bindir}:/usr/bin:/bin")
    env["PALEMON_AK_BRIDGE"] = "1"
    env["GCS_RECOVER_DRY_RUN"] = "1"
    env["GCS_A2A_PORT"] = str(_free_port())
    proc = _run(RECOVER, [], env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode != 0, blob
    assert "AK_REFUSE" in blob
    assert "RECOVER_OK" not in blob
    _assert_secret_free(blob)
    _assert_no_ak_exec(log)


def test_recover_help_works_when_bridge_on(tmp_path: Path) -> None:
    env = _base_env(tmp_path, tmp_path / "a2a-state")
    env["PALEMON_AK_BRIDGE"] = "1"
    proc = _run(RECOVER, ["--help"], env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "Usage" in blob or "recover.sh" in blob
    _assert_secret_free(blob)


def test_doctor_does_not_exec_ak_when_honeypot_on_path(tmp_path: Path) -> None:
    bindir, log = _honeypot(tmp_path)
    state = tmp_path / "a2a-state"
    state.mkdir()
    env = _base_env(tmp_path, state, extra_path=f"{bindir}:/usr/bin:/bin")
    proc = _run(DOCTOR, [], env, timeout=40)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "doctor: OK" in blob
    _assert_secret_free(blob)
    _assert_no_ak_exec(log)
    assert not AK_TREE.exists()


def test_doctor_refuses_palemon_ak_bridge(tmp_path: Path) -> None:
    bindir, log = _honeypot(tmp_path)
    state = tmp_path / "a2a-state"
    state.mkdir()
    env = _base_env(tmp_path, state, extra_path=f"{bindir}:/usr/bin:/bin")
    env["PALEMON_AK_BRIDGE"] = "1"
    proc = _run(DOCTOR, [], env, timeout=40)
    blob = proc.stdout + proc.stderr
    assert proc.returncode != 0, blob
    assert "AK_REFUSE" in blob or "Agent Kanban" in blob
    assert "doctor: FAIL" in blob or "ERR" in blob
    _assert_secret_free(blob)
    _assert_no_ak_exec(log)


def test_doctor_fails_when_gcs_root_agent_kanban_tree_reappears(tmp_path: Path) -> None:
    bindir, log = _honeypot(tmp_path)
    state = tmp_path / "a2a-state"
    state.mkdir()
    planted = tmp_path / "foreign-root" / "scripts" / "studio" / "agent-kanban"
    planted.mkdir(parents=True)
    (planted / "mint-floor-ops-worker.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    env = _base_env(tmp_path, state, extra_path=f"{bindir}:/usr/bin:/bin")
    env["GCS_ROOT"] = str(tmp_path / "foreign-root")
    proc = _run(DOCTOR, [], env, timeout=40)
    blob = proc.stdout + proc.stderr
    assert proc.returncode != 0, blob
    assert "Agent Kanban" in blob or "agent-kanban" in blob or "AK_REFUSE" in blob
    assert not AK_TREE.exists()
    _assert_no_ak_exec(log)


def test_board_stays_taskboard_never_bot_cloudagent() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    skip = {str(s) for s in registry.get("skipSeats") or []}
    assert "orchestrator" in skip
    assert "donald" in skip
    for path in (BUS, RECOVER, DOCTOR):
        text = path.read_text(encoding="utf-8").lower()
        assert "tcarac/taskboard" in text or "taskboard" in text
        assert "bot cloudagent" not in text
    recover = RECOVER.read_text(encoding="utf-8")
    assert "start-taskboard.sh" in recover
    assert "mcp-http.sh" in recover
    launch = LAUNCH.read_text(encoding="utf-8")
    assert "grok-4.6" in launch
    assert "xhigh" in launch
    assert "fast=false" in launch
    assert '"id": "grok-4.6"' in launch or "id\": \"grok-4.6\"" in launch
