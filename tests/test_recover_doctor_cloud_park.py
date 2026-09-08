"""recover.sh / doctor honor CLOUD_API_PARKED: no Extra High spawn.

Distinct from scripts/launch-cloud-extra-high.sh park guard (other writer).
PAL-25 stays studio-ops: bot-bridge stays off unless GCS_BOT_BRIDGE=1.
Never Bot CloudAgent. Never print credentials. Living Sky (LIV) only.
"""
from __future__ import annotations

import os
import signal
import socket
import stat
import subprocess
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
RECOVER = REPO / "recover.sh"
DOCTOR = REPO / "doctor.sh"
LAUNCH = REPO / "scripts" / "launch-cloud-extra-high.sh"
HELPER = REPO / "scripts" / "studio" / "cloud_api_park.sh"
FEATURE = REPO / "tests" / "features" / "recover_doctor_cloud_park.feature"
WIPE = REPO / "docs" / "studio" / "WIPE.md"
AGENTS = REPO / "AGENTS.md"
STUDIO_ENV_EXAMPLE = REPO / "studio.env.example"
BUS = REPO / "scripts" / "a2a" / "start-studio-bus.sh"

FAKE_KEY = "test-cursor-api-key-recover-doctor-park-not-leaked"
EXAMPLE_REPO = "https://github.com/example/control-plane"
PRIVATE_GAME = "atebites-hub/" + "palemon"
BOT_CLOUDAGENT = "Bot" + " CloudAgent"
PARK_TOKEN = "RECOVER_CLOUD_PARKED"


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


def _write_exec(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def _honeypot(tmp_path: Path) -> tuple[Path, Path]:
    log = tmp_path / "extra-high-honeypot.log"
    log.write_text("", encoding="utf-8")
    bindir = tmp_path / "extra-high-honeypot-bin"
    script = (
        "#!/bin/sh\n"
        f'printf "%s\\n" "$0 $*" >> "{log}"\n'
        "echo CLOUD_LAUNCH_OK\n"
        "exit 0\n"
    )
    for name in ("launch-cloud-extra-high.sh", "cloud_launch", "agent"):
        _write_exec(bindir / name, script)
    return bindir, log


def _drop_park_env(env: dict[str, str]) -> dict[str, str]:
    env.pop("CLOUD_API_PARKED", None)
    return env


def _recover_env(tmp_path: Path, state: Path, *, extra_path: str = "") -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    path = extra_path if extra_path else "/usr/bin:/bin"
    env = {
        "PATH": path,
        "HOME": str(home),
        "GCS_ROOT": str(REPO),
        "GCS_A2A_STATE": str(state),
        "GCS_MIND_SEATS": "",
        "GCS_BOT_BIND_OPTIONAL": "1",
        "GCS_START_SEAT_DAEMONS": "0",
        "GCS_RECOVER_DRY_RUN": "1",
        "LC_ALL": "C",
        "TERM": "dumb",
        "CURSOR_API_KEY": FAKE_KEY,
        "GCS_A2A_PORT": str(_free_port()),
        "GCS_TASKBOARD_UI_PORT": str(_free_port()),
        "GCS_TASKBOARD_MCP_PORT": str(_free_port()),
    }
    return _drop_park_env(env)


def _doctor_env(tmp_path: Path, *, extra_path: str = "", **extra: str) -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    drop = {
        "CURSOR_API_KEY",
        "GCS_CLOUD_REPO",
        "CLOUD_REPO_URL",
        "CURSOR_CLOUD_REPO",
        "CURSOR_AGENT_ENV",
        "CLOUD_API_PARKED",
    }
    env = {k: v for k, v in os.environ.items() if k not in drop}
    path = extra_path if extra_path else os.environ.get("PATH", "/usr/bin:/bin")
    env.update(
        {
            "HOME": str(home),
            "GCS_ROOT": str(REPO),
            "GCS_A2A_STATE": str(tmp_path / "a2a-state"),
            "GCS_BOT_BIND_OPTIONAL": "1",
            "LC_ALL": "C",
            "TERM": "dumb",
            "PATH": path,
            "GCS_CLOUD_REPO": EXAMPLE_REPO,
            "CURSOR_API_KEY": FAKE_KEY,
        }
    )
    env.update(extra)
    return env


def _assert_secret_free(blob: str) -> None:
    assert FAKE_KEY not in blob
    assert "CURSOR_API_KEY=" not in blob
    assert PRIVATE_GAME not in blob
    assert BOT_CLOUDAGENT not in blob


def _assert_honeypot_idle(log: Path) -> None:
    text = log.read_text(encoding="utf-8") if log.is_file() else ""
    assert text.strip() == "", text


def _source_parked(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "bash",
            "-c",
            "set -euo pipefail; "
            f'source "{HELPER}"; '
            "if gcs_cloud_api_parked; then echo PARKED=1; else echo PARKED=0; fi",
        ],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_feature_binds_recover_doctor_park_not_launch_slice() -> None:
    text = FEATURE.read_text(encoding="utf-8")
    fold = " ".join(text.lower().split())
    assert FEATURE.is_file()
    assert "cloud_api_parked" in fold
    assert "recover.sh" in text
    assert "doctor.sh" in text
    assert "launch-cloud-extra-high.sh" in text
    assert "distinct" in fold
    assert "gcs_bot_bridge" in fold
    assert "bot-bridge" in fold
    assert "never bot cloudagent" in fold
    assert "RECOVER_CLOUD_PARKED" in text
    assert "STUDIO_BUS_BOT_BRIDGE_SKIP" in text
    assert "STUDIO_BUS_BOT_BRIDGE_START" in text
    assert "demonstrate" in fold and "theatre" in fold


def test_helper_and_scripts_exist_and_stay_off_the_launcher() -> None:
    assert HELPER.is_file(), "missing scripts/studio/cloud_api_park.sh"
    helper = HELPER.read_text(encoding="utf-8")
    recover = RECOVER.read_text(encoding="utf-8")
    doctor = DOCTOR.read_text(encoding="utf-8")
    launch = LAUNCH.read_text(encoding="utf-8")
    assert "gcs_cloud_api_parked" in helper
    assert "CLOUD_API_PARKED" in helper
    assert "cloud_api_park.sh" in recover
    assert "cloud_api_park.sh" in doctor
    assert "gcs_cloud_api_parked" in recover
    assert "gcs_cloud_api_parked" in doctor
    assert PARK_TOKEN in recover
    assert "CLOUD_API_PARKED" in recover
    assert "CLOUD_API_PARKED" in doctor
    assert "launch-cloud-extra-high" not in recover
    assert "CLOUD_LAUNCH" not in doctor
    assert "cloud_api_park.sh" not in launch
    assert "gcs_cloud_api_parked" not in launch
    invoked = [
        line.strip()
        for line in doctor.splitlines()
        if "launch-cloud-extra-high.sh" in line and not line.strip().startswith("#")
    ]
    for line in invoked:
        assert not line.startswith("bash ")
        assert "bash \"$ROOT/scripts/launch-cloud-extra-high.sh\"" not in line


def test_helper_env_1_is_parked_zero_and_unset_are_not(tmp_path: Path) -> None:
    state = tmp_path / "a2a-state"
    state.mkdir()
    env = _recover_env(tmp_path, state)
    proc = _source_parked(env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "PARKED=0" in blob, blob

    env["CLOUD_API_PARKED"] = "0"
    proc = _source_parked(env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "PARKED=0" in blob, blob

    env["CLOUD_API_PARKED"] = "1"
    proc = _source_parked(env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "PARKED=1" in blob, blob


def test_helper_honors_state_marker_and_studio_env(tmp_path: Path) -> None:
    state = tmp_path / "a2a-state"
    state.mkdir()
    env = _recover_env(tmp_path, state)
    marker = state / "CLOUD_API_PARKED"
    marker.write_text("1\n", encoding="utf-8")
    proc = _source_parked(env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "PARKED=1" in blob, blob

    marker.write_text("0\n", encoding="utf-8")
    proc = _source_parked(env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "PARKED=0" in blob, blob

    marker.unlink()
    (state / "studio.env").write_text("CLOUD_API_PARKED=1\n", encoding="utf-8")
    proc = _source_parked(env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "PARKED=1" in blob, blob


def test_recover_help_names_park_and_bot_bridge() -> None:
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": "/tmp",
        "GCS_ROOT": str(REPO),
        "LC_ALL": "C",
        "TERM": "dumb",
    }
    proc = _run(RECOVER, ["--help"], env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "CLOUD_API_PARKED" in blob
    assert "GCS_BOT_BRIDGE" in blob
    assert "Extra High" in blob
    assert FAKE_KEY not in blob
    assert "launch-cloud-extra-high" not in blob


@pytest.mark.parametrize("parked", ["1", "true", "yes"], ids=["one", "true", "yes"])
def test_recover_parked_prints_token_and_does_not_spawn(
    tmp_path: Path, parked: str
) -> None:
    bindir, log = _honeypot(tmp_path)
    state = tmp_path / "a2a-state"
    state.mkdir()
    env = _recover_env(tmp_path, state, extra_path=f"{bindir}:/usr/bin:/bin")
    env["CLOUD_API_PARKED"] = parked
    proc = _run(RECOVER, [], env)
    blob = proc.stdout + proc.stderr
    assert PARK_TOKEN in blob, blob
    assert "reason=CLOUD_API_PARKED" in blob, blob
    assert "RECOVER_OK" in blob, blob
    assert "CLOUD_LAUNCH_OK" not in blob
    assert "STUDIO_BUS_BOT_BRIDGE_START" not in blob
    _assert_honeypot_idle(log)
    _assert_secret_free(blob)
    dry = "\n".join(line for line in blob.splitlines() if line.startswith("RECOVER_DRY"))
    assert "launch-cloud-extra-high" not in dry
    assert "cloud_launch" not in dry


def test_recover_unparked_does_not_print_park_token(tmp_path: Path) -> None:
    state = tmp_path / "a2a-state"
    state.mkdir()
    env = _recover_env(tmp_path, state)
    proc = _run(RECOVER, [], env)
    blob = proc.stdout + proc.stderr
    assert PARK_TOKEN not in blob, blob
    assert "RECOVER_OK" in blob, blob


def test_recover_parked_via_state_marker(tmp_path: Path) -> None:
    bindir, log = _honeypot(tmp_path)
    state = tmp_path / "a2a-state"
    state.mkdir()
    (state / "CLOUD_API_PARKED").write_text("1\n", encoding="utf-8")
    env = _recover_env(tmp_path, state, extra_path=f"{bindir}:/usr/bin:/bin")
    proc = _run(RECOVER, [], env)
    blob = proc.stdout + proc.stderr
    assert PARK_TOKEN in blob, blob
    assert "RECOVER_OK" in blob, blob
    _assert_honeypot_idle(log)


def test_doctor_parked_ok_does_not_spawn(tmp_path: Path) -> None:
    bindir, log = _honeypot(tmp_path)
    env = _doctor_env(
        tmp_path,
        extra_path=f"{bindir}:{os.environ.get('PATH', '/usr/bin:/bin')}",
        CLOUD_API_PARKED="1",
    )
    proc = _run(DOCTOR, [], env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "doctor: OK" in blob
    assert "CLOUD_API_PARKED" in blob
    assert "Extra High spawn skipped" in blob or "spawn skipped" in blob.lower()
    assert "CLOUD_LAUNCH_OK" not in blob
    assert "CLOUD_LAUNCH_ERR" not in blob
    _assert_honeypot_idle(log)
    _assert_secret_free(blob)
    assert EXAMPLE_REPO not in blob or "GCS_CLOUD_REPO/CLOUD_REPO_URL is set" in blob


def test_doctor_unparked_does_not_claim_parked(tmp_path: Path) -> None:
    env = _doctor_env(tmp_path)
    proc = _run(DOCTOR, [], env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "doctor: OK" in blob
    assert "OK  CLOUD_API_PARKED" not in blob
    assert "spawn skipped" not in blob.lower()


def test_docs_and_studio_env_name_recover_doctor_park() -> None:
    wipe = WIPE.read_text(encoding="utf-8")
    agents = AGENTS.read_text(encoding="utf-8")
    studio = STUDIO_ENV_EXAMPLE.read_text(encoding="utf-8")
    blob = f"{wipe}\n{agents}\n{studio}"
    assert "CLOUD_API_PARKED" in wipe
    assert "CLOUD_API_PARKED" in agents
    assert "CLOUD_API_PARKED=0" in studio
    assert "GCS_BOT_BRIDGE=0" in studio
    assert "recover.sh" in wipe and "doctor.sh" in wipe
    assert "Extra High" in blob
    assert "launch-cloud-extra-high" in wipe or "distinct" in wipe.lower()
    assert BOT_CLOUDAGENT in wipe or BOT_CLOUDAGENT in agents


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
    for proc in procs.values():
        _reap_proc(proc)
    subprocess.run(
        ["bash", str(BUS), "stop"],
        cwd=str(REPO),
        env={
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(state.parent / "home"),
            "GCS_ROOT": str(REPO),
            "GCS_A2A_STATE": str(state),
            "LC_ALL": "C",
        },
        capture_output=True,
        text=True,
        timeout=20,
    )


def _bot_bridge_pids_for_state(state: Path) -> list[int]:
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


def test_recover_parked_live_does_not_start_bot_bridge(tmp_path: Path) -> None:
    """Park compose: CLOUD_API_PARKED=1 still PAL-25 default-off bot-bridge."""
    bindir, log = _honeypot(tmp_path)
    state = tmp_path / "a2a-state"
    procs = _plant_leftover_bus_without_bot_bridge(state)
    env = _recover_env(
        tmp_path, state, extra_path=f"{bindir}:{os.environ.get('PATH', '/usr/bin:/bin')}"
    )
    env.pop("GCS_RECOVER_DRY_RUN", None)
    env["CLOUD_API_PARKED"] = "1"
    env.pop("GCS_BOT_BRIDGE", None)
    try:
        proc = _run(RECOVER, [], env, timeout=30)
        blob = proc.stdout + proc.stderr
        assert PARK_TOKEN in blob, blob
        assert "RECOVER_OK" in blob, blob
        assert "STUDIO_BUS_BOT_BRIDGE_START" not in blob, blob
        assert "STUDIO_BUS_BOT_BRIDGE_SKIP" in blob, blob
        assert "CLOUD_LAUNCH_OK" not in blob
        pid = _pidfile_pid(state / "bot-bridge.pid")
        assert not _pid_alive(pid), f"parked recover spawned bot-bridge pid={pid}"
        live = _bot_bridge_pids_for_state(state)
        assert live == [], f"parked recover left live bot-bridge pids={live}"
        _assert_honeypot_idle(log)
        _assert_secret_free(blob)
    finally:
        _reap_bus_state(procs, state)
        for extra in _bot_bridge_pids_for_state(state):
            _reap_pid(extra)
