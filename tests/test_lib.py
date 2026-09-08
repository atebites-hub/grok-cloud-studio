"""lib.py cloud-repo fail-closed + seat ports."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "scripts" / "a2a" / "lib.py"


def _load_lib() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gcs_lib_canonical", LIB)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_registry(root: Path, seats: dict[str, dict], skip: list[str] | None = None) -> None:
    path = root / "docs" / "a2a" / "registry.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": "1.0.0",
                "hub": "http://127.0.0.1:8732",
                "skipSeats": skip or [],
                "seats": seats,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


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
    audio = subprocess.check_output(["python3", str(LIB), "port", "audio"], cwd=str(ROOT), text=True)
    narrative = subprocess.check_output(
        ["python3", str(LIB), "port", "narrative"], cwd=str(ROOT), text=True
    )
    assert floor.strip() == "8740"
    assert ops.strip() == "8741"
    assert audio.strip() == "8754"
    assert narrative.strip() == "8755"


def test_canonical_donald_aliases_to_orchestrator_on_shipped_registry() -> None:
    lib = _load_lib()
    assert lib.canonical_seat("donald", ROOT) == "orchestrator"
    assert lib.canonical_seat("Donald", ROOT) == "orchestrator"
    assert lib.canonical_seat("orchestrator", ROOT) == "orchestrator"


def test_canonical_cli_donald_prints_orchestrator() -> None:
    proc = subprocess.run(
        ["python3", str(LIB), "canonical", "donald"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "orchestrator"


def test_canonical_donald_first_class_wins(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("GCS_A2A_REGISTRY", raising=False)
    _write_registry(
        tmp_path,
        {
            "donald": {"card": "docs/a2a/cards/donald.json"},
            "floor": {"card": "docs/a2a/cards/floor.json"},
        },
        skip=["donald"],
    )
    lib = _load_lib()
    assert lib.canonical_seat("donald", tmp_path) == "donald"
    assert lib.canonical_seat("orchestrator", tmp_path) == "donald"


def test_skip_seats_still_lists_donald_and_orchestrator() -> None:
    proc = subprocess.run(
        ["python3", str(LIB), "skip-seats"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, proc.stderr
    names = {line.strip() for line in proc.stdout.splitlines() if line.strip()}
    assert "donald" in names
    assert "orchestrator" in names
