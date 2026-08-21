"""Director prompt path: prompts/ or docs/studio/directors.

LIVE remint of floor-ops failed with missing prompt: $ROOT/prompts/floor_ops_director_prompt.txt
while the file lived under docs/studio/directors/. Fake trees only — no grok serve.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[1]
LIB = REPO / "scripts" / "a2a" / "lib.py"
SEAT_COMMON = REPO / "scripts" / "directors" / "seat-daemon-common.sh"
LAUNCH = REPO / "scripts" / "directors" / "launch-director.sh"
FOOTER = REPO / "scripts" / "directors" / "common_footer.txt"


@pytest.fixture(autouse=True)
def _clear_prompt_override_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GCS_PROMPT_DIR", raising=False)
    monkeypatch.delenv("PROMPTS_DIR", raising=False)


def _load_lib() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gcs_lib_prompt_dir", LIB)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _docs_layout(
    tmp_path: Path,
    *,
    empty_prompts: bool = True,
    extra_prompt_files: tuple[str, ...] = (),
) -> Path:
    """Product-floor layout: director prompts under docs/studio/directors/."""
    root = tmp_path / "gcs"
    docs = root / "docs" / "studio" / "directors"
    docs.mkdir(parents=True)
    (docs / "floor_ops_director_prompt.txt").write_text(
        "You are the Floor-Ops seat.\n",
        encoding="utf-8",
    )
    (docs / "studio_ops_director_prompt.txt").write_text(
        "You are the Studio-Ops seat.\n",
        encoding="utf-8",
    )
    if empty_prompts:
        (root / "prompts").mkdir(parents=True)
        for name in extra_prompt_files:
            (root / "prompts" / name).write_text("unrelated\n", encoding="utf-8")
    (root / "scripts" / "a2a").mkdir(parents=True)
    (root / "scripts" / "directors").mkdir(parents=True)
    (root / "docs" / "a2a").mkdir(parents=True)
    (root / "scripts" / "a2a" / "lib.py").symlink_to(LIB)
    (root / "scripts" / "directors" / "seat-daemon-common.sh").symlink_to(SEAT_COMMON)
    (root / "scripts" / "directors" / "prompt-dir.sh").symlink_to(
        REPO / "scripts" / "directors" / "prompt-dir.sh"
    )
    (root / "scripts" / "directors" / "common_footer.txt").symlink_to(FOOTER)
    (root / "scripts" / "directors" / "launch-director.sh").symlink_to(LAUNCH)
    registry = {
        "version": "1.0.0",
        "hub": "http://127.0.0.1:8732",
        "skipSeats": ["orchestrator"],
        "seats": {
            "orchestrator": {},
            "floor-ops": {"acpPort": 8740},
            "studio-ops": {"acpPort": 8741},
        },
    }
    (root / "docs" / "a2a" / "registry.json").write_text(
        json.dumps(registry),
        encoding="utf-8",
    )
    return root


def _env_for(root: Path, tmp_path: Path) -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {"GCS_PROMPT_DIR", "PROMPTS_DIR"}
    }
    env.update(
        {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(home),
            "GCS_ROOT": str(root),
            "GCS_A2A_STATE": str(tmp_path / "a2a-state"),
            "LC_ALL": "C",
            "TERM": "dumb",
        }
    )
    env.pop("GCS_PROMPT_DIR", None)
    env.pop("PROMPTS_DIR", None)
    return env


def test_resolve_prompt_path_finds_floor_ops_from_docs_layout(tmp_path: Path) -> None:
    root = _docs_layout(tmp_path)
    lib = _load_lib()
    found = lib.resolve_director_prompt("floor-ops", root)
    assert found is not None
    assert found.is_file()
    assert found.name == "floor_ops_director_prompt.txt"
    assert found.parent == root / "docs" / "studio" / "directors"
    assert "You are the Floor-Ops seat." in found.read_text(encoding="utf-8")


def test_prompts_dir_defaults_to_docs_when_prompts_empty(tmp_path: Path) -> None:
    root = _docs_layout(tmp_path, empty_prompts=True)
    lib = _load_lib()
    assert lib.prompts_dir(root) == root / "docs" / "studio" / "directors"


def test_prompts_dir_defaults_to_docs_when_prompts_missing(tmp_path: Path) -> None:
    root = _docs_layout(tmp_path, empty_prompts=False)
    lib = _load_lib()
    assert not (root / "prompts").exists()
    assert lib.prompts_dir(root) == root / "docs" / "studio" / "directors"


def test_prompts_dir_ignores_non_director_files_in_prompts(tmp_path: Path) -> None:
    root = _docs_layout(tmp_path, extra_prompt_files=("qa_a.txt", "systems.txt"))
    lib = _load_lib()
    assert lib.prompts_dir(root) == root / "docs" / "studio" / "directors"


def test_prompt_file_cli_finds_floor_ops_from_docs_layout(tmp_path: Path) -> None:
    root = _docs_layout(tmp_path)
    proc = subprocess.run(
        ["python3", str(LIB), "prompt-file", "floor-ops"],
        cwd=str(root),
        env=_env_for(root, tmp_path),
        capture_output=True,
        text=True,
        timeout=15,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    out = Path(proc.stdout.strip())
    assert out.is_file()
    assert out.name == "floor_ops_director_prompt.txt"
    assert (root / "docs" / "studio" / "directors") in out.parents or out.parent == (
        root / "docs" / "studio" / "directors"
    )


def test_write_agent_profile_remint_finds_docs_floor_ops(tmp_path: Path) -> None:
    root = _docs_layout(tmp_path)
    env = _env_for(root, tmp_path)
    script = r"""
set -euo pipefail
source scripts/directors/seat-daemon-common.sh
write_agent_profile floor-ops
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
    assert "missing prompt:" not in blob
    profile = Path(env["GCS_A2A_STATE"]) / "floor-ops" / "agent-profile.md"
    stdout_path = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    if stdout_path:
        profile = Path(stdout_path)
    assert profile.is_file(), blob
    text = profile.read_text(encoding="utf-8")
    assert "You are the Floor-Ops seat." in text
    assert "floor-ops" in text


def test_repo_layout_still_resolves_floor_from_prompts() -> None:
    lib = _load_lib()
    found = lib.resolve_director_prompt("floor", REPO)
    assert found is not None
    assert found.is_file()
    assert found.name == "floor_director_prompt.txt"
    assert found.parent == REPO / "prompts"


def test_ensure_prompts_links_docs_into_prompts(tmp_path: Path) -> None:
    root = _docs_layout(tmp_path, empty_prompts=True)
    lib = _load_lib()
    created = lib.ensure_prompt_links(root)
    dest = root / "prompts" / "floor_ops_director_prompt.txt"
    assert dest.is_file()
    assert dest.resolve() == (
        root / "docs" / "studio" / "directors" / "floor_ops_director_prompt.txt"
    ).resolve()
    assert any(p.name == "floor_ops_director_prompt.txt" for p in created)
    again = lib.ensure_prompt_links(root)
    assert again == []


def test_unknown_seat_prompt_is_missing_on_docs_layout(tmp_path: Path) -> None:
    root = _docs_layout(tmp_path)
    lib = _load_lib()
    assert lib.resolve_director_prompt("qa-a", root) is None


def test_launch_director_dry_run_uses_docs_floor_ops(tmp_path: Path) -> None:
    root = _docs_layout(tmp_path)
    proc = subprocess.run(
        ["bash", str(root / "scripts" / "directors" / "launch-director.sh"), "--dry-run", "floor-ops"],
        cwd=str(root),
        env=_env_for(root, tmp_path),
        capture_output=True,
        text=True,
        timeout=15,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "missing prompt:" not in blob
    assert "You are the Floor-Ops seat." in proc.stdout


def test_remint_helpers_search_docs_studio_directors() -> None:
    common = SEAT_COMMON.read_text(encoding="utf-8")
    helper = (REPO / "scripts" / "directors" / "prompt-dir.sh").read_text(encoding="utf-8")
    start = (REPO / "scripts" / "directors" / "start-seat-daemon.sh").read_text(encoding="utf-8")
    assert "gcs_resolve_prompt_file" in common
    assert "docs/studio/directors" in helper
    assert "write_agent_profile" in start
    assert "ensure-prompts" in (REPO / "install.sh").read_text(encoding="utf-8")
