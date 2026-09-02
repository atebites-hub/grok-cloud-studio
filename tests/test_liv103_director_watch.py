"""LIV-103: directors never block-wait on Cloud watch."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WATCH = REPO / "scripts" / "cloud" / "watch.sh"
WATCH_LONG = REPO / "scripts" / "cloud" / "watch-cloud-agent.sh"


def _env(**extra: str) -> dict[str, str]:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": "/tmp",
        "LC_ALL": "C",
        "GCS_ROOT": str(REPO),
    }
    env.update(extra)
    return env


def _run(script: Path, args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(script), *args],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )


def test_watch_refuses_when_director_seat_set() -> None:
    proc = _run(WATCH, ["bc-liv103"], _env(GCS_DIRECTOR_SEAT="art"))
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 2
    assert "CLOUD_WATCH_REFUSED" in combined
    assert "CLOUD_ALLOW_BLOCK_WAIT=1" in combined


def test_watch_long_name_refuses_when_director_seat_set() -> None:
    proc = _run(WATCH_LONG, ["bc-liv103"], _env(GCS_DIRECTOR_SEAT="floor"))
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 2
    assert "CLOUD_WATCH_REFUSED" in combined


def test_watch_allows_operator_override() -> None:
    proc = _run(
        WATCH,
        ["bc-liv103"],
        _env(GCS_DIRECTOR_SEAT="art", CLOUD_ALLOW_BLOCK_WAIT="1"),
    )
    combined = proc.stdout + proc.stderr
    assert "CLOUD_WATCH_REFUSED" not in combined
    assert proc.returncode != 2


def test_watch_without_director_seat_does_not_refuse() -> None:
    env = _env()
    env.pop("GCS_DIRECTOR_SEAT", None)
    proc = _run(WATCH, ["bc-liv103"], env)
    combined = proc.stdout + proc.stderr
    assert "CLOUD_WATCH_REFUSED" not in combined
    assert proc.returncode != 2
