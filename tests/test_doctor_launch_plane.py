"""doctor.sh Cursor Cloud launch-plane: fail closed, never print keys.

Does not spawn Extra High, Bot CloudAgent, or remint GCS #30 cloud-env.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DOCTOR = REPO / "doctor.sh"
LAUNCH = REPO / "scripts" / "launch-cloud-extra-high.sh"
WIPE = REPO / "docs" / "studio" / "WIPE.md"
README = REPO / "README.md"
SETUP = REPO / "setup.sh"

FAKE_KEY = "test-cursor-api-key-doctor-launch-plane-not-leaked"
EXAMPLE_REPO = "https://github.com/example/control-plane"

BOT_CLOUDAGENT = "Bot" + " CloudAgent"


def _run(
    env: dict[str, str],
    *,
    xtrace: bool = False,
    timeout: int = 30,
) -> subprocess.CompletedProcess[str]:
    argv = ["bash"]
    if xtrace:
        argv.append("-x")
    argv.append(str(DOCTOR))
    return subprocess.run(
        argv,
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _doctor_env(tmp_path: Path, **extra: str) -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    drop = {
        "CURSOR_API_KEY",
        "GCS_CLOUD_REPO",
        "CLOUD_REPO_URL",
        "CURSOR_CLOUD_REPO",
        "CURSOR_AGENT_ENV",
    }
    env = {k: v for k, v in os.environ.items() if k not in drop}
    env.update(
        {
            "HOME": str(home),
            "GCS_ROOT": str(REPO),
            "GCS_A2A_STATE": str(tmp_path / "a2a-state"),
            "GCS_BOT_BIND_OPTIONAL": "1",
            "LC_ALL": "C",
            "TERM": "dumb",
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        }
    )
    env.update(extra)
    return env


def _assert_key_absent(blob: str) -> None:
    assert FAKE_KEY not in blob
    assert "CURSOR_API_KEY=" not in blob
    assert f"CURSOR_API_KEY={FAKE_KEY}" not in blob


def test_doctor_and_launcher_exist() -> None:
    assert DOCTOR.is_file(), "missing doctor.sh"
    assert LAUNCH.is_file(), "missing scripts/launch-cloud-extra-high.sh"


def test_doctor_source_fail_closed_launch_plane_no_secrets_no_spawn() -> None:
    text = DOCTOR.read_text(encoding="utf-8")
    assert "scripts/launch-cloud-extra-high.sh" in text
    assert "GCS_CLOUD_REPO" in text
    assert "CURSOR_API_KEY" in text
    assert "echo \"$CURSOR_API_KEY\"" not in text
    assert "echo $CURSOR_API_KEY" not in text
    assert "CURSOR_API_KEY=" not in text
    assert BOT_CLOUDAGENT not in text
    assert "gcs-cloud-env" not in text
    assert "session/new" not in text
    assert "remint" not in text.lower()
    assert "bash \"$ROOT/scripts/launch-cloud-extra-high.sh\"" not in text
    assert "bash $ROOT/scripts/launch-cloud-extra-high.sh" not in text
    assert '"$ROOT/scripts/launch-cloud-extra-high.sh"' not in text or "-e" in text
    assert "WARN GCS_CLOUD_REPO" not in text
    assert "WARN CURSOR_API_KEY" not in text
    assert "bad " in text
    invoked = [
        line.strip()
        for line in text.splitlines()
        if "launch-cloud-extra-high.sh" in line and not line.strip().startswith("#")
    ]
    for line in invoked:
        assert not line.startswith("bash ")
        assert "launch-cloud-extra-high.sh" in line


def test_doctor_fails_closed_without_gcs_cloud_repo(tmp_path: Path) -> None:
    env = _doctor_env(tmp_path, CURSOR_API_KEY=FAKE_KEY)
    proc = _run(env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode != 0, blob
    assert "doctor: FAIL" in blob
    assert "ERR" in blob
    assert "GCS_CLOUD_REPO" in blob
    assert "WARN GCS_CLOUD_REPO" not in blob
    _assert_key_absent(blob)
    assert "CLOUD_LAUNCH_OK" not in blob
    assert BOT_CLOUDAGENT not in blob


def test_doctor_fails_closed_without_cursor_api_key(tmp_path: Path) -> None:
    env = _doctor_env(tmp_path, GCS_CLOUD_REPO=EXAMPLE_REPO)
    proc = _run(env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode != 0, blob
    assert "doctor: FAIL" in blob
    assert "ERR" in blob
    assert "CURSOR_API_KEY" in blob
    assert "WARN CURSOR_API_KEY" not in blob
    _assert_key_absent(blob)
    assert "CLOUD_LAUNCH_OK" not in blob


def test_doctor_ok_launch_plane_does_not_print_key(tmp_path: Path) -> None:
    env = _doctor_env(tmp_path, GCS_CLOUD_REPO=EXAMPLE_REPO, CURSOR_API_KEY=FAKE_KEY)
    proc = _run(env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "doctor: OK" in blob
    assert "GCS_CLOUD_REPO" in blob
    assert "CURSOR_API_KEY is set" in blob
    assert "value not printed" in blob
    assert "scripts/launch-cloud-extra-high.sh" in blob
    _assert_key_absent(blob)
    assert "CLOUD_LAUNCH_OK" not in blob
    assert EXAMPLE_REPO not in blob or "GCS_CLOUD_REPO/CLOUD_REPO_URL is set" in blob


def test_doctor_accepts_cloud_repo_url_alias(tmp_path: Path) -> None:
    env = _doctor_env(tmp_path, CLOUD_REPO_URL=EXAMPLE_REPO, CURSOR_API_KEY=FAKE_KEY)
    proc = _run(env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "GCS_CLOUD_REPO" in blob
    _assert_key_absent(blob)


def test_doctor_accepts_agent_env_file_without_printing_key(tmp_path: Path) -> None:
    env = _doctor_env(tmp_path, GCS_CLOUD_REPO=EXAMPLE_REPO)
    agent_env = Path(env["HOME"]) / ".config" / "cursor" / "agent.env"
    agent_env.parent.mkdir(parents=True, exist_ok=True)
    agent_env.write_text(f"export CURSOR_API_KEY={FAKE_KEY}\n", encoding="utf-8")
    proc = _run(env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "CURSOR_API_KEY" in blob
    assert "value not printed" in blob or "file present" in blob
    _assert_key_absent(blob)
    assert agent_env.read_text(encoding="utf-8").startswith("export CURSOR_API_KEY=")


def test_doctor_xtrace_does_not_print_cursor_api_key(tmp_path: Path) -> None:
    env = _doctor_env(tmp_path, GCS_CLOUD_REPO=EXAMPLE_REPO, CURSOR_API_KEY=FAKE_KEY)
    proc = _run(env, xtrace=True)
    blob = proc.stdout + proc.stderr
    assert FAKE_KEY not in blob
    assert f"CURSOR_API_KEY={FAKE_KEY}" not in blob


def test_docs_say_doctor_fails_closed_on_launch_plane() -> None:
    wipe = WIPE.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    setup = SETUP.read_text(encoding="utf-8")
    blob = f"{wipe}\n{readme}\n{setup}"
    assert "launch-plane" in blob.lower()
    assert "GCS_CLOUD_REPO" in wipe
    assert "CURSOR_API_KEY" in wipe
    assert "launch-cloud-extra-high" in wipe
    assert "never prints" in wipe.lower() or "never print" in wipe.lower()
    assert "Bot CloudAgent" in wipe or "Bot CloudAgent" in readme
    assert "FAIL" in readme and "GCS_CLOUD_REPO" in readme
    assert "launch-plane" in setup.lower()
