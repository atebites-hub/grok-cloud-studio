"""Fleet capacity: RUNNING workers, not ACTIVE+FINISHED leftovers.

If playability/art work is in progress and in-flight Cursor Cloud count for
the target repo is below N (default 8), the cloud mind MUST launch.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from test_cloud_launch import (
    CLOUD,
    EXAMPLE_REPO,
    FAKE_KEY,
    MockCursorAPI,
    _run,
    _script_env,
)

REPO = Path(__file__).resolve().parents[1]
CAPACITY = REPO / "scripts" / "cloud" / "capacity.py"
RUNNING_COUNT = REPO / "scripts" / "cloud" / "running-count.sh"
FOOTER = REPO / "scripts" / "directors" / "common_footer.txt"
MIND_DOC = REPO / "docs" / "studio" / "MIND.md"
LIST_TS = REPO / "scripts" / "cloud" / "sdk" / "list.ts"
ART_SOUL = REPO / "docs" / "studio" / "directors" / "souls" / "art" / "SOUL.md"
FLOOR_SOUL = REPO / "docs" / "studio" / "directors" / "souls" / "floor" / "SOUL.md"


def _load():
    spec = importlib.util.spec_from_file_location("gcs_cloud_capacity", CAPACITY)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _list_row(stdout: str, agent_id: str) -> str:
    rows = [line for line in stdout.splitlines() if agent_id in line]
    assert rows, stdout
    return rows[0]


def test_active_finished_leftovers_are_not_running_workers() -> None:
    cap = _load()
    rows = [
        {
            "id": "bc-leftover",
            "status": "ACTIVE",
            "runStatus": "FINISHED",
            "name": "done-grunt",
        },
        {
            "id": "bc-live",
            "status": "ACTIVE",
            "runStatus": "RUNNING",
            "name": "busy-grunt",
        },
        {
            "id": "bc-creating",
            "status": "ACTIVE",
            "runStatus": "CREATING",
            "name": "booting-grunt",
        },
        {
            "id": "bc-idle",
            "status": "ACTIVE",
            "runStatus": "none",
            "name": "no-run",
        },
    ]
    assert cap.is_in_flight_run("FINISHED") is False
    assert cap.is_in_flight_run("RUNNING") is True
    assert cap.count_in_flight(rows) == 2
    leftover = next(r for r in rows if r["id"] == "bc-leftover")
    assert leftover["status"] == "ACTIVE"
    assert cap.is_in_flight_run(leftover["runStatus"]) is False


def test_must_launch_when_playability_art_below_default_cap_8() -> None:
    cap = _load()
    assert cap.DEFAULT_RUNNING_CAP == 8
    assert cap.work_is_playability_or_art("playability pass on combat juice") is True
    assert cap.work_is_playability_or_art("Art: sprite sheets for the hub") is True
    assert cap.work_is_playability_or_art("rebase CI only") is False
    assert cap.must_launch_cloud(work="playability: hitboxes", running_count=0) is True
    assert cap.must_launch_cloud(work="art tileset pass", running_count=7) is True
    assert cap.must_launch_cloud(work="playability", running_count=8) is False
    assert cap.must_launch_cloud(work="playability", running_count=3, cap=3) is False
    assert cap.must_launch_cloud(work="docs only", running_count=0) is False


def test_must_launch_filters_running_count_to_target_repo() -> None:
    cap = _load()
    rows = [
        {
            "id": "bc-palemon-live",
            "status": "ACTIVE",
            "runStatus": "RUNNING",
            "repos": [{"url": EXAMPLE_REPO}],
        },
        {
            "id": "bc-other-live",
            "status": "ACTIVE",
            "runStatus": "RUNNING",
            "repos": [{"url": "https://github.com/example/other"}],
        },
        {
            "id": "bc-palemon-done",
            "status": "ACTIVE",
            "runStatus": "FINISHED",
            "repos": [{"url": EXAMPLE_REPO}],
        },
    ]
    n = cap.count_in_flight(rows, repo=EXAMPLE_REPO)
    assert n == 1
    assert cap.must_launch_cloud(
        work="playability",
        running_count=n,
        cap=8,
    )


def test_list_prints_run_status_so_finished_leftovers_are_not_spinning(tmp_path: Path) -> None:
    items = [
        {
            "id": "bc-leftover",
            "name": "done-grunt",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-leftover",
            "latestRunId": "run-done",
        },
        {
            "id": "bc-live",
            "name": "busy-grunt",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-live",
            "latestRunId": "run-live",
        },
        {
            "id": "bc-idle",
            "name": "no-run",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-idle",
            "latestRunId": "",
        },
    ]
    with MockCursorAPI(
        list_items=items,
        run_status_by_id={"run-done": "FINISHED", "run-live": "RUNNING"},
    ) as api:
        env = _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY)
        listed = _run(CLOUD / "list-cloud-agents.sh", [], env)
    assert listed.returncode == 0, listed.stdout + listed.stderr
    leftover = _list_row(listed.stdout, "bc-leftover")
    live = _list_row(listed.stdout, "bc-live")
    idle = _list_row(listed.stdout, "bc-idle")
    assert "status=ACTIVE" in leftover
    assert "runStatus=FINISHED" in leftover
    assert "runStatus=RUNNING" not in leftover
    assert "status=ACTIVE" in live
    assert "runStatus=RUNNING" in live
    assert "runStatus=none" in idle
    assert any(path.endswith("/runs/run-done") for path in api.gets), api.gets
    assert FAKE_KEY not in listed.stdout + listed.stderr


def test_running_count_must_launch_for_playability_below_cap(tmp_path: Path) -> None:
    items = [
        {
            "id": "bc-leftover",
            "name": "done-grunt",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-leftover",
            "latestRunId": "run-done",
            "repos": [{"url": EXAMPLE_REPO}],
        },
        {
            "id": "bc-live",
            "name": "busy-grunt",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-live",
            "latestRunId": "run-live",
            "repos": [{"url": EXAMPLE_REPO}],
        },
    ]
    with MockCursorAPI(
        list_items=items,
        run_status_by_id={"run-done": "FINISHED", "run-live": "RUNNING"},
    ) as api:
        env = _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY)
        proc = _run(
            RUNNING_COUNT,
            ["--work", "playability: camera feel"],
            env,
        )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "runStatus=FINISHED" in blob
    assert "runStatus=RUNNING" in blob
    assert "CLOUD_MUST_LAUNCH=1" in blob
    assert "CLOUD_RUNNING=" in blob or "running=" in blob.lower()
    assert FAKE_KEY not in blob


def test_running_count_does_not_must_launch_when_at_cap(tmp_path: Path) -> None:
    items = [
        {
            "id": f"bc-live-{i}",
            "name": f"grunt-{i}",
            "status": "ACTIVE",
            "url": f"https://cursor.com/agents/bc-live-{i}",
            "latestRunId": f"run-live-{i}",
            "repos": [{"url": EXAMPLE_REPO}],
        }
        for i in range(8)
    ]
    with MockCursorAPI(
        list_items=items,
        run_status_by_id={f"run-live-{i}": "RUNNING" for i in range(8)},
    ) as api:
        env = _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY)
        proc = _run(
            RUNNING_COUNT,
            ["--work", "art: hub sprites"],
            env,
        )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "CLOUD_MUST_LAUNCH=0" in blob
    assert FAKE_KEY not in blob


def test_sdk_list_and_docs_require_run_status_and_must_launch_rule() -> None:
    src = LIST_TS.read_text(encoding="utf-8")
    assert "runStatus=" in src
    assert "mapRunStatus" in src
    footer = FOOTER.read_text(encoding="utf-8")
    mind = MIND_DOC.read_text(encoding="utf-8")
    art = ART_SOUL.read_text(encoding="utf-8")
    floor = FLOOR_SOUL.read_text(encoding="utf-8")
    blob = footer + "\n" + mind + "\n" + art + "\n" + floor
    low = blob.lower()
    assert "runstatus" in low
    assert "must" in low and "launch" in low
    assert "8" in footer or "GCS_CLOUD_RUNNING_CAP" in footer
    assert "finished" in low
    assert "playability" in low
    assert "scripts/launch-cloud-extra-high.sh" in art
    assert "scripts/launch-cloud-extra-high.sh" in floor


def test_capacity_module_exists() -> None:
    assert CAPACITY.is_file()
    assert RUNNING_COUNT.is_file()
