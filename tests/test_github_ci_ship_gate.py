"""GitHub Actions on this repo must run pytest AND secret_scan.

Empty CI is not merge. Main currently has no workflows; this PR adds a
minimal ship-gate so #79 has GitHub evidence. Does not remint #64 MCP
catalogs / footers / SOUL. Does not vendor Hermes. Does not land #26+#28.
Living Sky Linear is LIV (never Black Swan).
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO / ".github" / "workflows"
SECRET_SCAN = REPO / "scripts" / "secret_scan.py"
PRIVATE_GAME = "atebites-hub/" + "pale" + "mon"


def _workflow_texts() -> list[tuple[Path, str]]:
    if not WORKFLOWS.is_dir():
        return []
    rows: list[tuple[Path, str]] = []
    for path in sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml")):
        rows.append((path, path.read_text(encoding="utf-8")))
    return rows


def _blob() -> str:
    return "\n".join(text for _path, text in _workflow_texts())


def test_github_actions_workflow_exists() -> None:
    assert WORKFLOWS.is_dir(), "empty CI is not merge: missing .github/workflows"
    assert _workflow_texts(), "empty CI is not merge: no workflow YAML"


def test_github_actions_runs_pytest_and_secret_scan() -> None:
    blob = _blob()
    assert "pull_request" in blob
    assert "ubuntu-latest" in blob
    assert "pytest" in blob
    assert "secret_scan.py" in blob or str(SECRET_SCAN.relative_to(REPO)) in blob
    assert "-q" in blob or "pytest -q" in blob
    assert "actions/checkout@" in blob
    assert "actions/setup-python@" in blob


def test_github_actions_checks_out_submodules_with_full_history() -> None:
    """Wipe-kit pins vendor/taskboard via git describe --tags --exact-match."""
    blob = _blob()
    assert "submodules:" in blob
    assert "true" in blob or "recursive" in blob
    assert re.search(r"fetch-depth:\s*0\b", blob)


def test_github_actions_is_not_leftover_green() -> None:
    blob = _blob()
    assert "--override-ini" not in blob
    assert "continue-on-error" not in blob
    assert "Hermes" not in blob
    assert PRIVATE_GAME not in blob
    assert "launch-cloud-extra-high" not in blob
    low = blob.lower()
    assert "black swan" not in low
    assert "blackswan" not in low.replace("-", "")
