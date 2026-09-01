"""Fleet floor: ≥8 RUNNING per repo; leftover ACTIVE is not a worker.

Directors must cloud_launch until the target repo has at least
GCS_CLOUD_MIN_RUNNING (default 8) in-flight runs. Count latest-run
runStatus (RUNNING/CREATING). Agent status ACTIVE + runStatus FINISHED
is leftover membership, not a spinning worker. Never Bot CloudAgent.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from test_cloud_launch import (
    CLOUD,
    EXAMPLE_REPO,
    FAKE_KEY,
    MockCursorAPI,
    _list_row,
    _run,
    _script_env,
)

REPO = Path(__file__).resolve().parents[1]
CAPACITY = REPO / "scripts" / "cloud" / "capacity.py"
RUNNING_COUNT = REPO / "scripts" / "cloud" / "running-count.sh"
FOOTER = REPO / "scripts" / "directors" / "common_footer.txt"
MIND_DOC = REPO / "docs" / "studio" / "MIND.md"
CLOUD_DOC = REPO / "docs" / "CLOUD.md"
CLOUD_README = REPO / "scripts" / "cloud" / "README.md"
A2A_DOC = REPO / "docs" / "A2A.md"
FLOOR_SOUL = REPO / "docs" / "studio" / "directors" / "souls" / "floor" / "SOUL.md"
CLOUD_SOUL = REPO / "docs" / "studio" / "directors" / "souls" / "cloud" / "SOUL.md"
ART_SOUL = REPO / "docs" / "studio" / "directors" / "souls" / "art" / "SOUL.md"
LAUNCH = REPO / "scripts" / "launch-cloud-extra-high.sh"
LIST_TS = REPO / "scripts" / "cloud" / "sdk" / "list.ts"
STATUS_TS = REPO / "scripts" / "cloud" / "sdk" / "status.ts"
COMMON_TS = REPO / "scripts" / "cloud" / "sdk" / "common.ts"
STUDIO_ENV = REPO / "studio.env.example"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gcs_cloud_capacity", CAPACITY)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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
    assert cap.is_in_flight_run("CREATING") is True
    assert cap.count_in_flight(rows) == 2
    leftover = next(r for r in rows if r["id"] == "bc-leftover")
    assert leftover["status"] == "ACTIVE"
    assert cap.is_in_flight_run(leftover["runStatus"]) is False


def test_must_launch_until_eight_running_per_repo() -> None:
    cap = _load()
    assert cap.DEFAULT_MIN_RUNNING == 8
    assert cap.must_launch_cloud(running_count=0) is True
    assert cap.must_launch_cloud(running_count=7) is True
    assert cap.must_launch_cloud(running_count=8) is False
    assert cap.must_launch_cloud(running_count=3, cap=3) is False
    assert cap.must_launch_cloud(running_count=2, cap=3) is True


def test_must_launch_filters_running_count_to_target_repo() -> None:
    cap = _load()
    rows = [
        {
            "id": "bc-here-live",
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
            "id": "bc-here-done",
            "status": "ACTIVE",
            "runStatus": "FINISHED",
            "repos": [{"url": EXAMPLE_REPO}],
        },
    ]
    n = cap.count_in_flight(rows, repo=EXAMPLE_REPO)
    assert n == 1
    assert cap.must_launch_cloud(running_count=n, cap=8) is True


def test_running_count_must_launch_below_floor(tmp_path: Path) -> None:
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
        proc = _run(RUNNING_COUNT, [], env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    leftover = _list_row(proc.stdout, "bc-leftover")
    live = _list_row(proc.stdout, "bc-live")
    assert "runStatus=FINISHED" in leftover
    assert "runStatus=RUNNING" in live
    assert "CLOUD_MUST_LAUNCH=1" in blob
    assert "CLOUD_RUNNING=" in blob
    assert FAKE_KEY not in blob


def test_running_count_does_not_must_launch_when_at_floor(tmp_path: Path) -> None:
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
        proc = _run(RUNNING_COUNT, [], env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "CLOUD_MUST_LAUNCH=0" in blob
    assert FAKE_KEY not in blob


def test_directors_pin_grok_46_xhigh_and_never_bot_cloudagent() -> None:
    footer = FOOTER.read_text(encoding="utf-8")
    launch = LAUNCH.read_text(encoding="utf-8")
    common = COMMON_TS.read_text(encoding="utf-8")
    mind = MIND_DOC.read_text(encoding="utf-8")
    a2a = A2A_DOC.read_text(encoding="utf-8")
    floor = FLOOR_SOUL.read_text(encoding="utf-8")
    cloud = CLOUD_SOUL.read_text(encoding="utf-8")
    art = ART_SOUL.read_text(encoding="utf-8")
    blob = "\n".join([footer, mind, a2a, floor, cloud, art])
    low = blob.lower()
    assert "grok-4.6" in launch
    assert "xhigh" in launch
    assert '"id": "grok-4.6"' in common or "grok-4.6" in common
    assert "xhigh" in common
    assert "grok-4.6" in footer and "xhigh" in footer
    assert "bot cloudagent" in low
    assert "runstatus" in footer.lower()
    assert "GCS_CLOUD_MIN_RUNNING" in footer or "8" in footer
    assert "cloud_launch" in footer or "launch-cloud-extra-high.sh" in footer
    assert "scripts/launch-cloud-extra-high.sh" in floor
    assert "scripts/launch-cloud-extra-high.sh" in cloud
    assert "scripts/launch-cloud-extra-high.sh" in art


def test_sdk_and_docs_require_run_status_and_running_floor() -> None:
    list_src = LIST_TS.read_text(encoding="utf-8")
    status_src = STATUS_TS.read_text(encoding="utf-8")
    footer = FOOTER.read_text(encoding="utf-8")
    readme = CLOUD_README.read_text(encoding="utf-8")
    cloud_doc = CLOUD_DOC.read_text(encoding="utf-8")
    studio = STUDIO_ENV.read_text(encoding="utf-8")
    assert "runStatus=" in list_src
    assert "mapRunStatus" in list_src
    assert "runStatus=" in status_src
    assert "runStatus" in readme
    assert "RUNNING" in readme
    assert "8" in footer or "GCS_CLOUD_MIN_RUNNING" in footer
    assert "GCS_CLOUD_MIN_RUNNING" in studio
    assert "runStatus" in cloud_doc
    assert CAPACITY.is_file()
    assert RUNNING_COUNT.is_file()
