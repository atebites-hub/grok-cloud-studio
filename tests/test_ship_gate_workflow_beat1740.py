"""GitHub Actions ship-gate unique to beat1740.

Reads `.github/workflows/ship-gate-beat1740.yml` (not LIV-94 `ship-gate.yml`)
and asserts the workflow invokes `.venv/bin/pytest -q` and
`python3 scripts/secret_scan.py` on pull_request and push to main.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / ".github" / "workflows" / "ship-gate-beat1740.yml"


def _active_text() -> str:
    assert WORKFLOW.is_file(), "missing .github/workflows/ship-gate-beat1740.yml"
    lines: list[str] = []
    for line in WORKFLOW.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines)


def test_ship_gate_beat1740_workflow_exists() -> None:
    assert WORKFLOW.is_file(), "missing .github/workflows/ship-gate-beat1740.yml"
    assert WORKFLOW.name == "ship-gate-beat1740.yml"


def test_workflow_invokes_venv_pytest_q() -> None:
    text = _active_text()
    assert re.search(r"^\s+run:\s+\.venv/bin/pytest -q\s*$", text, re.M), text


def test_workflow_invokes_secret_scan_script() -> None:
    text = _active_text()
    assert re.search(r"^\s+run:\s+python3 scripts/secret_scan\.py\s*$", text, re.M), text


def test_workflow_triggers_on_pull_request() -> None:
    text = _active_text()
    assert re.search(r"^on:\s*$", text, re.M)
    assert re.search(r"^\s+pull_request:\s*$", text, re.M)


def test_workflow_triggers_on_push_to_main() -> None:
    text = _active_text()
    assert "push:" in text
    on_block = re.search(
        r"^on:\s*\n(?P<body>.*?)(?=^[a-zA-Z])",
        text,
        re.M | re.S,
    )
    assert on_block is not None, "workflow missing on: trigger block"
    body = on_block.group("body")
    assert "push:" in body
    assert re.search(r"branches:\s*\n(?:[ \t].*\n)*[ \t]*-\s*main\b", body) or re.search(
        r"branches:\s*\[[^\]]*main",
        body,
    )


def test_workflow_filename_is_ship_gate_beat1740() -> None:
    assert WORKFLOW.name == "ship-gate-beat1740.yml"
    assert WORKFLOW.relative_to(REPO).as_posix() == (
        ".github/workflows/ship-gate-beat1740.yml"
    )
