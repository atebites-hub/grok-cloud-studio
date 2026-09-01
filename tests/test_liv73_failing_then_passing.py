"""LIV-73: failing-then-passing evidence for list runStatus (BDD in Action).

Gherkin: tests/features/liv73_failing_then_passing.feature
Same mock fleet: main-era TSV has no runStatus token (RED); list.sh after
LIV-67 prints runStatus=FINISHED vs RUNNING (GREEN). Directors paste that
pair, not leftover-green theatre.
"""
from __future__ import annotations

from pathlib import Path

from liv_list_bdd import (
    FAKE_KEY,
    FEATURE_73,
    PRIVATE_GAME,
    leftover_and_live_items,
    list_row,
    main_era_tsv_row,
    run_list,
)


def test_liv73_feature_file_is_the_living_spec() -> None:
    text = FEATURE_73.read_text(encoding="utf-8")
    fold = " ".join(text.lower().split())
    assert FEATURE_73.is_file()
    assert "LIV-73" in text
    assert "LIV-67" in text
    assert "failing-then-passing" in fold or "failing then passing" in fold
    assert "runStatus" in text
    assert "RED" in text and "GREEN" in text
    assert "living sky" in fold or "liv-73" in text
    assert "bot cloudagent" in fold
    assert PRIVATE_GAME not in text
    assert "Scenario:" in text


def test_liv73_red_main_era_tsv_has_no_runstatus_token() -> None:
    """RED: membership TSV on main cannot distinguish leftover from live."""
    items = leftover_and_live_items()
    leftover = main_era_tsv_row(items[0])
    live = main_era_tsv_row(items[1])
    assert leftover.startswith("bc-leftover\tACTIVE\t")
    assert live.startswith("bc-live\tACTIVE\t")
    assert "runStatus" not in leftover
    assert "runStatus" not in live
    assert "runStatus=FINISHED" not in leftover
    assert "runStatus=RUNNING" not in live
    assert leftover.split("\t")[1] == live.split("\t")[1] == "ACTIVE"


def test_liv73_green_same_fleet_prints_runstatus(tmp_path: Path) -> None:
    """GREEN: the same mock fleet prints runStatus after the LIV-67 fix."""
    items = leftover_and_live_items()
    red_leftover = main_era_tsv_row(items[0])
    red_live = main_era_tsv_row(items[1])
    assert "runStatus=" not in red_leftover
    assert "runStatus=" not in red_live
    api, listed, _long_name = run_list(
        tmp_path,
        items,
        run_status_by_id={"run-done": "FINISHED", "run-live": "RUNNING"},
    )
    assert listed.returncode == 0, listed.stdout + listed.stderr
    leftover = list_row(listed.stdout, "bc-leftover")
    live = list_row(listed.stdout, "bc-live")
    assert "runStatus=FINISHED" in leftover
    assert "runStatus=RUNNING" in live
    assert leftover != red_leftover
    assert live != red_live
    assert any(path.endswith("/runs/run-done") for path in api.gets), api.gets
    assert any(path.endswith("/runs/run-live") for path in api.gets), api.gets
    assert FAKE_KEY not in listed.stdout + listed.stderr
    assert PRIVATE_GAME not in listed.stdout
