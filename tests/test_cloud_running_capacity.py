"""Cloud floor: count RUNNING runStatus only; must-launch under N.

Directors must spawn Cursor Cloud specialists for playability/art work
when the RUNNING count for GCS_CLOUD_REPO is below GCS_CLOUD_MIN_RUNNING
(default 8). Agent status ACTIVE with runStatus FINISHED is leftover, not
a worker. Always print runStatus.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from test_cloud_launch import (
    EXAMPLE_REPO,
    FAKE_KEY,
    LAUNCH,
    MockCursorAPI,
    _run,
    _script_env,
)

REPO = Path(__file__).resolve().parents[1]
CAPACITY = REPO / "scripts" / "cloud" / "running_capacity.py"
RUNNING_SH = REPO / "scripts" / "cloud" / "running.sh"
MIND_PY = REPO / "scripts" / "directors" / "mind.py"
MIND_DOC = REPO / "docs" / "studio" / "MIND.md"
CLOUD_DOC = REPO / "docs" / "CLOUD.md"
FOOTER = REPO / "scripts" / "directors" / "common_footer.txt"
STUDIO_ENV = REPO / "studio.env.example"
ART_SOUL = REPO / "docs" / "studio" / "directors" / "souls" / "art" / "SOUL.md"
CONTENT_SOUL = REPO / "docs" / "studio" / "directors" / "souls" / "content" / "SOUL.md"
FLOOR_SOUL = REPO / "docs" / "studio" / "directors" / "souls" / "floor" / "SOUL.md"
CLOUD_README = REPO / "scripts" / "cloud" / "README.md"

OTHER_REPO = "https://github.com/example/other-game"


def _load_capacity() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gcs_running_capacity", CAPACITY)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gcs_running_capacity"] = mod
    spec.loader.exec_module(mod)
    return mod


def _agent(
    *,
    agent_id: str,
    name: str,
    agent_status: str,
    run_id: str,
    run_status: str,
    repo: str = EXAMPLE_REPO,
) -> dict:
    return {
        "id": agent_id,
        "name": name,
        "status": agent_status,
        "url": f"https://cursor.com/agents/{agent_id}",
        "latestRunId": run_id,
        "runStatus": run_status,
        "repos": [{"url": repo, "startingRef": "main"}],
    }


def test_active_finished_leftovers_are_not_running_workers() -> None:
    mod = _load_capacity()
    leftover = _agent(
        agent_id="bc-done",
        name="art-old",
        agent_status="ACTIVE",
        run_id="run-done",
        run_status="FINISHED",
    )
    live = _agent(
        agent_id="bc-live",
        name="art-now",
        agent_status="ACTIVE",
        run_id="run-live",
        run_status="RUNNING",
    )
    other = _agent(
        agent_id="bc-other",
        name="other-live",
        agent_status="ACTIVE",
        run_id="run-other",
        run_status="RUNNING",
        repo=OTHER_REPO,
    )
    creating = _agent(
        agent_id="bc-boot",
        name="art-boot",
        agent_status="ACTIVE",
        run_id="run-boot",
        run_status="CREATING",
    )
    rows = mod.annotate_agents(
        [leftover, live, other, creating],
        repo=EXAMPLE_REPO,
        run_by_id={
            "run-done": "FINISHED",
            "run-live": "RUNNING",
            "run-other": "RUNNING",
            "run-boot": "CREATING",
        },
    )
    count = mod.count_running(rows)
    assert count == 1
    printed = "\n".join(mod.format_rows(rows))
    assert "runStatus=FINISHED" in printed
    assert "runStatus=RUNNING" in printed
    assert "agentStatus=ACTIVE" in printed
    assert "bc-done" in printed
    assert "bc-live" in printed
    assert "bc-other" not in printed


def test_must_launch_when_playability_art_below_default_floor() -> None:
    mod = _load_capacity()
    assert mod.DEFAULT_MIN_RUNNING == 8
    assert mod.must_launch_cloud_floor(
        work_kind="playability",
        prompt="",
        running_count=3,
        min_running=8,
    )
    assert mod.must_launch_cloud_floor(
        work_kind="art",
        prompt="paint the town tileset",
        running_count=0,
    )
    assert mod.must_launch_cloud_floor(
        work_kind="",
        prompt="Playability pass on the hub loop",
        running_count=7,
        min_running=8,
    )
    assert not mod.must_launch_cloud_floor(
        work_kind="playability",
        prompt="",
        running_count=8,
        min_running=8,
    )
    assert not mod.must_launch_cloud_floor(
        work_kind="qa",
        prompt="squash-merge odd PRs",
        running_count=0,
        min_running=8,
    )


def test_running_sh_prints_runstatus_and_must_launch(tmp_path: Path) -> None:
    leftovers = [
        _agent(
            agent_id="bc-old",
            name="leftover",
            agent_status="ACTIVE",
            run_id="run-old",
            run_status="FINISHED",
        ),
        _agent(
            agent_id="bc-live",
            name="worker",
            agent_status="ACTIVE",
            run_id="run-live",
            run_status="RUNNING",
        ),
    ]
    with MockCursorAPI(list_items=leftovers) as api:
        api.run_status_by_run_id = {"run-old": "FINISHED", "run-live": "RUNNING"}
        env = _script_env(
            tmp_path,
            api.base,
            CURSOR_API_KEY=FAKE_KEY,
            GCS_CLOUD_MIN_RUNNING="8",
        )
        proc = _run(
            RUNNING_SH,
            ["--work-kind", "playability"],
            env,
        )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "runStatus=FINISHED" in proc.stdout
    assert "runStatus=RUNNING" in proc.stdout
    assert "agentStatus=ACTIVE" in proc.stdout
    assert "CLOUD_RUNNING count=1" in proc.stdout
    assert "CLOUD_MUST_LAUNCH=1" in proc.stdout
    assert FAKE_KEY not in blob


def test_running_sh_at_floor_does_not_must_launch(tmp_path: Path) -> None:
    items = [
        _agent(
            agent_id=f"bc-{i}",
            name=f"w{i}",
            agent_status="ACTIVE",
            run_id=f"run-{i}",
            run_status="RUNNING",
        )
        for i in range(8)
    ]
    with MockCursorAPI(list_items=items) as api:
        api.run_status_by_run_id = {f"run-{i}": "RUNNING" for i in range(8)}
        proc = _run(
            RUNNING_SH,
            ["--work-kind", "art"],
            _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY),
        )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "CLOUD_RUNNING count=8" in proc.stdout
    assert "CLOUD_MUST_LAUNCH=0" in proc.stdout


def test_hard_rule_is_in_footer_mind_and_playability_seats() -> None:
    footer = FOOTER.read_text(encoding="utf-8")
    mind = MIND_DOC.read_text(encoding="utf-8")
    cloud = CLOUD_DOC.read_text(encoding="utf-8")
    readme = CLOUD_README.read_text(encoding="utf-8")
    studio = STUDIO_ENV.read_text(encoding="utf-8")
    art = ART_SOUL.read_text(encoding="utf-8")
    content = CONTENT_SOUL.read_text(encoding="utf-8")
    floor = FLOOR_SOUL.read_text(encoding="utf-8")
    blob = "\n".join((footer, mind, cloud, readme, studio, art, content, floor))
    low = blob.lower()
    assert "runstatus" in low
    assert "gcs_cloud_min_running" in low
    assert "8" in blob
    assert "must" in low and "launch" in low
    assert "playability" in low
    assert "finished" in low
    assert "running.sh" in low or "running_capacity" in low
    assert "do not burn" in low or "burn grok" in low or "instead of spawning" in low
    for text, label in ((footer, "footer"), (mind, "MIND.md"), (art, "art"), (floor, "floor")):
        assert "launch-cloud-extra-high.sh" in text, label
        assert "RUNNING" in text, label
    mind_src = MIND_PY.read_text(encoding="utf-8")
    assert "cloud_running" in mind_src
    assert "GCS_CLOUD_MIN_RUNNING" in studio


def test_cloud_running_plugin_exists() -> None:
    spec = importlib.util.spec_from_file_location("gcs_mind_running", MIND_PY)
    assert spec is not None and spec.loader is not None
    mind = importlib.util.module_from_spec(spec)
    sys.modules["gcs_mind_running"] = mind
    spec.loader.exec_module(mind)
    assert "cloud_running" in mind.PLUGINS


def test_launch_script_still_creates_when_floor_open(tmp_path: Path) -> None:
    """Capacity helper does not block an explicit launch."""
    with MockCursorAPI(create_http=201) as api:
        proc = _run(
            LAUNCH,
            ["--name", "floor-play", "Playability pass. Open a PR."],
            _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY),
        )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "CLOUD_LAUNCH_OK" in proc.stdout
