"""Unique GitHub Actions ship-gate: gcs-github-ship-gate-workflows-beat1740.

Empty GitHub checks are not evidence. This beat must ship a real workflow
that executes `.venv/bin/pytest -q` and `python3 scripts/secret_scan.py`
as `run:` steps — not a comment, not a twin `ship-gate.yml` /
`scripts/ci/ship-gate.sh` wrapper, not leftover `--override-ini`.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
UNIQUE = "gcs-github-ship-gate-workflows-beat1740"
WORKFLOW = REPO / ".github" / "workflows" / f"{UNIQUE}.yml"
TWIN_WORKFLOW = REPO / ".github" / "workflows" / "ship-gate.yml"
TWIN_SCRIPT = REPO / "scripts" / "ci" / "ship-gate.sh"
AGENTS = REPO / "AGENTS.md"
README = REPO / "README.md"

PYTEST_CMD = ".venv/bin/pytest -q"
SCAN_CMD = "python3 scripts/secret_scan.py"

# Same-line `run:` so GitHub executes the command, not a wrapper script.
RUN_PYTEST = re.compile(rf"(?m)^[ \t]*run:[ \t]*{re.escape(PYTEST_CMD)}[ \t]*$")
RUN_SCAN = re.compile(rf"(?m)^[ \t]*run:[ \t]*{re.escape(SCAN_CMD)}[ \t]*$")
FETCH_DEPTH_ZERO = re.compile(r"(?m)^[ \t]*fetch-depth:[ \t]*0[ \t]*$")
BLACK_SWAN = "blackswan" + ".money"


def _workflow_text() -> str:
    assert WORKFLOW.is_file(), f"missing unique workflow {WORKFLOW.relative_to(REPO)}"
    return WORKFLOW.read_text(encoding="utf-8")


def test_unique_workflow_file_exists_and_is_not_twin_ship_gate() -> None:
    assert WORKFLOW.is_file(), f"missing {WORKFLOW.relative_to(REPO)}"
    assert not TWIN_WORKFLOW.exists(), "do not twin .github/workflows/ship-gate.yml"
    assert not TWIN_SCRIPT.exists(), "do not twin scripts/ci/ship-gate.sh"
    assert UNIQUE in WORKFLOW.name


def test_workflow_check_name_is_unique_beat1740() -> None:
    text = _workflow_text()
    assert f"name: {UNIQUE}" in text
    assert text.count(UNIQUE) >= 2
    assert "name: ship-gate" not in text
    assert "pytest -q and secret_scan" not in text


def _active_yaml(text: str) -> str:
    """Drop full-line comments so anti-twin notes are not treated as steps."""
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )


def test_workflow_runs_pytest_q_and_secret_scan_as_run_steps() -> None:
    text = _workflow_text()
    active = _active_yaml(text)
    assert RUN_PYTEST.search(text), f"workflow must run {PYTEST_CMD!r} as a run: step"
    assert RUN_SCAN.search(text), f"workflow must run {SCAN_CMD!r} as a run: step"
    assert "scripts/ci/ship-gate.sh" not in active
    assert "--override-ini" not in active
    assert "continue-on-error" not in active


def test_workflow_bootstraps_venv_on_pull_request() -> None:
    text = _workflow_text()
    assert "pull_request" in text
    assert "ubuntu-latest" in text
    assert "bash ./install.sh" in text or "bash install.sh" in text or "./install.sh" in text
    assert "GCS_BOT_BIND_OPTIONAL" in text
    assert "actions/setup-python@" in text
    assert "actions/checkout@" in text


def test_workflow_checks_out_submodules_with_tags() -> None:
    """Wipe-kit `git describe --tags --exact-match` needs vendor/taskboard tags."""
    text = _workflow_text()
    assert "submodules:" in text
    assert "true" in text or "recursive" in text
    assert FETCH_DEPTH_ZERO.search(text), "fetch-depth: 0 required so submodule tags exist"


def test_workflow_is_not_bot_cloudagent_or_cloned_liv_tickets() -> None:
    text = _workflow_text()
    lowered = text.lower()
    assert "launch-cloud-extra-high" not in text
    assert "bot cloudagent" not in lowered
    assert "cloud_launch" not in text
    assert "runstatus" not in text
    assert "hermes" not in lowered
    assert BLACK_SWAN not in lowered
    assert "black swan" not in lowered


def test_docs_name_the_unique_workflow_and_the_two_commands() -> None:
    agents = AGENTS.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    assert PYTEST_CMD in agents
    assert SCAN_CMD in agents
    assert UNIQUE in agents
    assert PYTEST_CMD in readme
    assert SCAN_CMD in readme
    assert UNIQUE in readme
    assert str(WORKFLOW.relative_to(REPO)) in readme or str(WORKFLOW.relative_to(REPO)) in agents
