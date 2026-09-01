"""Empty GitHub CI is not merge. Ship gate is pytest -q plus secret_scan."""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO / ".github" / "workflows"


def _workflow_files() -> list[Path]:
    if not WORKFLOWS.is_dir():
        return []
    return sorted(
        p
        for p in WORKFLOWS.iterdir()
        if p.is_file() and p.suffix.lower() in {".yml", ".yaml"}
    )


def test_github_ci_is_not_empty() -> None:
    files = _workflow_files()
    assert files, "empty CI is not merge: add .github/workflows ship-gate"
    blob = "\n".join(p.read_text(encoding="utf-8") for p in files)
    assert "pytest -q" in blob
    assert "secret_scan.py" in blob
    assert "GCS_BOT_BIND_OPTIONAL" in blob
    assert "actions/checkout" in blob
    low = blob.lower()
    assert "submodule" in low
    # A workflow that only echo's success is empty CI.
    assert "run:" in blob
    assert "pytest" in blob
