"""list-cloud-agents.sh --repo: count runStatus=RUNNING per bound repo.

Leftover agent status=ACTIVE is not capacity. Palemon Linear is Living Sky
(LIV), not Black Swan. Never Bot CloudAgent. Does not remint GCS #29/#33/#44
≥8 must-launch law — this is the per-repo list filter.
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

LIST_SH = CLOUD / "list.sh"
LIST_LONG = CLOUD / "list-cloud-agents.sh"
LIST_TS = CLOUD / "sdk" / "list.ts"
FOOTER = REPO / "scripts" / "directors" / "common_footer.txt"
CLOUD_DOC = REPO / "docs" / "CLOUD.md"
CLOUD_README = CLOUD / "README.md"
A2A_DOC = REPO / "docs" / "A2A.md"
LAUNCH_TS = CLOUD / "sdk" / "launch.ts"
LAUNCH_SH = REPO / "scripts" / "launch-cloud-extra-high.sh"

STUDIO_REPO = EXAMPLE_REPO
OTHER_REPO = "https://github.com/example/other-game"
STUDIO_SLUG = "atebites-hub/grok-cloud-studio"


def _list_row(stdout: str, agent_id: str) -> str:
    rows = [line for line in stdout.splitlines() if agent_id in line]
    assert rows, stdout
    return rows[0]


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
        "run-other-live": "RUNNING",
    }


def test_repo_key_accepts_org_name_https_git_and_ssh() -> None:
    sys.path.insert(0, str(CLOUD))
    import list_format

    key = list_format.repo_key
    assert key("atebites-hub/grok-cloud-studio") == STUDIO_SLUG
    assert key(STUDIO_REPO) == STUDIO_SLUG
    assert key(STUDIO_REPO + ".git") == STUDIO_SLUG
    assert key(STUDIO_REPO + "/") == STUDIO_SLUG
    assert key("git@github.com:atebites-hub/grok-cloud-studio.git") == STUDIO_SLUG
    assert key("github.com/atebites-hub/grok-cloud-studio") == STUDIO_SLUG
    assert key(OTHER_REPO) != STUDIO_SLUG


def test_list_help_documents_repo_filter() -> None:
    proc = subprocess.run(
        ["bash", str(LIST_SH), "--help"],
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
    assert "org/name" in blob or "github.com" in blob
    assert "runStatus" in blob


def test_list_prints_run_status_on_every_row_without_treating_active_as_capacity(
    tmp_path: Path,
) -> None:
    items = _fleet_items()
    with MockCursorAPI(list_items=items, run_status_by_id=_run_status_by_id()) as api:
        env = _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY)
        listed = _run(LIST_LONG, ["--limit", "20"], env)
    assert listed.returncode == 0, listed.stdout + listed.stderr
    live = _list_row(listed.stdout, "bc-studio-live")
    done = _list_row(listed.stdout, "bc-studio-done")
    other = _list_row(listed.stdout, "bc-other-live")
    assert "status=ACTIVE" in live
    assert "runStatus=RUNNING" in live
    assert "status=ACTIVE" in done
    assert "runStatus=FINISHED" in done
    assert "runStatus=RUNNING" not in done
    assert "runStatus=RUNNING" in other
    assert any(path.endswith("/runs/run-studio-live") for path in api.gets), api.gets
    assert FAKE_KEY not in listed.stdout + listed.stderr


def test_list_repo_org_name_keeps_bound_repo_and_drops_other_remotes(tmp_path: Path) -> None:
    items = _fleet_items()
    with MockCursorAPI(list_items=items, run_status_by_id=_run_status_by_id()) as api:
        env = _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY)
        listed = _run(LIST_LONG, ["--repo", STUDIO_SLUG], env)
    assert listed.returncode == 0, listed.stdout + listed.stderr
    out = listed.stdout
    assert "bc-studio-live" in out
    assert "bc-studio-done" in out
    assert "bc-other-live" not in out
    live = _list_row(out, "bc-studio-live")
    done = _list_row(out, "bc-studio-done")
    assert "runStatus=RUNNING" in live
    assert "runStatus=FINISHED" in done
    running = [line for line in out.splitlines() if "runStatus=RUNNING" in line]
    assert len(running) == 1
    assert "bc-studio-live" in running[0]
    assert any(path.endswith("/v1/agents/bc-studio-live") for path in api.gets), api.gets
    assert any(path.endswith("/v1/agents/bc-other-live") for path in api.gets), api.gets
    assert FAKE_KEY not in listed.stdout + listed.stderr


def test_list_repo_https_url_and_git_suffix_match_org_name(tmp_path: Path) -> None:
    items = _fleet_items()
    with MockCursorAPI(list_items=items, run_status_by_id=_run_status_by_id()) as api:
        env = _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY)
        via_url = _run(LIST_SH, ["--repo", STUDIO_REPO], env)
        via_git = _run(LIST_SH, ["--repo", STUDIO_REPO + ".git", "--limit", "20"], env)
    assert via_url.returncode == 0, via_url.stdout + via_url.stderr
    assert via_git.returncode == 0, via_git.stdout + via_git.stderr
    for proc in (via_url, via_git):
        assert "bc-studio-live" in proc.stdout
        assert "bc-other-live" not in proc.stdout
        assert "runStatus=RUNNING" in proc.stdout


def test_list_repo_excludes_unbound_agents(tmp_path: Path) -> None:
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
        listed = _run(LIST_SH, ["--repo", STUDIO_SLUG], env)
    assert listed.returncode == 0, listed.stdout + listed.stderr
    assert "bc-studio-live" in listed.stdout
    assert "bc-unbound" not in listed.stdout


def test_list_repo_falls_back_to_run_git_repo_url(tmp_path: Path) -> None:
    items = [
        {
            "id": "bc-git-only",
            "name": "git-only",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-git-only",
            "latestRunId": "run-git-only",
            "runGit": {
                "branches": [
                    {"repoUrl": "github.com/atebites-hub/grok-cloud-studio", "branch": "cursor/x"}
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
        listed = _run(LIST_SH, ["--repo", STUDIO_SLUG], env)
    assert listed.returncode == 0, listed.stdout + listed.stderr
    assert "bc-git-only" in listed.stdout
    assert "runStatus=RUNNING" in _list_row(listed.stdout, "bc-git-only")
    assert "bc-other-live" not in listed.stdout


def test_list_run_not_found_prints_run_status_none(tmp_path: Path) -> None:
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
        listed = _run(LIST_LONG, ["--repo", STUDIO_SLUG], env)
    assert listed.returncode == 0, listed.stdout + listed.stderr
    row = _list_row(listed.stdout, "bc-stale-id")
    assert "status=ACTIVE" in row
    assert "runStatus=none" in row
    assert any(path.endswith("/runs/run-missing") for path in api.gets), api.gets
    assert FAKE_KEY not in listed.stdout + listed.stderr


def test_list_repo_equals_form(tmp_path: Path) -> None:
    items = _fleet_items()
    with MockCursorAPI(list_items=items, run_status_by_id=_run_status_by_id()) as api:
        env = _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY)
        listed = _run(LIST_SH, [f"--repo={STUDIO_SLUG}"], env)
    assert listed.returncode == 0, listed.stdout + listed.stderr
    assert "bc-studio-live" in listed.stdout
    assert "bc-other-live" not in listed.stdout


def test_sdk_list_accepts_repo_and_prints_run_status() -> None:
    src = LIST_TS.read_text(encoding="utf-8")
    assert "--repo" in src
    assert "runStatus=" in src
    assert "mapRunStatus" in src
    assert "repoKey" in src or "repo_key" in src or "normalizeRepo" in src


def test_palemon_linear_is_living_sky_liv_not_black_swan() -> None:
    blob = "\n".join(p.read_text(encoding="utf-8") for p in (CLOUD_DOC, CLOUD_README, FOOTER))
    assert "Living Sky" in blob
    assert "LIV" in blob
    assert "Black Swan" in blob
    assert "not Black Swan" in blob
    assert "pale" + "mon" not in blob.lower() or "Palemon Linear" in blob


def test_never_bot_cloudagent_as_grunt() -> None:
    blob = "\n".join(
        p.read_text(encoding="utf-8")
        for p in (CLOUD_DOC, CLOUD_README, FOOTER, A2A_DOC, LIST_SH, LIST_LONG, LIST_TS)
    )
    assert "Bot CloudAgent" in blob or "Grok Bot CloudAgent" in blob
    launch = LAUNCH_TS.read_text(encoding="utf-8") + LAUNCH_SH.read_text(encoding="utf-8")
    assert "GCS_BOT_AGENT_ID" not in launch
    assert "GCS_BOT_AGENT_ID" not in LIST_SH.read_text(encoding="utf-8")
    assert "GCS_BOT_AGENT_ID" not in LIST_TS.read_text(encoding="utf-8")


def test_list_scripts_do_not_remint_must_launch_floor() -> None:
    blob = (
        LIST_SH.read_text(encoding="utf-8")
        + LIST_LONG.read_text(encoding="utf-8")
        + LIST_TS.read_text(encoding="utf-8")
    )
    assert "MUST_LAUNCH" not in blob
    assert "GCS_CLOUD_MIN_RUNNING" not in blob
    assert "running-count" not in blob
