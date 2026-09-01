"""LIV-41 directors-spawn: playability below 8 RUNNING must launch Extra High.

Cloud mind MUST call scripts/launch-cloud-extra-high.sh when playability work
is in progress and the target repo has fewer than 8 in-flight runs
(runStatus RUNNING/CREATING). Leftover ACTIVE+FINISHED is not a worker.

Do not reuse --name gcs-liv41-mind-must-launch (already RUNNING).
Model grok-4.6 xhigh fast=false. Never Bot CloudAgent.
Linear = Living Sky (LIV).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parents[1]
SPAWN = REPO / "scripts" / "cloud" / "directors_spawn.py"
CLOUD_DOC = REPO / "docs" / "CLOUD.md"
LAUNCH = REPO / "scripts" / "launch-cloud-extra-high.sh"
EXAMPLE_REPO = "https://github.com/atebites-hub/grok-cloud-studio"
OTHER_REPO = "https://github.com/example/other"
RESERVED_NAME = "gcs-liv41-mind-must-launch"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gcs_directors_spawn", SPAWN)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _agent(
    *,
    name: str,
    run_status: str,
    repo: str = EXAMPLE_REPO,
    status: str = "ACTIVE",
    agent_id: str = "",
) -> dict:
    return {
        "id": agent_id or f"bc-{name}",
        "name": name,
        "status": status,
        "runStatus": run_status,
        "repos": [{"url": repo}],
    }


def test_leftover_active_finished_does_not_count_as_running() -> None:
    spawn = _load()
    rows = [
        _agent(name="leftover", run_status="FINISHED"),
        _agent(name="live", run_status="RUNNING"),
        _agent(name="booting", run_status="CREATING"),
        _agent(name="idle", run_status="none"),
    ]
    assert spawn.is_in_flight_run("FINISHED") is False
    assert spawn.is_in_flight_run("RUNNING") is True
    assert spawn.is_in_flight_run("CREATING") is True
    assert spawn.count_running_for_repo(rows, EXAMPLE_REPO) == 2


def test_running_count_is_per_target_repo() -> None:
    spawn = _load()
    rows = [
        _agent(name="here-live", run_status="RUNNING", repo=EXAMPLE_REPO),
        _agent(name="other-live", run_status="RUNNING", repo=OTHER_REPO),
        _agent(name="here-done", run_status="FINISHED", repo=EXAMPLE_REPO),
    ]
    assert spawn.count_running_for_repo(rows, EXAMPLE_REPO) == 1


def test_must_launch_only_when_playability_below_eight() -> None:
    spawn = _load()
    assert spawn.DEFAULT_MIN_RUNNING == 8
    assert spawn.work_is_playability("playability: camera juice") is True
    assert spawn.work_is_playability("rebase CI only") is False
    assert spawn.must_launch(work="playability hitboxes", running_count=0) is True
    assert spawn.must_launch(work="playability pass", running_count=7) is True
    assert spawn.must_launch(work="playability pass", running_count=8) is False
    assert spawn.must_launch(work="docs only", running_count=0) is False


def test_playability_below_8_cloud_mind_must_invoke_launcher() -> None:
    """Playability in progress + RUNNING count < 8 → launch-cloud-extra-high.sh.

    The reserved name gcs-liv41-mind-must-launch is already RUNNING, so the
    spawn MUST pick a different --name.
    """
    spawn = _load()
    recorded: list[list[str]] = []

    def fake_launch(argv: list[str]) -> str:
        recorded.append(list(argv))
        return "CLOUD_LAUNCH_OK id=bc-new"

    agents = [
        _agent(name=RESERVED_NAME, run_status="RUNNING"),
        _agent(name="leftover-shell", run_status="FINISHED"),
        _agent(name="other-game", run_status="RUNNING", repo=OTHER_REPO),
    ]
    result = spawn.cloud_mind_spawn_if_required(
        work="playability work is in progress on combat juice",
        agents=agents,
        repo=EXAMPLE_REPO,
        root=REPO,
        launch=fake_launch,
        requested_name=RESERVED_NAME,
    )
    assert result["launched"] is True
    assert recorded, result
    argv = recorded[0]
    blob = " ".join(argv)
    assert "launch-cloud-extra-high.sh" in blob
    assert "--name" in argv
    name = argv[argv.index("--name") + 1]
    assert name != RESERVED_NAME
    assert name.lower() not in {"donald", "orchestrator", "bot"}
    assert "bot cloudagent" not in blob.lower()
    assert RESERVED_NAME not in argv


def test_at_eight_running_does_not_launch() -> None:
    spawn = _load()
    recorded: list[list[str]] = []

    def fake_launch(argv: list[str]) -> str:
        recorded.append(list(argv))
        return "CLOUD_LAUNCH_OK"

    agents = [
        _agent(name=f"grunt-{i}", run_status="RUNNING") for i in range(7)
    ] + [_agent(name=RESERVED_NAME, run_status="RUNNING")]
    assert spawn.count_running_for_repo(agents, EXAMPLE_REPO) == 8
    result = spawn.cloud_mind_spawn_if_required(
        work="playability: remaining juice",
        agents=agents,
        repo=EXAMPLE_REPO,
        root=REPO,
        launch=fake_launch,
    )
    assert result["launched"] is False
    assert recorded == []


def test_non_playability_does_not_launch_even_when_empty() -> None:
    spawn = _load()
    recorded: list[list[str]] = []

    def fake_launch(argv: list[str]) -> str:
        recorded.append(list(argv))
        return "CLOUD_LAUNCH_OK"

    result = spawn.cloud_mind_spawn_if_required(
        work="STATUS ping / rebase CI",
        agents=[],
        repo=EXAMPLE_REPO,
        root=REPO,
        launch=fake_launch,
    )
    assert result["launched"] is False
    assert recorded == []


def test_never_spawns_bot_cloudagent_name() -> None:
    spawn = _load()
    recorded: list[list[str]] = []

    def fake_launch(argv: list[str]) -> str:
        recorded.append(list(argv))
        return "CLOUD_LAUNCH_OK"

    result = spawn.cloud_mind_spawn_if_required(
        work="playability: hub feel",
        agents=[],
        repo=EXAMPLE_REPO,
        root=REPO,
        launch=fake_launch,
        requested_name="donald",
        bot_agent_id="bot-agent-xyz",
    )
    assert result["launched"] is True
    argv = recorded[0]
    name = argv[argv.index("--name") + 1]
    assert name.lower() not in {"donald", "orchestrator"}
    assert name != "bot-agent-xyz"
    assert spawn.is_bot_cloudagent("donald") is True
    assert spawn.is_bot_cloudagent("orchestrator") is True
    assert spawn.is_bot_cloudagent("bot-agent-xyz", bot_agent_id="bot-agent-xyz") is True


def test_cloud_md_directors_spawn_law() -> None:
    text = CLOUD_DOC.read_text(encoding="utf-8")
    low = text.lower()
    assert "directors" in low and "spawn" in low
    assert "scripts/launch-cloud-extra-high.sh" in text
    assert "playability" in low
    assert "8" in text
    assert "running" in low
    assert "grok-4.6" in text
    assert "xhigh" in text
    assert "fast=false" in text.replace(" ", "")
    assert "bot cloudagent" in low
    assert "living sky" in low
    assert "liv" in low
    assert "black swan" not in low or "never" in low
    assert RESERVED_NAME in text
    launch = LAUNCH.read_text(encoding="utf-8")
    assert "grok-4.6" in launch
    assert "xhigh" in launch
    assert "fast=false" in launch
    assert SPAWN.is_file()
