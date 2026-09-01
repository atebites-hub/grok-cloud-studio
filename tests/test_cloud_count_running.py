"""count-running.sh: RUNNING counts per bound repo via runStatus, not ACTIVE.

LIV-41 / LIV-67 (Living Sky, not Black Swan). Leftover agent status=ACTIVE
is membership, not capacity. CREATING is not RUNNING. Never Bot CloudAgent.

Does not remint GCS #50 list --repo, #29 list runStatus rows, or #44
≥8 MUST_LAUNCH / running-count.sh / capacity.py.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from test_cloud_launch import (
    CLOUD,
    EXAMPLE_REPO,
    FAKE_KEY,
    MockCursorAPI,
    REPO,
    _run,
    _script_env,
)

COUNT_SH = CLOUD / "count-running.sh"
COUNT_PY = CLOUD / "count_running.py"
LIST_SH = CLOUD / "list.sh"
LIST_LONG = CLOUD / "list-cloud-agents.sh"
LIST_TS = CLOUD / "sdk" / "list.ts"
LAUNCH_SH = REPO / "scripts" / "launch-cloud-extra-high.sh"
LAUNCH_TS = CLOUD / "sdk" / "launch.ts"
FOOTER = REPO / "scripts" / "directors" / "common_footer.txt"
CLOUD_DOC = REPO / "docs" / "CLOUD.md"
CLOUD_README = CLOUD / "README.md"
A2A_DOC = REPO / "docs" / "A2A.md"

STUDIO_REPO = EXAMPLE_REPO
OTHER_REPO = "https://github.com/example/other-game"
STUDIO_SLUG = "atebites-hub/grok-cloud-studio"
OTHER_SLUG = "example/other-game"


def _load_count_running():
    sys.path.insert(0, str(CLOUD))
    import count_running

    return count_running


def _fleet_items() -> list[dict]:
    return [
        {
            "id": "bc-studio-live",
            "name": "studio-live",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-studio-live",
            "latestRunId": "run-studio-live",
            "repos": [{"url": STUDIO_REPO, "startingRef": "main"}],
        },
        {
            "id": "bc-studio-done",
            "name": "studio-done",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-studio-done",
            "latestRunId": "run-studio-done",
            "repos": [{"url": STUDIO_REPO, "startingRef": "main"}],
        },
        {
            "id": "bc-studio-creating",
            "name": "studio-creating",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-studio-creating",
            "latestRunId": "run-studio-creating",
            "repos": [{"url": STUDIO_REPO, "startingRef": "main"}],
        },
        {
            "id": "bc-other-live",
            "name": "other-live",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-other-live",
            "latestRunId": "run-other-live",
            "repos": [{"url": OTHER_REPO, "startingRef": "main"}],
        },
    ]


def _run_status_by_id() -> dict[str, str]:
    return {
        "run-studio-live": "RUNNING",
        "run-studio-done": "FINISHED",
        "run-studio-creating": "CREATING",
        "run-other-live": "RUNNING",
    }


def _running_line(stdout: str, slug: str) -> str:
    prefix = f"CLOUD_RUNNING repo={slug} "
    rows = [line for line in stdout.splitlines() if line.startswith(prefix)]
    assert rows, stdout
    return rows[0]


def test_repo_key_accepts_org_name_https_git_and_ssh() -> None:
    count_running = _load_count_running()
    key = count_running.repo_key
    assert key("atebites-hub/grok-cloud-studio") == STUDIO_SLUG
    assert key(STUDIO_REPO) == STUDIO_SLUG
    assert key(STUDIO_REPO + ".git") == STUDIO_SLUG
    assert key(STUDIO_REPO + "/") == STUDIO_SLUG
    assert key("git@github.com:atebites-hub/grok-cloud-studio.git") == STUDIO_SLUG
    assert key("github.com/atebites-hub/grok-cloud-studio") == STUDIO_SLUG
    assert key(OTHER_REPO) == OTHER_SLUG
    assert key(OTHER_REPO) != STUDIO_SLUG


def test_is_running_is_run_status_not_agent_active() -> None:
    count_running = _load_count_running()
    assert count_running.is_running("RUNNING") is True
    assert count_running.is_running("running") is True
    assert count_running.is_running("ACTIVE") is False
    assert count_running.is_running("FINISHED") is False
    assert count_running.is_running("CREATING") is False
    assert count_running.is_running("none") is False
    assert count_running.is_running("") is False


def test_count_running_by_repo_ignores_leftover_active() -> None:
    count_running = _load_count_running()
    counts = count_running.count_running_by_repo(
        [
            (STUDIO_SLUG, "RUNNING"),
            (STUDIO_SLUG, "FINISHED"),
            (STUDIO_SLUG, "CREATING"),
            (STUDIO_SLUG, "ACTIVE"),
            (OTHER_SLUG, "RUNNING"),
            ("", "RUNNING"),
        ]
    )
    assert counts[STUDIO_SLUG] == 1
    assert counts[OTHER_SLUG] == 1
    assert "" not in counts


def test_count_running_help_documents_per_repo_run_status() -> None:
    proc = subprocess.run(
        ["bash", str(COUNT_SH), "--help"],
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
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "--repo" in blob
    assert "runStatus" in blob
    assert "RUNNING" in blob
    assert "ACTIVE" in blob


def test_count_running_per_bound_repo_uses_run_status_not_active(tmp_path: Path) -> None:
    items = _fleet_items()
    with MockCursorAPI(list_items=items, run_status_by_id=_run_status_by_id()) as api:
        env = _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY)
        proc = _run(COUNT_SH, ["--limit", "20"], env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    studio = _running_line(proc.stdout, STUDIO_SLUG)
    other = _running_line(proc.stdout, OTHER_SLUG)
    assert "running=1" in studio
    assert "running=3" not in studio
    assert "running=2" not in studio
    assert "running=1" in other
    assert "MUST_LAUNCH" not in blob
    assert any(path.endswith("/v1/agents/bc-studio-live") for path in api.gets), api.gets
    assert any(path.endswith("/runs/run-studio-live") for path in api.gets), api.gets
    assert any(path.endswith("/runs/run-studio-done") for path in api.gets), api.gets
    assert FAKE_KEY not in blob


def test_count_running_repo_org_name_keeps_one_bound_remote(tmp_path: Path) -> None:
    items = _fleet_items()
    with MockCursorAPI(list_items=items, run_status_by_id=_run_status_by_id()) as api:
        env = _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY)
        proc = _run(COUNT_SH, ["--repo", STUDIO_SLUG], env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    studio = _running_line(proc.stdout, STUDIO_SLUG)
    assert "running=1" in studio
    assert OTHER_SLUG not in proc.stdout
    assert "bc-other-live" not in proc.stdout
    assert FAKE_KEY not in blob


def test_count_running_repo_https_url_and_git_suffix_match_org_name(tmp_path: Path) -> None:
    items = _fleet_items()
    with MockCursorAPI(list_items=items, run_status_by_id=_run_status_by_id()) as api:
        env = _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY)
        via_url = _run(COUNT_SH, ["--repo", STUDIO_REPO], env)
        via_git = _run(COUNT_SH, ["--repo", STUDIO_REPO + ".git", "--limit", "20"], env)
    assert via_url.returncode == 0, via_url.stdout + via_url.stderr
    assert via_git.returncode == 0, via_git.stdout + via_git.stderr
    for proc in (via_url, via_git):
        studio = _running_line(proc.stdout, STUDIO_SLUG)
        assert "running=1" in studio
        assert OTHER_SLUG not in proc.stdout


def test_count_running_repo_equals_form(tmp_path: Path) -> None:
    items = _fleet_items()
    with MockCursorAPI(list_items=items, run_status_by_id=_run_status_by_id()) as api:
        env = _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY)
        proc = _run(COUNT_SH, [f"--repo={STUDIO_SLUG}"], env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "running=1" in _running_line(proc.stdout, STUDIO_SLUG)
    assert OTHER_SLUG not in proc.stdout


def test_count_running_leftover_active_finished_is_zero(tmp_path: Path) -> None:
    items = [
        {
            "id": "bc-studio-done",
            "name": "studio-done",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-studio-done",
            "latestRunId": "run-studio-done",
            "repos": [{"url": STUDIO_REPO}],
        }
    ]
    with MockCursorAPI(
        list_items=items,
        run_status_by_id={"run-studio-done": "FINISHED"},
    ) as api:
        env = _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY)
        proc = _run(COUNT_SH, ["--repo", STUDIO_SLUG], env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    studio = _running_line(proc.stdout, STUDIO_SLUG)
    assert "running=0" in studio
    assert "running=1" not in studio
    assert FAKE_KEY not in proc.stdout + proc.stderr


def test_count_running_excludes_unbound_agents(tmp_path: Path) -> None:
    items = [
        {
            "id": "bc-unbound",
            "name": "no-repos",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-unbound",
            "latestRunId": "run-unbound",
        },
        {
            "id": "bc-studio-live",
            "name": "studio-live",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-studio-live",
            "latestRunId": "run-studio-live",
            "repos": [{"url": STUDIO_REPO}],
        },
    ]
    with MockCursorAPI(
        list_items=items,
        run_status_by_id={"run-unbound": "RUNNING", "run-studio-live": "RUNNING"},
    ) as api:
        env = _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY)
        proc = _run(COUNT_SH, ["--repo", STUDIO_SLUG], env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "running=1" in _running_line(proc.stdout, STUDIO_SLUG)
    assert "bc-unbound" not in proc.stdout


def test_count_running_falls_back_to_run_git_repo_url(tmp_path: Path) -> None:
    items = [
        {
            "id": "bc-git-only",
            "name": "git-only",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-git-only",
            "latestRunId": "run-git-only",
            "runGit": {
                "branches": [
                    {
                        "repoUrl": "github.com/atebites-hub/grok-cloud-studio",
                        "branch": "cursor/x",
                    }
                ]
            },
        },
        {
            "id": "bc-other-live",
            "name": "other-live",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-other-live",
            "latestRunId": "run-other-live",
            "repos": [{"url": OTHER_REPO}],
        },
    ]
    with MockCursorAPI(
        list_items=items,
        run_status_by_id={"run-git-only": "RUNNING", "run-other-live": "FINISHED"},
    ) as api:
        env = _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY)
        proc = _run(COUNT_SH, ["--repo", STUDIO_SLUG], env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "running=1" in _running_line(proc.stdout, STUDIO_SLUG)
    assert OTHER_SLUG not in proc.stdout


def test_count_running_missing_run_is_not_running(tmp_path: Path) -> None:
    items = [
        {
            "id": "bc-stale-id",
            "name": "ghost-run",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-stale-id",
            "latestRunId": "run-missing",
            "repos": [{"url": STUDIO_REPO}],
        }
    ]
    with MockCursorAPI(list_items=items, run_not_found_ids={"run-missing"}) as api:
        env = _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY)
        proc = _run(COUNT_SH, ["--repo", STUDIO_SLUG], env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "running=0" in _running_line(proc.stdout, STUDIO_SLUG)
    assert any(path.endswith("/runs/run-missing") for path in api.gets), api.gets
    assert FAKE_KEY not in proc.stdout + proc.stderr


def test_count_running_does_not_remint_must_launch_or_list_repo() -> None:
    src = COUNT_SH.read_text(encoding="utf-8") + COUNT_PY.read_text(encoding="utf-8")
    assert "MUST_LAUNCH" not in src
    assert "GCS_CLOUD_MIN_RUNNING" not in src
    assert "running-count.sh" not in src
    assert "capacity.py" not in src
    list_src = LIST_SH.read_text(encoding="utf-8") + LIST_LONG.read_text(encoding="utf-8")
    assert "--repo" not in list_src
    assert "MUST_LAUNCH" not in list_src
    ts = LIST_TS.read_text(encoding="utf-8")
    assert "--repo" not in ts


def test_palemon_linear_is_living_sky_liv_not_black_swan() -> None:
    blob = "\n".join(p.read_text(encoding="utf-8") for p in (CLOUD_DOC, CLOUD_README, FOOTER))
    assert "Living Sky" in blob
    assert "LIV" in blob
    assert "not Black Swan" in blob


def test_never_bot_cloudagent_as_grunt() -> None:
    blob = "\n".join(
        p.read_text(encoding="utf-8")
        for p in (CLOUD_DOC, CLOUD_README, FOOTER, A2A_DOC, COUNT_SH, COUNT_PY)
    )
    assert "Bot CloudAgent" in blob or "Grok Bot CloudAgent" in blob
    launch = LAUNCH_TS.read_text(encoding="utf-8") + LAUNCH_SH.read_text(encoding="utf-8")
    assert "GCS_BOT_AGENT_ID" not in launch
    assert "GCS_BOT_AGENT_ID" not in COUNT_SH.read_text(encoding="utf-8")
    assert "GCS_BOT_AGENT_ID" not in COUNT_PY.read_text(encoding="utf-8")


def test_launch_stays_grok_46_xhigh_fast_false() -> None:
    launch = LAUNCH_SH.read_text(encoding="utf-8")
    common = (CLOUD / "sdk" / "common.ts").read_text(encoding="utf-8")
    assert "grok-4.6" in launch
    assert "xhigh" in launch
    assert "fast=false" in launch or '"false"' in launch
    assert "grok-4.6" in common
    assert "xhigh" in common
    assert "fast" in common
