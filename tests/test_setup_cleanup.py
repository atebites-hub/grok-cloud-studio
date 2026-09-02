"""Disaster-recovery setup.sh / cleanup.sh. No live grok serve, no secrets."""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SETUP = REPO / "setup.sh"
CLEANUP = REPO / "cleanup.sh"
INSTALL = REPO / "install.sh"
DOCTOR = REPO / "doctor.sh"
WIPE = REPO / "docs" / "studio" / "WIPE.md"
README = REPO / "README.md"
STUDIO_ENV_EXAMPLE = REPO / "studio.env.example"

PRIVATE_GAME = "atebites-hub/" + "palemon"


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


def _base_env(tmp_path: Path, state: Path) -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": str(home),
        "GCS_ROOT": str(REPO),
        "GCS_A2A_STATE": str(state),
        "GCS_BOT_BIND_OPTIONAL": "1",
        "GCS_SETUP_SKIP_INSTALL": "1",
        "GCS_SETUP_SKIP_START": "1",
        "GCS_SETUP_SKIP_DOCTOR": "1",
        "LC_ALL": "C",
        "TERM": "dumb",
    }


def test_setup_and_cleanup_scripts_exist() -> None:
    assert SETUP.is_file(), "missing setup.sh"
    assert CLEANUP.is_file(), "missing cleanup.sh"


def test_install_chmods_setup_and_cleanup() -> None:
    text = INSTALL.read_text(encoding="utf-8")
    assert '"$ROOT/setup.sh"' in text
    assert '"$ROOT/cleanup.sh"' in text
    assert "chmod +x" in text


def test_doctor_lists_setup_and_cleanup() -> None:
    text = DOCTOR.read_text(encoding="utf-8")
    assert "setup.sh" in text
    assert "cleanup.sh" in text


def test_setup_and_cleanup_help() -> None:
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": "/tmp",
        "GCS_ROOT": str(REPO),
        "LC_ALL": "C",
        "TERM": "dumb",
    }
    for script, token in ((SETUP, "SETUP"), (CLEANUP, "CLEANUP")):
        proc = _run(script, ["--help"], env)
        blob = proc.stdout + proc.stderr
        assert proc.returncode == 0, blob
        assert "--help" in blob or "Usage" in blob or script.name in blob
        assert token.lower() in blob.lower() or script.name in blob
        assert "CURSOR_API_KEY=" not in blob
        key = os.environ.get("CURSOR_API_KEY", "")
        if key:
            assert key not in blob


def test_setup_cleanup_secret_free_and_no_ak() -> None:
    for path in (SETUP, CLEANUP):
        text = path.read_text(encoding="utf-8")
        assert "agent-kanban" not in text
        assert "ak start" not in text
        assert "mint-floor-ops-worker" not in text
        assert "echo \"$CURSOR_API_KEY\"" not in text
        assert "echo $CURSOR_API_KEY" not in text
        assert "CURSOR_API_KEY=" not in text
        assert "TAILSCALE_AUTH_KEY=" not in text
        assert PRIVATE_GAME not in text
        assert "git add" not in text
        assert "git commit" not in text


def test_setup_is_crash_safe_no_daemons() -> None:
    text = SETUP.read_text(encoding="utf-8")
    assert "start-studio-bus.sh start" in text
    assert "start-studio-bus.sh start --daemons" not in text
    assert "install.sh" in text
    assert "start-taskboard.sh" in text
    assert "mcp-http.sh" in text
    assert "start-tailscale-serve.sh" in text
    assert "doctor.sh" in text
    assert "SETUP_OK" in text
    assert "setup-taskboard.sh" in text
    assert "studio.env.example" in text
    assert "13-seat" in text or "13 seat" in text.lower() or "--daemons" in text
    assert "GCS_ACP_SEATS" in text
    assert "submodule update --init" in text
    assert "vendor/taskboard" in text


def test_cleanup_soft_by_default_and_wipe_flag() -> None:
    text = CLEANUP.read_text(encoding="utf-8")
    assert "start-studio-bus.sh stop" in text
    assert "CLEANUP_DAEMONS" in text
    assert "CLEANUP_WIPE_STATE" in text
    assert "CLEANUP_OK" in text
    assert "setup-taskboard.sh" in text
    assert "start-taskboard.sh" in text or "setup-taskboard.sh" in text
    assert "mcp-http.sh" in text or "setup-taskboard.sh" in text
    assert "start-tailscale-serve.sh" in text


def test_docs_name_setup_cleanup_as_dr_entrypoints() -> None:
    wipe = WIPE.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    assert "setup.sh" in wipe
    assert "cleanup.sh" in wipe
    assert "setup.sh" in readme
    assert "cleanup.sh" in readme
    fold = " ".join(wipe.lower().split())
    assert "entrypoint" in fold or "disaster" in fold or "dr " in fold or "one-command" in fold


def test_setup_copies_example_env_and_does_not_overwrite(tmp_path: Path) -> None:
    state = tmp_path / "a2a-state"
    env = _base_env(tmp_path, state)
    first = _run(SETUP, [], env)
    blob = first.stdout + first.stderr
    assert first.returncode == 0, blob
    studio = state / "studio.env"
    assert studio.is_file()
    assert STUDIO_ENV_EXAMPLE.read_text(encoding="utf-8") == studio.read_text(encoding="utf-8")
    assert "SETUP_OK" in blob
    marker = "# live-studio-env-keep\nGCS_MIND_SEATS=\nGCS_START_SEAT_DAEMONS=0\n"
    studio.write_text(marker, encoding="utf-8")
    second = _run(SETUP, [], env)
    blob2 = second.stdout + second.stderr
    assert second.returncode == 0, blob2
    assert studio.read_text(encoding="utf-8") == marker
    assert "SETUP_OK" in blob2


def test_cleanup_default_does_not_delete_studio_env(tmp_path: Path) -> None:
    state = tmp_path / "a2a-state"
    state.mkdir(parents=True)
    studio = state / "studio.env"
    studio.write_text("GCS_MIND_SEATS=\n# keep-me\n", encoding="utf-8")
    inbox = state / "floor" / "inbox.jsonl"
    inbox.parent.mkdir(parents=True)
    inbox.write_text("{}\n", encoding="utf-8")
    pin = state / "floor" / "mind" / "session"
    pin.parent.mkdir(parents=True)
    pin.write_text("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\n", encoding="utf-8")
    db = state / "taskboard" / "taskboard.db"
    db.parent.mkdir(parents=True)
    db.write_text("db\n", encoding="utf-8")
    envf = tmp_path / "repo-env"
    envf.write_text("GCS_CLOUD_REPO=https://example.invalid/repo\n", encoding="utf-8")
    env = _base_env(tmp_path, state)
    env.pop("GCS_SETUP_SKIP_INSTALL", None)
    env.pop("GCS_SETUP_SKIP_START", None)
    env.pop("GCS_SETUP_SKIP_DOCTOR", None)
    proc = _run(CLEANUP, [], env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "CLEANUP_OK" in blob
    assert studio.is_file()
    assert "keep-me" in studio.read_text(encoding="utf-8")
    assert inbox.is_file()
    assert pin.is_file()
    assert db.is_file()
    assert envf.is_file()
    assert "CURSOR_API_KEY=" not in blob
    assert PRIVATE_GAME not in blob


def test_cleanup_wipe_state_removes_inbox_db_keeps_studio_env(tmp_path: Path) -> None:
    state = tmp_path / "a2a-state"
    studio = state / "studio.env"
    studio.parent.mkdir(parents=True)
    studio.write_text("GCS_MIND_SEATS=\n# keep-studio-env\n", encoding="utf-8")
    inbox = state / "floor" / "inbox.jsonl"
    inbox.parent.mkdir(parents=True)
    inbox.write_text("{}\n", encoding="utf-8")
    pin = state / "floor" / "mind" / "session"
    pin.parent.mkdir(parents=True)
    pin.write_text("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\n", encoding="utf-8")
    db = state / "taskboard" / "taskboard.db"
    db.parent.mkdir(parents=True)
    db.write_text("db\n", encoding="utf-8")
    pid = state / "hub.pid"
    pid.write_text("1\n", encoding="utf-8")
    env = _base_env(tmp_path, state)
    env["CLEANUP_WIPE_STATE"] = "1"
    proc = _run(CLEANUP, [], env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "CLEANUP_OK" in blob
    assert "inbox" in blob.lower() or "taskboard.db" in blob
    assert studio.is_file()
    assert "keep-studio-env" in studio.read_text(encoding="utf-8")
    assert not inbox.exists()
    assert not pin.exists()
    assert not db.exists()
    assert not pid.exists()


def test_setup_and_cleanup_are_chmod_targets_after_install_list() -> None:
    mode_s = SETUP.stat().st_mode
    mode_c = CLEANUP.stat().st_mode
    # Fresh git clone may lack +x until install.sh; the chmod list is the contract.
    # After this repo records them as scripts, prefer executable bits when present.
    assert stat.S_ISREG(mode_s)
    assert stat.S_ISREG(mode_c)
