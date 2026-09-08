"""Owning director seat for spawn-waiter / Extra High FLEET_DONE.

GCS_DIRECTOR_SEAT=cloud must register fleet.jsonl + FLEET_DONE on cloud,
not silently default to floor. Distinct from GCS #32 leftover shepherd skip
and GCS #111 waiter_pid tombstone (do not remint). Never Bot CloudAgent.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cloud"))
sys.path.insert(0, str(ROOT / "scripts" / "a2a"))

import fleet_ledger  # noqa: E402
from fleet_ledger import (  # noqa: E402
    load_entries,
    notify_owner,
    register,
    set_waiter_pid,
)
from test_cloud_launch import (  # noqa: E402
    EXAMPLE_REPO,
    FAKE_KEY,
    LAUNCH,
    MockCursorAPI,
    _run,
    _script_env,
)

FEATURE = ROOT / "tests" / "features" / "waiter_owner_seat.feature"
SPAWN = ROOT / "scripts" / "cloud" / "spawn-waiter.sh"
LAUNCH_TS = ROOT / "scripts" / "cloud" / "sdk" / "launch.ts"
WAIT_TS = ROOT / "scripts" / "cloud" / "sdk" / "wait-notify.ts"
CLOUD_README = ROOT / "scripts" / "cloud" / "README.md"
CLOUD_DOC = ROOT / "docs" / "CLOUD.md"
HERMES = ROOT / "docs" / "studio" / "HERMES_GAP.md"


def _load_seat(state: Path, seat: str) -> list[dict]:
    return load_entries(state / seat / "fleet.jsonl")


def _spawn_env(tmp_path: Path, **extra: str) -> dict[str, str]:
    """Minimal env. Do not inherit a live Palemon GCS_DIRECTOR_SEAT."""
    stub = tmp_path / "wait-notify-stub"
    if not stub.exists():
        stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        stub.chmod(0o755)
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(tmp_path),
        "TMPDIR": str(tmp_path),
        "GCS_ROOT": str(ROOT),
        "GCS_A2A_STATE": str(tmp_path / "a2a"),
        "GCS_CLOUD_LOG_DIR": str(tmp_path / "logs"),
        "CLOUD_WAITER_BIN": str(stub),
        "LC_ALL": "C",
    }
    env.update(extra)
    return env


def _run_spawn(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SPAWN), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )


def test_feature_binds_cloud_owner_not_floor() -> None:
    text = FEATURE.read_text(encoding="utf-8")
    fold = " ".join(text.split())
    assert "GCS_DIRECTOR_SEAT=cloud" in text
    assert "silently default to floor" in fold
    assert "FLEET_DONE" in text
    assert "Bot CloudAgent" in text
    assert "Hermes" in text


def test_spawn_waiter_set_waiter_invocation_passes_seat() -> None:
    src = SPAWN.read_text(encoding="utf-8")
    lines = [ln for ln in src.splitlines() if "set-waiter" in ln]
    assert lines, "spawn-waiter.sh must call fleet_ledger set-waiter"
    assert any("--seat" in ln for ln in lines), (
        "set-waiter must pass --seat so waiter_pid lands on cloud, not ops/floor"
    )


def test_launch_sh_spawn_waiter_invocation_passes_seat() -> None:
    src = LAUNCH.read_text(encoding="utf-8")
    match = re.search(r"spawn-waiter\.sh[^\n]+", src)
    assert match, "launch Extra High must invoke spawn-waiter.sh"
    assert "--seat" in match.group(0), (
        "launch-cloud-extra-high.sh must pass --seat so GCS_DIRECTOR_SEAT=cloud "
        "is not dropped (silent floor default)"
    )


def test_launch_ts_spawn_waiter_passes_seat() -> None:
    src = LAUNCH_TS.read_text(encoding="utf-8")
    fn = re.search(r"function spawnWaiter\([\s\S]*?\n\}", src)
    assert fn, "launch.ts must define spawnWaiter"
    assert '"--seat"' in fn.group(0), (
        "SDK launch Extra High must pass --seat to spawn-waiter.sh"
    )


def test_wait_notify_ledger_notify_passes_seat() -> None:
    src = WAIT_TS.read_text(encoding="utf-8")
    fn = re.search(r"function ledgerNotify\([\s\S]*?\n\}", src)
    assert fn, "wait-notify.ts must define ledgerNotify"
    assert '"--seat"' in fn.group(0), (
        "FLEET_DONE notify must pass --seat so the ping is not ops/floor default"
    )


def test_set_waiter_pid_stays_on_registered_cloud_when_env_unset(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("GCS_ROOT", str(ROOT))
    monkeypatch.setenv("GCS_A2A_STATE", str(tmp_path))
    monkeypatch.delenv("GCS_DIRECTOR_SEAT", raising=False)
    monkeypatch.delenv("CLOUD_OWNER_SEAT", raising=False)
    register("bc-tandem", seat="cloud", name="gcs-waiter-owner-seat-tandem")
    set_waiter_pid("bc-tandem", 4242, seat=None)
    cloud = _load_seat(tmp_path, "cloud")
    ops = _load_seat(tmp_path, "ops")
    floor = _load_seat(tmp_path, "floor")
    assert len(cloud) == 1
    assert cloud[0]["bc_id"] == "bc-tandem"
    assert cloud[0]["seat"] == "cloud"
    assert int(cloud[0]["waiter_pid"]) == 4242
    assert ops == []
    assert floor == []


def test_spawn_waiter_explicit_seat_cloud_does_not_default_to_floor(
    tmp_path: Path,
) -> None:
    env = _spawn_env(tmp_path)
    proc = _run_spawn(
        ["--id", "bc-tandem", "--name", "gcs-waiter-owner-seat-tandem", "--seat", "cloud"],
        env,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "CLOUD_WAITER_SPAWNED" in proc.stdout
    assert "seat=cloud" in proc.stdout
    state = tmp_path / "a2a"
    cloud = _load_seat(state, "cloud")
    ops = _load_seat(state, "ops")
    floor = _load_seat(state, "floor")
    assert len(cloud) == 1, cloud
    assert cloud[0]["bc_id"] == "bc-tandem"
    assert cloud[0]["seat"] == "cloud"
    assert cloud[0].get("waiter_pid") not in (None, "", 0)
    assert ops == []
    assert floor == []
    assert FAKE_KEY not in blob


def test_spawn_waiter_env_cloud_does_not_register_floor(tmp_path: Path) -> None:
    env = _spawn_env(tmp_path, GCS_DIRECTOR_SEAT="cloud")
    proc = _run_spawn(["--id", "bc-env-cloud", "--name", "owner-env"], env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "seat=cloud" in proc.stdout
    state = tmp_path / "a2a"
    cloud = _load_seat(state, "cloud")
    floor = _load_seat(state, "floor")
    assert len(cloud) == 1
    assert cloud[0]["bc_id"] == "bc-env-cloud"
    assert floor == []
    assert FAKE_KEY not in blob


def test_fleet_done_pings_cloud_owner_not_floor(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("GCS_ROOT", str(ROOT))
    monkeypatch.setenv("GCS_A2A_STATE", str(tmp_path))
    monkeypatch.setenv("GCS_DIRECTOR_SEAT", "cloud")
    monkeypatch.delenv("REPORT_TO", raising=False)
    monkeypatch.delenv("GCS_REPORT_TO", raising=False)
    pings: list[str] = []

    def fake_ping(seat: str, text: str) -> bool:
        pings.append(seat)
        assert "FLEET_DONE" in text
        assert "bc-tandem" in text
        return True

    monkeypatch.setattr(fleet_ledger, "ping_seat", fake_ping)
    register("bc-tandem", seat="cloud", name="gcs-waiter-owner-seat-tandem")
    notify_owner(
        "bc-tandem",
        {
            "runStatus": "ERROR",
            "name": "gcs-waiter-owner-seat-tandem",
            "url": "https://cursor.com/agents/bc-tandem",
        },
    )
    assert pings[0] == "cloud"
    assert "studio-ops" in pings
    assert "floor" not in pings


def test_launch_extra_high_registers_cloud_not_floor(tmp_path: Path) -> None:
    stub = tmp_path / "wait-notify-stub"
    stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    stub.chmod(0o755)
    with MockCursorAPI(run_statuses=["CREATING"]) as api:
        env = _script_env(
            tmp_path,
            api.base,
            CURSOR_API_KEY=FAKE_KEY,
            GCS_DIRECTOR_SEAT="cloud",
            GCS_SPAWN_WAITER="1",
            CLOUD_SPAWN_WAITER="1",
            GCS_A2A_STATE=str(tmp_path / "a2a"),
            GCS_CLOUD_LOG_DIR=str(tmp_path / "logs"),
            CLOUD_WAITER_BIN=str(stub),
        )
        env.pop("CLOUD_WAITER_DRY", None)
        proc = _run(
            LAUNCH,
            ["--name", "gcs-waiter-owner-seat-tandem", "Prove owner seat. Open a PR."],
            env,
        )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "CLOUD_LAUNCH_OK" in proc.stdout
    assert "CLOUD_WAITER_SPAWNED" in blob
    assert "seat=cloud" in blob
    state = Path(env["GCS_A2A_STATE"])
    cloud = _load_seat(state, "cloud")
    floor = _load_seat(state, "floor")
    assert len(cloud) == 1, cloud
    assert cloud[0]["bc_id"] == "bc-mock"
    assert cloud[0]["seat"] == "cloud"
    assert floor == []
    assert FAKE_KEY not in blob
    assert api.posts and api.posts[0]["body"]["repos"][0]["url"] == EXAMPLE_REPO


def test_docs_name_cloud_owner_not_silent_floor() -> None:
    readme = CLOUD_README.read_text(encoding="utf-8")
    cloud_md = CLOUD_DOC.read_text(encoding="utf-8")
    fold = " ".join((readme + "\n" + cloud_md).split()).replace("`", "")
    assert "GCS_DIRECTOR_SEAT" in readme
    assert "spawn-waiter" in readme
    assert "Bot CloudAgent" in cloud_md
    assert "not silently default to floor" in fold


def test_does_not_vendor_hermes_or_bot_cloudagent() -> None:
    spawn = SPAWN.read_text(encoding="utf-8")
    launch = LAUNCH.read_text(encoding="utf-8")
    assert "hermes-agent" not in spawn.lower()
    assert "NousResearch" not in spawn
    assert "hermes-agent" not in launch.lower()
    assert "never Bot CloudAgent" in launch or "Never Bot CloudAgent" in launch
    assert HERMES.is_file()
