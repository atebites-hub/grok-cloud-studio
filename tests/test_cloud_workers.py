"""Live Extra High workers: runStatus on list, not leftover ACTIVE.

Floor must see RUNNING vs FINISHED and must not treat leftover ACTIVE shells
as capacity. Staff GCS_CLOUD_REPO until >=8 RUNNING. Model grok-4.6 xhigh only.
Never Grok Bot CloudAgent.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from test_cloud_launch import (
    CLOUD,
    EXAMPLE_REPO,
    FAKE_KEY,
    NON_GROK_CURSOR_CLOUD_MODELS,
    MockCursorAPI,
    _run,
    _script_env,
)

REPO = Path(__file__).resolve().parents[1]
LIST_ROWS = REPO / "scripts" / "cloud" / "list_rows.py"
EXTRA_HIGH = REPO / "scripts" / "cloud" / "extra_high_model.py"
CAPACITY = REPO / "scripts" / "cloud" / "capacity.py"
RUNNING_COUNT = REPO / "scripts" / "cloud" / "running-count.sh"
LIST_TS = CLOUD / "sdk" / "list.ts"
LAUNCH_TS = CLOUD / "sdk" / "launch.ts"
COMMON_TS = CLOUD / "sdk" / "common.ts"
FOOTER = REPO / "scripts" / "directors" / "common_footer.txt"
README = REPO / "README.md"
CLOUD_DOC = REPO / "docs" / "CLOUD.md"
CLOUD_README = CLOUD / "README.md"
MIND_DOC = REPO / "docs" / "studio" / "MIND.md"
FLOOR_SOUL = REPO / "docs" / "studio" / "directors" / "souls" / "floor" / "SOUL.md"
CLOUD_SOUL = REPO / "docs" / "studio" / "directors" / "souls" / "cloud" / "SOUL.md"
FLOOR_PROMPT = REPO / "prompts" / "floor_director_prompt.txt"
CLOUD_PROMPT = REPO / "prompts" / "cloud_director_prompt.txt"
OTHER_REPO = "https://github.com/example/other-game"

BOT_CLOUDAGENT = "Grok Bot " + "CloudAgent"


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _list_row(stdout: str, agent_id: str) -> str:
    rows = [line for line in stdout.splitlines() if f"id={agent_id}" in line or agent_id in line]
    assert rows, stdout
    return rows[0]


def test_list_rows_parser_distinguishes_running_from_leftover_active() -> None:
    rows_mod = _load(LIST_ROWS, "gcs_list_rows")
    leftover = rows_mod.parse_list_output(
        "id=bc-leftover status=ACTIVE runStatus=FINISHED model=grok-4.6 "
        "name=done url=https://cursor.com/agents/bc-leftover latestRunId=run-done\n"
        "id=bc-live status=ACTIVE runStatus=RUNNING model=grok-4.6 "
        "name=busy url=https://cursor.com/agents/bc-live latestRunId=run-live\n"
        "id=bc-idle status=ACTIVE runStatus=none model=none "
        "name=idle url=https://cursor.com/agents/bc-idle latestRunId=\n"
    )
    assert [r["id"] for r in leftover] == ["bc-leftover", "bc-live", "bc-idle"]
    assert leftover[0]["status"] == "ACTIVE"
    assert leftover[0]["runStatus"] == "FINISHED"
    assert leftover[1]["runStatus"] == "RUNNING"
    assert leftover[2]["runStatus"] == "none"
    assert leftover[0]["model"] == "grok-4.6"
    assert rows_mod.is_live_worker(leftover[0]) is False
    assert rows_mod.is_live_worker(leftover[1]) is True
    assert rows_mod.is_live_worker(leftover[2]) is False


def test_list_prints_run_status_so_finished_leftovers_are_not_spinning(tmp_path: Path) -> None:
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
        run_model_by_id={
            "run-done": {"id": "grok-4.6"},
            "run-live": {"id": "grok-4.6"},
        },
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
    assert "model=grok-4.6" in leftover
    assert "status=ACTIVE" in live
    assert "runStatus=RUNNING" in live
    assert "runStatus=FINISHED" not in live
    assert "model=grok-4.6" in live
    assert "runStatus=none" in idle
    assert "model=none" in idle
    assert any(path.endswith("/runs/run-done") for path in api.gets), api.gets
    assert any(path.endswith("/runs/run-live") for path in api.gets), api.gets
    assert FAKE_KEY not in listed.stdout + listed.stderr


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
        listed = _run(CLOUD / "list-cloud-agents.sh", [], env)
    assert listed.returncode == 0, listed.stdout + listed.stderr
    row = _list_row(listed.stdout, "bc-stale-id")
    assert "status=ACTIVE" in row
    assert "runStatus=none" in row
    assert "model=none" in row
    assert any(path.endswith("/runs/run-missing") for path in api.gets), api.gets
    assert FAKE_KEY not in listed.stdout + listed.stderr


def test_list_prints_model_none_when_api_omits_it(tmp_path: Path) -> None:
    items = [
        {
            "id": "bc-nomodel",
            "name": "opaque",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-nomodel",
            "latestRunId": "run-opaque",
        }
    ]
    with MockCursorAPI(
        list_items=items,
        run_status_by_id={"run-opaque": "RUNNING"},
    ) as api:
        env = _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY)
        listed = _run(CLOUD / "list.sh", [], env)
    assert listed.returncode == 0, listed.stdout + listed.stderr
    row = _list_row(listed.stdout, "bc-nomodel")
    assert "runStatus=RUNNING" in row
    assert "model=none" in row


def test_sdk_list_prints_run_status_and_model_tokens() -> None:
    src = LIST_TS.read_text(encoding="utf-8")
    assert "runStatus=" in src
    assert "mapRunStatus" in src
    assert "listRuns" in src or "getRun" in src
    assert "model=" in src


def test_extra_high_model_accepts_grok_and_rejects_auto() -> None:
    mod = _load(EXTRA_HIGH, "gcs_extra_high_model")
    assert mod.is_extra_high_model("grok-4.6") is True
    assert mod.is_extra_high_model("cursor-grok-4.6-xhigh") is True
    assert mod.is_extra_high_model("") is True
    assert mod.is_extra_high_model(None) is True
    assert mod.is_extra_high_model("claude-4-sonnet") is False
    assert mod.is_extra_high_model("auto") is False
    assert mod.is_extra_high_model("gemini-2.5-pro") is False
    ok, found = mod.create_response_ok({"agent": {"id": "bc-1"}, "run": {"id": "run-1"}})
    assert ok is True
    assert found == ""
    ok, found = mod.create_response_ok({"model": {"id": "claude-4-sonnet"}})
    assert ok is False
    assert found == "claude-4-sonnet"
    pin = mod.extra_high_model_object()
    assert pin["id"] == "grok-4.6"
    params = {(p["id"], p["value"]) for p in pin["params"]}
    assert ("effort", "xhigh") in params
    assert ("fast", "false") in params


def test_cursor_cloud_model_env_rejects_non_grok_and_pin_stays_hardcoded(
    monkeypatch,
) -> None:
    mod = _load(EXTRA_HIGH, "gcs_extra_high_env")
    monkeypatch.delenv("CURSOR_CLOUD_MODEL", raising=False)
    ok, found = mod.cursor_cloud_model_env_ok()
    assert ok is True
    assert found == ""
    monkeypatch.setenv("CURSOR_CLOUD_MODEL", "grok-4.6")
    ok, found = mod.cursor_cloud_model_env_ok()
    assert ok is True
    assert found == "grok-4.6"
    for model_id in NON_GROK_CURSOR_CLOUD_MODELS:
        monkeypatch.setenv("CURSOR_CLOUD_MODEL", model_id)
        ok, found = mod.cursor_cloud_model_env_ok()
        assert ok is False, model_id
        assert found == model_id
        pin = mod.extra_high_model_object()
        assert pin["id"] == "grok-4.6", model_id
        try:
            mod.require_cursor_cloud_model_env()
        except ValueError as err:
            assert "CURSOR_CLOUD_MODEL" in str(err)
            assert model_id in str(err)
        else:
            raise AssertionError(f"expected reject for {model_id}")


def test_count_running_ignores_leftover_active_and_other_repos() -> None:
    cap = _load(CAPACITY, "gcs_cloud_capacity")
    rows = [
        {
            "id": "bc-leftover",
            "status": "ACTIVE",
            "runStatus": "FINISHED",
            "repo": EXAMPLE_REPO,
        },
        {
            "id": "bc-live",
            "status": "ACTIVE",
            "runStatus": "RUNNING",
            "repo": EXAMPLE_REPO,
        },
        {
            "id": "bc-creating",
            "status": "ACTIVE",
            "runStatus": "CREATING",
            "repo": EXAMPLE_REPO,
        },
        {
            "id": "bc-other",
            "status": "ACTIVE",
            "runStatus": "RUNNING",
            "repo": OTHER_REPO,
        },
        {
            "id": "bc-idle",
            "status": "ACTIVE",
            "runStatus": "none",
            "repo": EXAMPLE_REPO,
        },
    ]
    assert cap.DEFAULT_MIN_RUNNING == 8
    assert cap.count_running(rows, repo=EXAMPLE_REPO) == 1
    assert cap.count_in_flight(rows, repo=EXAMPLE_REPO) == 2
    leftover = next(r for r in rows if r["id"] == "bc-leftover")
    assert leftover["status"] == "ACTIVE"
    assert cap.is_live_worker(leftover) is False
    assert cap.must_launch(running_count=0) is True
    assert cap.must_launch(running_count=7) is True
    assert cap.must_launch(running_count=8) is False


def test_running_count_must_launch_below_eight(tmp_path: Path) -> None:
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
        {
            "id": "bc-other",
            "name": "other-repo",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-other",
            "latestRunId": "run-other",
            "repos": [{"url": OTHER_REPO}],
        },
    ]
    with MockCursorAPI(
        list_items=items,
        run_status_by_id={
            "run-done": "FINISHED",
            "run-live": "RUNNING",
            "run-other": "RUNNING",
        },
    ) as api:
        env = _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY)
        proc = _run(RUNNING_COUNT, ["--limit", "20"], env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "runStatus=FINISHED" in blob
    assert "runStatus=RUNNING" in blob
    assert "CLOUD_MUST_LAUNCH=1" in blob
    assert "CLOUD_RUNNING=1" in blob
    assert FAKE_KEY not in blob


def test_running_count_at_cap_does_not_must_launch(tmp_path: Path) -> None:
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
    assert "CLOUD_RUNNING=8" in blob
    assert FAKE_KEY not in blob


def test_directors_and_docs_require_live_workers_and_grok_only() -> None:
    footer = FOOTER.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    cloud_doc = CLOUD_DOC.read_text(encoding="utf-8")
    cloud_readme = CLOUD_README.read_text(encoding="utf-8")
    mind = MIND_DOC.read_text(encoding="utf-8")
    floor = FLOOR_SOUL.read_text(encoding="utf-8")
    cloud_soul = CLOUD_SOUL.read_text(encoding="utf-8")
    floor_prompt = FLOOR_PROMPT.read_text(encoding="utf-8")
    cloud_prompt = CLOUD_PROMPT.read_text(encoding="utf-8")
    blob = "\n".join(
        (
            footer,
            readme,
            cloud_doc,
            cloud_readme,
            mind,
            floor,
            cloud_soul,
            floor_prompt,
            cloud_prompt,
        )
    )
    low = blob.lower()
    assert "runstatus" in low
    assert "running" in low
    assert "8" in footer
    assert "GCS_CLOUD_MIN_RUNNING" in footer or "8 RUNNING" in footer
    assert "leftover" in low
    assert "ACTIVE" in footer or "active" in low
    assert BOT_CLOUDAGENT in readme
    assert "never" in readme.lower()
    assert "sonnet" in readme.lower() or "gemini" in readme.lower()
    assert "grok-4.6" in readme
    assert "xhigh" in readme.lower()
    assert "scripts/launch-cloud-extra-high.sh" in floor
    assert "scripts/launch-cloud-extra-high.sh" in cloud_soul
    assert "8" in floor or "RUNNING" in floor
    launch_ts = LAUNCH_TS.read_text(encoding="utf-8")
    common_ts = COMMON_TS.read_text(encoding="utf-8")
    assert BOT_CLOUDAGENT not in launch_ts
    assert "extraHighModel()" in launch_ts
    assert 'id: "grok-4.6"' in common_ts or "EXTRA_HIGH_MODEL_ID" in common_ts
    assert LIST_ROWS.is_file()
    assert EXTRA_HIGH.is_file()
    assert CAPACITY.is_file()
    assert RUNNING_COUNT.is_file()
    assert "hermes-agent" not in blob.lower()
