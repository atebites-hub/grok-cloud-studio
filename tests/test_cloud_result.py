"""Extra High result JSON: bound repos[0].url for game vs studio targeting."""
from __future__ import annotations

import json
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

sys.path.insert(0, str(CLOUD))
import result_payload  # noqa: E402

RESULT = CLOUD / "result-cloud-agent.sh"
COLLECT = CLOUD / "sdk" / "collect.ts"
COMMON_TS = CLOUD / "sdk" / "common.ts"
RESULT_SH = CLOUD / "result-cloud-agent.sh"
FOOTER = REPO / "scripts" / "directors" / "common_footer.txt"
CLOUD_DOC = REPO / "docs" / "CLOUD.md"
CLOUD_README = CLOUD / "README.md"
A2A_DOC = REPO / "docs" / "A2A.md"
LAUNCH_TS = CLOUD / "sdk" / "launch.ts"
LAUNCH_SH = REPO / "scripts" / "launch-cloud-extra-high.sh"

STUDIO_REPO = EXAMPLE_REPO
GAME_REPO = "https://github.com/" + "atebites-hub/" + "palemon"
PRIVATE_GAME = "atebites-hub/" + "palemon"


def _result_json(home: Path, base: str, **extra: str) -> tuple[dict, str, str]:
    env = _script_env(home, base, CURSOR_API_KEY=FAKE_KEY, **extra)
    proc = _run(RESULT, ["bc-target"], env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    return payload, proc.stdout, proc.stderr


def test_bound_repo_url_prefers_agent_repos() -> None:
    agent = {"repos": [{"url": GAME_REPO, "startingRef": "main"}]}
    run = {"git": {"branches": [{"repoUrl": "github.com/atebites-hub/grok-cloud-studio"}]}}
    assert result_payload.bound_repo_url(agent, run) == GAME_REPO
    assert result_payload.bound_repos(agent)[0]["url"] == GAME_REPO


def test_bound_repo_url_normalizes_run_git_scheme() -> None:
    assert (
        result_payload.bound_repo_url(
            {},
            {"git": {"branches": [{"repoUrl": "github.com/atebites-hub/grok-cloud-studio"}]}},
        )
        == STUDIO_REPO
    )


def test_result_json_prefers_bound_agent_repos_over_run_git(tmp_path: Path) -> None:
    repos = [{"url": GAME_REPO, "startingRef": "main"}]
    git = {
        "branches": [
            {
                "repoUrl": "github.com/atebites-hub/grok-cloud-studio",
                "branch": "cursor/demo",
            }
        ]
    }
    with MockCursorAPI(agent_repos=repos, run_git=git) as api:
        payload, _, _ = _result_json(tmp_path, api.base)
    assert payload["repoUrl"] == GAME_REPO
    assert payload["repos"][0]["url"] == GAME_REPO


def test_result_json_includes_bound_studio_repos_url(tmp_path: Path) -> None:
    repos = [{"url": STUDIO_REPO, "startingRef": "main"}]
    with MockCursorAPI(agent_repos=repos) as api:
        payload, out, err = _result_json(tmp_path, api.base)
    assert payload["repos"][0]["url"] == STUDIO_REPO
    assert payload["repoUrl"] == STUDIO_REPO
    assert "grok-cloud-studio" in payload["repoUrl"]
    assert FAKE_KEY not in out + err


def test_result_json_includes_bound_game_repos_url(tmp_path: Path) -> None:
    repos = [{"url": GAME_REPO, "startingRef": "main"}]
    with MockCursorAPI(agent_repos=repos) as api:
        payload, out, err = _result_json(tmp_path, api.base)
    assert payload["repos"][0]["url"] == GAME_REPO
    assert payload["repoUrl"] == GAME_REPO
    assert PRIVATE_GAME in payload["repoUrl"]
    assert "grok-cloud-studio" not in payload["repoUrl"]
    assert FAKE_KEY not in out + err


def test_result_json_falls_back_to_run_git_repo_url(tmp_path: Path) -> None:
    git = {
        "branches": [
            {
                "repoUrl": "github.com/atebites-hub/grok-cloud-studio",
                "branch": "cursor/demo",
                "prUrl": "https://github.com/atebites-hub/grok-cloud-studio/pull/1",
            }
        ]
    }
    with MockCursorAPI(run_git=git) as api:
        payload, _, _ = _result_json(tmp_path, api.base)
    assert payload["repoUrl"] == STUDIO_REPO
    assert payload["prUrl"] == "https://github.com/atebites-hub/grok-cloud-studio/pull/1"


def test_result_json_repo_url_null_when_unbound(tmp_path: Path) -> None:
    with MockCursorAPI() as api:
        payload, _, _ = _result_json(tmp_path, api.base)
    assert payload["repoUrl"] is None
    assert payload["repos"] == []


def test_collect_ts_includes_bound_repos_url() -> None:
    collect = COLLECT.read_text(encoding="utf-8")
    common = COMMON_TS.read_text(encoding="utf-8")
    blob = collect + "\n" + common
    assert "repoUrl" in collect
    assert "repos" in collect
    assert "boundRepoUrl" in blob
    assert PRIVATE_GAME not in blob


def test_result_shell_reads_agent_repos_url() -> None:
    text = RESULT_SH.read_text(encoding="utf-8")
    assert "result_payload.py" in text or "repos" in text
    assert "repoUrl" in text or "result_payload.py" in text
    assert PRIVATE_GAME not in text


def test_palemon_linear_is_living_sky_liv_not_black_swan() -> None:
    blob = "\n".join(
        p.read_text(encoding="utf-8") for p in (CLOUD_DOC, CLOUD_README, FOOTER)
    )
    assert "Living Sky" in blob
    assert "LIV" in blob
    assert "Black Swan" in blob
    low = blob.lower()
    assert "not black swan" in low
    assert PRIVATE_GAME not in blob


def test_never_bot_cloudagent_as_grunt() -> None:
    blob = "\n".join(
        p.read_text(encoding="utf-8")
        for p in (CLOUD_DOC, CLOUD_README, FOOTER, A2A_DOC, LAUNCH_TS, LAUNCH_SH, COLLECT)
    )
    assert "Bot CloudAgent" in blob or "Grok Bot CloudAgent" in blob
    launch = LAUNCH_TS.read_text(encoding="utf-8") + LAUNCH_SH.read_text(encoding="utf-8")
    assert "Agent.create" in launch or "POST /v1/agents" in launch
    assert "GCS_BOT_AGENT_ID" not in launch
    collect = COLLECT.read_text(encoding="utf-8")
    assert "GCS_BOT_AGENT_ID" not in collect
    assert "boundRepoUrl" in collect or "repoUrl" in collect
