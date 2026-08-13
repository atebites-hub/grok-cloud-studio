"""lib.py cloud-repo fail-closed + seat ports."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "scripts" / "a2a" / "lib.py"


def test_cloud_repo_fail_closed() -> None:
    env = {k: v for k, v in os.environ.items() if k not in {
        "GCS_CLOUD_REPO", "CLOUD_REPO_URL", "CURSOR_CLOUD_REPO",
    }}
    proc = subprocess.run(
        ["python3", str(LIB), "cloud-repo"],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "CLOUD_BLOCKED" in proc.stderr


def test_cloud_repo_from_env(tmp_path: Path) -> None:
    env = {**os.environ, "GCS_CLOUD_REPO": "https://github.com/example/control-plane"}
    proc = subprocess.run(
        ["python3", str(LIB), "cloud-repo"],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "https://github.com/example/control-plane"


def test_seat_ports() -> None:
    floor = subprocess.check_output(["python3", str(LIB), "port", "floor"], cwd=str(ROOT), text=True)
    ops = subprocess.check_output(["python3", str(LIB), "port", "ops"], cwd=str(ROOT), text=True)
    assert floor.strip() == "8740"
    assert ops.strip() == "8741"
