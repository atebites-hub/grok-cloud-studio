"""Unit tests for cloud list row formatting (agent status vs runStatus)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "gcs_list_rows", ROOT / "scripts" / "cloud" / "list_rows.py"
)
assert _SPEC is not None and _SPEC.loader is not None
list_rows = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(list_rows)
format_list_row = list_rows.format_list_row
normalize_run_status = list_rows.normalize_run_status
unwrap_entity = list_rows.unwrap_entity


def test_format_list_row_prints_run_status_token() -> None:
    leftover = format_list_row(
        agent_id="bc-leftover",
        agent_status="ACTIVE",
        run_status="FINISHED",
        name="done-grunt",
        url="https://cursor.com/agents/bc-leftover",
        run_id="run-done",
    )
    live = format_list_row(
        agent_id="bc-live",
        agent_status="ACTIVE",
        run_status="RUNNING",
        name="busy-grunt",
        url="https://cursor.com/agents/bc-live",
        run_id="run-live",
    )
    assert "status=ACTIVE" in leftover
    assert "runStatus=FINISHED" in leftover
    assert "runStatus=RUNNING" not in leftover
    assert leftover.startswith("id=bc-leftover ")
    assert "status=ACTIVE" in live
    assert "runStatus=RUNNING" in live
    assert "runStatus=FINISHED" not in live


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
