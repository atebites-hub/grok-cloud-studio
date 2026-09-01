"""LIV-67: leftover agent ACTIVE + latest-run FINISHED is not the RUNNING floor.

Capacity beats (ACP_PING STATUS/CONTINUE) call scripts/cloud/capacity-count.sh
/ capacity_count.py. Existence is not liveness. Do not remint list.sh --running
(GCS #78 / #73 / #82). Never Bot CloudAgent. Living Sky LIV-67.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from test_cloud_launch import (
    CLOUD,
    EXAMPLE_REPO,
    FAKE_KEY,
    MockCursorAPI,
    REPO,
    _run,
    _script_env,
)

CAP_PY = CLOUD / "capacity_count.py"
CAP_SH = CLOUD / "capacity-count.sh"
LIST_SH = CLOUD / "list.sh"
LIST_LONG = CLOUD / "list-cloud-agents.sh"
LIST_TS = CLOUD / "sdk" / "list.ts"
LAUNCH_SH = REPO / "scripts" / "launch-cloud-extra-high.sh"
FOOTER = REPO / "scripts" / "directors" / "common_footer.txt"
CLOUD_DOC = REPO / "docs" / "CLOUD.md"
CLOUD_README = CLOUD / "README.md"
TICKER_PY = REPO / "scripts" / "a2a" / "host-ticker.py"
CLOCK_SH = REPO / "scripts" / "directors" / "host-clock-ticker.sh"

STUDIO_REPO = EXAMPLE_REPO
OTHER_REPO = "https://github.com/example/other-game"
STUDIO_SLUG = "atebites-hub/grok-cloud-studio"
OTHER_SLUG = "example/other-game"


def _load_capacity_count() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gcs_liv67_capacity_count", CAP_PY)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _row(
    *,
    agent_id: str,
    repo: str,
    run_status: str,
    agent_status: str = "ACTIVE",
    unbound: bool = False,
) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "id": agent_id,
        "status": agent_status,
        "agentStatus": agent_status,
        "runStatus": run_status,
    }
    if not unbound:
        rec["repo"] = repo
        rec["repos"] = [repo]
    return rec


def _fleet_items() -> list[dict[str, Any]]:
    return [
        {
            "id": "bc-leftover",
            "name": "done-grunt",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-leftover",
            "latestRunId": "run-done",
            "repos": [{"url": STUDIO_REPO, "startingRef": "main"}],
        },
        {
            "id": "bc-live",
            "name": "busy-grunt",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-live",
            "latestRunId": "run-live",
            "repos": [{"url": STUDIO_REPO, "startingRef": "main"}],
        },
        {
            "id": "bc-creating",
            "name": "boot-grunt",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-creating",
            "latestRunId": "run-creating",
            "repos": [{"url": STUDIO_REPO, "startingRef": "main"}],
        },
        {
            "id": "bc-other",
            "name": "other-live",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-other",
            "latestRunId": "run-other",
            "repos": [{"url": OTHER_REPO, "startingRef": "main"}],
        },
        {
            "id": "bc-unbound",
            "name": "no-repo",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-unbound",
            "latestRunId": "run-unbound",
        },
    ]


def _run_status_by_id() -> dict[str, str]:
    return {
        "run-done": "FINISHED",
        "run-live": "RUNNING",
        "run-creating": "CREATING",
        "run-other": "RUNNING",
        "run-unbound": "RUNNING",
    }


def test_capacity_count_helper_exists_for_beats() -> None:
    assert CAP_PY.is_file(), "capacity beats call scripts/cloud/capacity_count.py"
    assert CAP_SH.is_file(), "capacity beats call scripts/cloud/capacity-count.sh"


def test_leftover_active_finished_is_not_counted_toward_running_floor() -> None:
    """Example: three ACTIVE studio shells, only one latest-run RUNNING.

    Naive grep of agent status=ACTIVE would count leftover FINISHED + CREATING
    + live as the floor. Capacity beats must count only runStatus=RUNNING.
    """
    cap = _load_capacity_count()
    rows = [
        _row(agent_id="bc-leftover", repo=STUDIO_REPO, run_status="FINISHED"),
        _row(agent_id="bc-live", repo=STUDIO_REPO, run_status="RUNNING"),
        _row(agent_id="bc-creating", repo=STUDIO_REPO, run_status="CREATING"),
        _row(agent_id="bc-other", repo=OTHER_REPO, run_status="RUNNING"),
        _row(agent_id="bc-unbound", repo="", run_status="RUNNING", unbound=True),
    ]
    naive_active = sum(1 for row in rows if str(row.get("status") or "") == "ACTIVE")
    assert naive_active == 5

    running = cap.count_running_for_repo(rows, STUDIO_REPO)
    leftover = cap.count_leftover_active_finished_for_repo(rows, STUDIO_REPO)
    snap = cap.floor_snapshot(running, leftover_active=leftover)

    assert running == 1
    assert leftover == 1
    assert running != naive_active
    assert snap["must_launch"] == 1
    assert snap["floor"] == 8
    assert snap["deficit"] == 7
    assert cap.counts_toward_running_floor("ACTIVE", "FINISHED") is False
    assert cap.counts_toward_running_floor("ACTIVE", "RUNNING") is True
    assert cap.counts_toward_running_floor("ACTIVE", "CREATING") is False
    assert cap.counts_toward_running_floor("", "RUNNING") is True
    assert cap.counts_toward_running_floor("ACTIVE", "none") is False


def test_leftover_only_fleet_does_not_fill_the_floor() -> None:
    cap = _load_capacity_count()
    rows = [
        _row(agent_id="bc-leftover", repo=STUDIO_REPO, run_status="FINISHED"),
        _row(agent_id="bc-leftover-2", repo=STUDIO_REPO, run_status="FINISHED"),
    ]
    running = cap.count_running_for_repo(rows, STUDIO_REPO)
    leftover = cap.count_leftover_active_finished_for_repo(rows, STUDIO_REPO)
    snap = cap.floor_snapshot(running, leftover_active=leftover)
    assert running == 0
    assert leftover == 2
    assert snap["must_launch"] == 1
    assert snap["deficit"] == 8
    line = cap.format_capacity_line(STUDIO_SLUG, snap)
    assert "running=0" in line
    assert "leftover_active=2" in line
    assert "must_launch=1" in line
    assert line.startswith("CLOUD_CAPACITY ")


def test_at_floor_running_does_not_must_launch() -> None:
    cap = _load_capacity_count()
    rows = [
        _row(agent_id=f"bc-live-{i}", repo=STUDIO_REPO, run_status="RUNNING")
        for i in range(8)
    ]
    rows.append(_row(agent_id="bc-leftover", repo=STUDIO_REPO, run_status="FINISHED"))
    running = cap.count_running_for_repo(rows, STUDIO_REPO)
    leftover = cap.count_leftover_active_finished_for_repo(rows, STUDIO_REPO)
    snap = cap.floor_snapshot(running, leftover_active=leftover)
    assert running == 8
    assert leftover == 1
    assert snap["must_launch"] == 0
    assert snap["deficit"] == 0


def test_other_remote_running_does_not_count_toward_this_repo_floor() -> None:
    cap = _load_capacity_count()
    rows = [
        _row(agent_id="bc-other", repo=OTHER_REPO, run_status="RUNNING"),
        _row(agent_id="bc-leftover", repo=STUDIO_REPO, run_status="FINISHED"),
    ]
    assert cap.count_running_for_repo(rows, STUDIO_REPO) == 0
    assert cap.count_running_for_repo(rows, OTHER_REPO) == 1
    assert cap.count_running_for_repo(rows, STUDIO_SLUG) == 0


def test_capacity_count_sh_skips_leftover_active_finished(tmp_path: Path) -> None:
    items = _fleet_items()
    with MockCursorAPI(list_items=items, run_status_by_id=_run_status_by_id()) as api:
        env = _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY)
        env["GCS_CLOUD_REPO"] = STUDIO_REPO
        proc = _run(CAP_SH, ["--repo", STUDIO_SLUG], env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "CLOUD_CAPACITY" in proc.stdout
    assert f"repo={STUDIO_SLUG}" in proc.stdout
    assert "running=1" in proc.stdout
    assert "leftover_active=1" in proc.stdout
    assert "must_launch=1" in proc.stdout
    assert "running=3" not in proc.stdout
    assert "running=5" not in proc.stdout
    assert OTHER_SLUG not in proc.stdout
    assert FAKE_KEY not in blob
    assert any(path.endswith("/v1/agents/bc-leftover") for path in api.gets), api.gets
    assert any(path.endswith("/runs/run-done") for path in api.gets), api.gets
    assert any(path.endswith("/runs/run-live") for path in api.gets), api.gets


def test_capacity_count_leftover_only_cli_must_launch(tmp_path: Path) -> None:
    items = [
        {
            "id": "bc-leftover",
            "name": "done-grunt",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-leftover",
            "latestRunId": "run-done",
            "repos": [{"url": STUDIO_REPO}],
        }
    ]
    with MockCursorAPI(
        list_items=items,
        run_status_by_id={"run-done": "FINISHED"},
    ) as api:
        env = _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY)
        proc = _run(CAP_SH, ["--repo", STUDIO_REPO], env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "running=0" in proc.stdout
    assert "leftover_active=1" in proc.stdout
    assert "must_launch=1" in proc.stdout
    assert "deficit=8" in proc.stdout
    assert FAKE_KEY not in proc.stdout + proc.stderr


def test_does_not_remint_list_running() -> None:
    """GCS #78 / #73 / #82 own list --running / runStatus rows. This PR does not."""
    list_src = LIST_SH.read_text(encoding="utf-8") + LIST_LONG.read_text(encoding="utf-8")
    ts = LIST_TS.read_text(encoding="utf-8")
    assert "--running" not in list_src
    assert "--running" not in ts
    cap = CAP_PY.read_text(encoding="utf-8") + CAP_SH.read_text(encoding="utf-8")
    assert "list.sh --running" not in cap
    assert "MUST_LAUNCH" not in cap
    assert "running-count.sh" not in cap
    assert "cloud_capacity.py" not in cap


def test_beats_are_told_to_call_capacity_count() -> None:
    footer = FOOTER.read_text(encoding="utf-8")
    clock = CLOCK_SH.read_text(encoding="utf-8")
    ticker = TICKER_PY.read_text(encoding="utf-8")
    docs = CLOUD_DOC.read_text(encoding="utf-8") + CLOUD_README.read_text(encoding="utf-8")
    blob = "\n".join((footer, clock, ticker, docs))
    assert "capacity-count.sh" in blob
    assert "runStatus" in blob
    assert "ACTIVE" in blob
    assert "FINISHED" in blob
    assert "Bot CloudAgent" in blob or "Grok Bot CloudAgent" in blob
    assert "grok-4.6" in LAUNCH_SH.read_text(encoding="utf-8")
    assert "xhigh" in LAUNCH_SH.read_text(encoding="utf-8")


def test_capacity_count_help_and_missing_auth(tmp_path: Path) -> None:
    help_proc = subprocess.run(
        ["bash", str(CAP_SH), "--help"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env={
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": "/tmp",
            "LC_ALL": "C",
        },
        timeout=10,
    )
    blob = help_proc.stdout + help_proc.stderr
    assert help_proc.returncode == 0, blob
    assert "runStatus" in blob
    assert "RUNNING" in blob
    assert "ACTIVE" in blob
    with MockCursorAPI() as api:
        proc = _run(CAP_SH, ["--repo", STUDIO_SLUG], _script_env(tmp_path, api.base))
    assert proc.returncode != 0
    assert FAKE_KEY not in proc.stdout + proc.stderr
