"""gcs-list-sh-runstatus-beat1740: list rows print latest runStatus, not leftover ACTIVE.

REST mock list output must include runStatus= for each row. Agent membership
stays ACTIVE until archive; execution state lives on the latest run
(RUNNING / FINISHED / CANCELLED / …).
"""
from __future__ import annotations

from pathlib import Path

from test_cloud_launch import CLOUD, FAKE_KEY, MockCursorAPI, _run, _script_env


def _list_row(stdout: str, agent_id: str) -> str:
    matching = [line for line in stdout.splitlines() if agent_id in line]
    assert matching, stdout
    return matching[0]


def test_list_rest_rows_include_runstatus_not_leftover_active(tmp_path: Path) -> None:
    """ACTIVE leftover + FINISHED run must print runStatus=FINISHED, not look RUNNING."""
    items = [
        {
            "id": "bc-leftover",
            "name": "gcs-list-sh-runstatus-beat1740-done",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-leftover",
            "latestRunId": "run-done",
        },
        {
            "id": "bc-live",
            "name": "gcs-list-sh-runstatus-beat1740-live",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-live",
            "latestRunId": "run-live",
        },
        {
            "id": "bc-cancelled",
            "name": "gcs-list-sh-runstatus-beat1740-cancelled",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-cancelled",
            "latestRunId": "run-cancelled",
        },
        {
            "id": "bc-idle",
            "name": "gcs-list-sh-runstatus-beat1740-idle",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-idle",
            "latestRunId": "",
        },
    ]
    with MockCursorAPI(
        list_items=items,
        run_status_by_id={
            "run-done": "FINISHED",
            "run-live": "RUNNING",
            "run-cancelled": "CANCELLED",
        },
    ) as api:
        env = _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY)
        listed = _run(CLOUD / "list.sh", [], env)
        via_alias = _run(CLOUD / "list-cloud-agents.sh", [], env)
    assert listed.returncode == 0, listed.stdout + listed.stderr
    assert via_alias.returncode == 0, via_alias.stdout + via_alias.stderr

    leftover = _list_row(listed.stdout, "bc-leftover")
    live = _list_row(listed.stdout, "bc-live")
    cancelled = _list_row(listed.stdout, "bc-cancelled")
    idle = _list_row(listed.stdout, "bc-idle")

    assert "runStatus=" in leftover
    assert "runStatus=" in live
    assert "runStatus=" in cancelled
    assert "runStatus=" in idle

    assert "runStatus=FINISHED" in leftover
    assert "runStatus=ACTIVE" not in leftover
    assert "runStatus=RUNNING" not in leftover

    assert "runStatus=RUNNING" in live
    assert "runStatus=FINISHED" not in live
    assert "runStatus=ACTIVE" not in live

    assert "runStatus=CANCELLED" in cancelled
    assert "runStatus=ACTIVE" not in cancelled

    assert "runStatus=none" in idle

    assert any(path.endswith("/runs/run-done") for path in api.gets), api.gets
    assert any(path.endswith("/runs/run-live") for path in api.gets), api.gets
    assert any(path.endswith("/runs/run-cancelled") for path in api.gets), api.gets
    assert FAKE_KEY not in listed.stdout + listed.stderr
    assert FAKE_KEY not in via_alias.stdout + via_alias.stderr
    assert "runStatus=FINISHED" in via_alias.stdout
    assert "runStatus=RUNNING" in via_alias.stdout


def test_list_missing_run_prints_runstatus_none(tmp_path: Path) -> None:
    items = [
        {
            "id": "bc-stale-id",
            "name": "gcs-list-sh-runstatus-beat1740-ghost",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-stale-id",
            "latestRunId": "run-missing",
        }
    ]
    with MockCursorAPI(list_items=items, run_not_found_ids={"run-missing"}) as api:
        env = _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY)
        listed = _run(CLOUD / "list.sh", [], env)
    assert listed.returncode == 0, listed.stdout + listed.stderr
    row = _list_row(listed.stdout, "bc-stale-id")
    assert "runStatus=none" in row
    assert "runStatus=ACTIVE" not in row
    assert any(path.endswith("/runs/run-missing") for path in api.gets), api.gets
    assert FAKE_KEY not in listed.stdout + listed.stderr


def test_sdk_list_ts_prints_runstatus_via_listruns() -> None:
    """SDK list path must emit runStatus from listRuns, not only agent status."""
    src = (CLOUD / "sdk" / "list.ts").read_text(encoding="utf-8")
    assert "runStatus=" in src
    assert "mapRunStatus" in src
    assert "listRuns" in src
    assert "collectResult" not in src
    assert 'from "./status.ts"' not in src
    assert 'from "./collect.ts"' not in src
