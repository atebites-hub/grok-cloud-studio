"""Unit tests for cloud list row formatting (agent status vs runStatus)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cloud"))

from list_rows import format_list_row, normalize_run_status, unwrap_entity  # noqa: E402


def test_format_list_row_prints_run_status_token() -> None:
    row = format_list_row(
        agent_id="bc-leftover",
        agent_status="ACTIVE",
        run_status="FINISHED",
        name="done-grunt",
        url="https://cursor.com/agents/bc-leftover",
        run_id="run-done",
    )
    assert "status=ACTIVE" in row
    assert "runStatus=FINISHED" in row
    assert "runStatus=RUNNING" not in row
    assert row.startswith("id=bc-leftover ")


def test_normalize_run_status_uppercases_and_none() -> None:
    assert normalize_run_status("running") == "RUNNING"
    assert normalize_run_status("FINISHED") == "FINISHED"
    assert normalize_run_status("") == "none"
    assert normalize_run_status(None) == "none"


def test_unwrap_entity_run_wrapper() -> None:
    wrapped = {"run": {"id": "run-1", "status": "finished"}}
    run = unwrap_entity(wrapped, "run")
    assert run["id"] == "run-1"
    assert normalize_run_status(run.get("status")) == "FINISHED"
    bare = {"id": "run-2", "status": "RUNNING"}
    assert unwrap_entity(bare, "run") is bare
