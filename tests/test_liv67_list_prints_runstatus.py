"""LIV-67: list.sh prints latest-run runStatus (not leftover ACTIVE).

Gherkin: tests/features/liv67_list_prints_runstatus.feature
Living Sky only. Never Bot CloudAgent. Does not remint list twins
#29/#44/#50/#55/#60/#68/#69 extras (--repo, --running, MUST_LAUNCH, …).
"""
from __future__ import annotations

from pathlib import Path

from liv_list_bdd import (
    CLOUD,
    FAKE_KEY,
    FEATURE_67,
    LIST_LONG,
    LIST_SH,
    LIST_TS,
    PRIVATE_GAME,
    REPO,
    SIBLING_NEEDLES,
    leftover_and_live_items,
    list_row,
    list_source_blob,
    run_list,
)
from test_cloud_launch import MockCursorAPI, _run, _script_env


def test_liv67_feature_file_is_the_living_spec() -> None:
    text = FEATURE_67.read_text(encoding="utf-8")
    fold = " ".join(text.lower().split())
    assert FEATURE_67.is_file()
    assert "LIV-67" in text
    assert "runStatus" in text
    assert "RUNNING" in text and "FINISHED" in text
    assert "existence is not liveness" in fold
    assert "living sky" in fold
    assert "bot cloudagent" in fold
    assert PRIVATE_GAME not in text
    assert "Scenario:" in text
    assert "Given " in text and "When " in text and "Then " in text
    assert "#29" in text or "#44" in text


def test_list_prints_run_status_so_finished_leftovers_are_not_spinning(
    tmp_path: Path,
) -> None:
    """ACTIVE leftover agents with a FINISHED run must not look like live workers."""
    items = leftover_and_live_items()
    api, listed, long_name = run_list(
        tmp_path,
        items,
        run_status_by_id={"run-done": "FINISHED", "run-live": "RUNNING"},
    )
    assert listed.returncode == 0, listed.stdout + listed.stderr
    assert long_name.returncode == 0, long_name.stdout + long_name.stderr
    leftover = list_row(listed.stdout, "bc-leftover")
    live = list_row(listed.stdout, "bc-live")
    idle = list_row(listed.stdout, "bc-idle")
    assert "status=ACTIVE" in leftover
    assert "runStatus=FINISHED" in leftover
    assert "runStatus=RUNNING" not in leftover
    assert "status=ACTIVE" in live
    assert "runStatus=RUNNING" in live
    assert "runStatus=FINISHED" not in live
    assert "runStatus=none" in idle
    long_leftover = list_row(long_name.stdout, "bc-leftover")
    long_live = list_row(long_name.stdout, "bc-live")
    assert "runStatus=FINISHED" in long_leftover
    assert "runStatus=RUNNING" in long_live
    assert any(path.endswith("/runs/run-done") for path in api.gets), api.gets
    assert any(path.endswith("/runs/run-live") for path in api.gets), api.gets
    blob = listed.stdout + listed.stderr + long_name.stdout + long_name.stderr
    assert FAKE_KEY not in blob
    assert PRIVATE_GAME not in blob


def test_list_run_not_found_prints_run_status_none(tmp_path: Path) -> None:
    items = [
        {
            "id": "bc-stale-id",
            "name": "ghost-run",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-stale-id",
            "latestRunId": "run-missing",
        }
    ]
    with MockCursorAPI(list_items=items, run_not_found_ids={"run-missing"}) as api:
        env = _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY)
        listed = _run(LIST_SH, [], env)
    assert listed.returncode == 0, listed.stdout + listed.stderr
    row = list_row(listed.stdout, "bc-stale-id")
    assert "status=ACTIVE" in row
    assert "runStatus=none" in row
    assert any(path.endswith("/runs/run-missing") for path in api.gets), api.gets
    assert FAKE_KEY not in listed.stdout + listed.stderr


def test_sdk_list_prints_run_status_on_each_row() -> None:
    src = LIST_TS.read_text(encoding="utf-8")
    assert "runStatus=" in src
    assert "mapRunStatus" in src
    assert "listRuns" in src or "getRun" in src
    assert "status=${status}" in src or 'status=${status}' in src or "status=${" in src
    assert "Bot CloudAgent" not in src
    assert PRIVATE_GAME not in src


def test_list_cli_does_not_remint_sibling_list_prs() -> None:
    blob = list_source_blob()
    for needle in SIBLING_NEEDLES:
        assert needle not in blob, needle
    assert "agent.send" not in LIST_TS.read_text(encoding="utf-8")
    assert LIST_SH.is_file()
    assert LIST_LONG.is_file()
    readme = (CLOUD / "README.md").read_text(encoding="utf-8")
    cloud_doc = (REPO / "docs" / "CLOUD.md").read_text(encoding="utf-8")
    assert "runStatus" in readme
    assert "runStatus" in cloud_doc
    assert "grok-4.6" in (REPO / "docs" / "CLOUD.md").read_text(encoding="utf-8")
    assert "xhigh" in cloud_doc
    assert "fast=false" in cloud_doc
    footer = (REPO / "scripts" / "directors" / "common_footer.txt").read_text(
        encoding="utf-8"
    )
    assert "runStatus" in footer
    assert "liveness" in footer.lower()
