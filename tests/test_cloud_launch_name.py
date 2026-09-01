"""launch-cloud-extra-high.sh --name refuses a live runStatus=RUNNING twin.

Leftover ACTIVE+FINISHED does not block. Never Bot CloudAgent.
Palemon Linear is Living Sky (LIV). Does not remint GCS #49 followup-refuse.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from test_cloud_launch import CLOUD, FAKE_KEY, LAUNCH, MockCursorAPI, REPO, _run, _script_env

FOOTER = REPO / "scripts" / "directors" / "common_footer.txt"
CLOUD_DOC = REPO / "docs" / "CLOUD.md"
CLOUD_README = CLOUD / "README.md"
LAUNCH_TS = CLOUD / "sdk" / "launch.ts"
FOLLOWUP_SH = CLOUD / "followup.sh"
FOLLOWUP_TS = CLOUD / "sdk" / "followup.ts"
NAME_TWIN = CLOUD / "name_twin.py"

LIVE_NAME = "floor-iac"


def _create_posts(api: MockCursorAPI) -> list[dict[str, Any]]:
    return [p for p in api.posts if str(p.get("path") or "").rstrip("/") == "/v1/agents"]


def _fleet(
    *,
    live_status: str = "RUNNING",
    leftover_status: str = "FINISHED",
    other_status: str = "RUNNING",
    bot_status: str = "FINISHED",
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    items = [
        {
            "id": "bc-live",
            "name": LIVE_NAME,
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-live",
            "latestRunId": "run-live",
        },
        {
            "id": "bc-leftover",
            "name": "other-seat",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-leftover",
            "latestRunId": "run-done",
        },
        {
            "id": "bc-other-live",
            "name": "systems-grunt",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-other-live",
            "latestRunId": "run-other",
        },
        {
            "id": "bot-orchestrator-not-a-cloud-agent",
            "name": LIVE_NAME,
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bot-orchestrator-not-a-cloud-agent",
            "latestRunId": "run-bot",
        },
    ]
    runs = {
        "run-live": live_status,
        "run-done": leftover_status,
        "run-other": other_status,
        "run-bot": bot_status,
    }
    return items, runs


def test_launch_name_refuses_live_running_twin(tmp_path: Path) -> None:
    """Given ACTIVE+RUNNING same --name, when launch, then refuse (not leftover-green).

    Membership ACTIVE is not liveness. The gate is latest-run runStatus=RUNNING.
    """
    items, runs = _fleet()
    with MockCursorAPI(list_items=items, run_status_by_id=runs) as api:
        proc = _run(
            LAUNCH,
            ["--name", LIVE_NAME, "Implement LIV-41. Open a PR."],
            _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY),
        )
    combined = proc.stdout + proc.stderr
    assert proc.returncode != 0, combined
    assert "CLOUD_LAUNCH_OK" not in proc.stdout
    err_lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("CLOUD_LAUNCH_ERR")]
    assert err_lines, combined
    refuse = err_lines[0]
    assert "runStatus=RUNNING" in refuse, refuse
    assert not _create_posts(api), api.posts
    assert any(path.endswith("/runs/run-live") for path in api.gets), api.gets
    assert FAKE_KEY not in combined


def test_launch_positional_name_refuses_running_twin(tmp_path: Path) -> None:
    items, runs = _fleet()
    with MockCursorAPI(list_items=items, run_status_by_id=runs) as api:
        proc = _run(
            LAUNCH,
            ["Implement LIV-41. Open a PR.", LIVE_NAME],
            _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY),
        )
    combined = proc.stdout + proc.stderr
    assert proc.returncode != 0, combined
    assert "CLOUD_LAUNCH_OK" not in proc.stdout
    refuse = [ln for ln in proc.stdout.splitlines() if ln.startswith("CLOUD_LAUNCH_ERR")][0]
    assert "runStatus=RUNNING" in refuse
    assert not _create_posts(api), api.posts


def test_launch_name_allows_active_finished_leftover(tmp_path: Path) -> None:
    """Same --name with leftover ACTIVE+FINISHED is idle, not a live twin."""
    items, runs = _fleet(live_status="FINISHED")
    with MockCursorAPI(list_items=items, run_status_by_id=runs) as api:
        proc = _run(
            LAUNCH,
            ["--name", LIVE_NAME, "Implement LIV-41. Open a PR."],
            _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY),
        )
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, combined
    assert "CLOUD_LAUNCH_OK" in proc.stdout
    assert "CLOUD_LAUNCH_ERR" not in proc.stdout
    posts = _create_posts(api)
    assert len(posts) == 1, api.posts
    body = posts[0]["body"]
    assert body["name"] == LIVE_NAME
    assert body["model"]["id"] == "grok-4.6"
    params = {(p["id"], p["value"]) for p in body["model"]["params"]}
    assert ("effort", "xhigh") in params
    assert ("fast", "false") in params
    assert FAKE_KEY not in combined


def test_launch_name_does_not_block_on_other_running_name(tmp_path: Path) -> None:
    items, runs = _fleet()
    with MockCursorAPI(list_items=items, run_status_by_id=runs) as api:
        proc = _run(
            LAUNCH,
            ["--name", "fresh-grunt", "Implement a new Extra High. Open a PR."],
            _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY),
        )
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, combined
    assert "CLOUD_LAUNCH_OK" in proc.stdout
    assert len(_create_posts(api)) == 1
    assert FAKE_KEY not in combined


def test_launch_without_name_does_not_scan_twins(tmp_path: Path) -> None:
    items, runs = _fleet()
    with MockCursorAPI(list_items=items, run_status_by_id=runs) as api:
        proc = _run(
            LAUNCH,
            ["Implement unnamed Extra High. Open a PR."],
            _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY),
        )
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, combined
    assert "CLOUD_LAUNCH_OK" in proc.stdout
    assert len(_create_posts(api)) == 1


def test_launch_name_refuses_lowercase_running(tmp_path: Path) -> None:
    items, runs = _fleet(live_status="running")
    with MockCursorAPI(list_items=items, run_status_by_id=runs) as api:
        proc = _run(
            LAUNCH,
            ["--name", LIVE_NAME, "Do not remint a live twin."],
            _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY),
        )
    assert proc.returncode != 0
    refuse = [ln for ln in proc.stdout.splitlines() if ln.startswith("CLOUD_LAUNCH_ERR")][0]
    assert "runStatus=RUNNING" in refuse
    assert not _create_posts(api)


def test_launch_name_skips_bot_cloudagent(tmp_path: Path) -> None:
    """Grok Bot is not an Extra High twin even if the listed name collides."""
    items, runs = _fleet(live_status="FINISHED", bot_status="RUNNING")
    bot_id = "bot-orchestrator-not-a-cloud-agent"
    with MockCursorAPI(list_items=items, run_status_by_id=runs) as api:
        proc = _run(
            LAUNCH,
            ["--name", LIVE_NAME, "Launch Extra High; never Bot CloudAgent."],
            _script_env(
                tmp_path,
                api.base,
                CURSOR_API_KEY=FAKE_KEY,
                GCS_BOT_AGENT_ID=bot_id,
            ),
        )
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, combined
    assert "CLOUD_LAUNCH_OK" in proc.stdout
    assert len(_create_posts(api)) == 1
    assert not any(path.endswith("/runs/run-bot") for path in api.gets), api.gets
    assert FAKE_KEY not in combined


def test_launch_name_creating_is_not_running(tmp_path: Path) -> None:
    """CREATING is in-flight membership, not runStatus=RUNNING. Do not refuse."""
    items, runs = _fleet(live_status="CREATING")
    with MockCursorAPI(list_items=items, run_status_by_id=runs) as api:
        proc = _run(
            LAUNCH,
            ["--name", LIVE_NAME, "CREATING is not RUNNING. Open a PR."],
            _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY),
        )
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, combined
    assert "CLOUD_LAUNCH_OK" in proc.stdout
    assert "CLOUD_LAUNCH_ERR" not in proc.stdout
    assert len(_create_posts(api)) == 1
    body = _create_posts(api)[0]["body"]
    assert body["model"]["id"] == "grok-4.6"
    params = {(p["id"], p["value"]) for p in body["model"]["params"]}
    assert ("effort", "xhigh") in params
    assert ("fast", "false") in params


def test_launch_name_equals_form_refuses_running(tmp_path: Path) -> None:
    items, runs = _fleet()
    with MockCursorAPI(list_items=items, run_status_by_id=runs) as api:
        proc = _run(
            LAUNCH,
            [f"--name={LIVE_NAME}", "Do not remint via --name=."],
            _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY),
        )
    assert proc.returncode != 0
    refuse = [ln for ln in proc.stdout.splitlines() if ln.startswith("CLOUD_LAUNCH_ERR")][0]
    assert "runStatus=RUNNING" in refuse
    assert not _create_posts(api)


def test_launch_name_list_probe_fail_closed(tmp_path: Path) -> None:
    """List probe failure must not remint blindly (not leftover-green)."""
    items, runs = _fleet()
    with MockCursorAPI(list_items=items, run_status_by_id=runs, list_http=500) as api:
        proc = _run(
            LAUNCH,
            ["--name", LIVE_NAME, "Fail closed if list cannot be read."],
            _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY),
        )
    combined = proc.stdout + proc.stderr
    assert proc.returncode != 0, combined
    assert "CLOUD_LAUNCH_OK" not in proc.stdout
    assert "CLOUD_LAUNCH_ERR" in proc.stdout
    assert not _create_posts(api), api.posts
    assert FAKE_KEY not in combined


def test_launch_name_resolves_latest_run_id_when_list_omits_it(tmp_path: Path) -> None:
    """GET /v1/agents list may omit latestRunId; still refuse a live RUNNING twin."""
    items = [
        {
            "id": "bc-live",
            "name": LIVE_NAME,
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-live",
            "detailLatestRunId": "run-live",
        }
    ]
    with MockCursorAPI(list_items=items, run_status_by_id={"run-live": "RUNNING"}) as api:
        proc = _run(
            LAUNCH,
            ["--name", LIVE_NAME, "Resolve latestRunId from GET agent."],
            _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY),
        )
    combined = proc.stdout + proc.stderr
    assert proc.returncode != 0, combined
    assert "CLOUD_LAUNCH_OK" not in proc.stdout
    refuse = [ln for ln in proc.stdout.splitlines() if ln.startswith("CLOUD_LAUNCH_ERR")][0]
    assert "runStatus=RUNNING" in refuse
    assert not _create_posts(api), api.posts
    assert any(path.rstrip("/").endswith("/v1/agents/bc-live") for path in api.gets), api.gets
    assert any(path.endswith("/runs/run-live") for path in api.gets), api.gets


def test_name_twin_cli_running_vs_finished(tmp_path: Path) -> None:
    items, runs = _fleet()
    with MockCursorAPI(list_items=items, run_status_by_id=runs) as api:
        env = _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY)
        live = subprocess.run(
            [sys.executable, str(NAME_TWIN), "--name", LIVE_NAME],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            env=env,
            timeout=20,
        )
        leftover = subprocess.run(
            [sys.executable, str(NAME_TWIN), "--name", "other-seat"],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            env=env,
            timeout=20,
        )
    assert live.returncode == 0, live.stdout + live.stderr
    assert "runStatus=RUNNING" in live.stdout
    assert leftover.returncode == 1, leftover.stdout + leftover.stderr
    assert FAKE_KEY not in live.stdout + live.stderr + leftover.stdout + leftover.stderr


def test_find_live_name_twin_pure() -> None:
    sys.path.insert(0, str(CLOUD))
    import name_twin

    fetched: list[tuple[str, str]] = []

    def fetch(agent_id: str, run_id: str) -> str | None:
        fetched.append((agent_id, run_id))
        return {
            "run-live": "RUNNING",
            "run-done": "FINISHED",
            "run-bot": "RUNNING",
        }.get(run_id)

    items, _runs = _fleet()
    twin = name_twin.find_live_name_twin(
        items,
        LIVE_NAME,
        bot_id="bot-orchestrator-not-a-cloud-agent",
        fetch_run_status=fetch,
    )
    assert twin is not None
    assert twin["id"] == "bc-live"
    assert twin["runStatus"] == "RUNNING"
    assert ("bot-orchestrator-not-a-cloud-agent", "run-bot") not in fetched

    leftover = name_twin.find_live_name_twin(
        items,
        LIVE_NAME,
        bot_id="bot-orchestrator-not-a-cloud-agent",
        fetch_run_status=lambda _a, _r: "FINISHED",
    )
    assert leftover is None

    other = name_twin.find_live_name_twin(
        items,
        "fresh-grunt",
        fetch_run_status=lambda _a, _r: "RUNNING",
    )
    assert other is None


def test_sdk_launch_refuses_running_name_before_create() -> None:
    src = LAUNCH_TS.read_text(encoding="utf-8")
    running_at = src.find("RUNNING")
    create_at = src.find("Agent.create")
    assert running_at != -1
    assert create_at != -1
    assert running_at < create_at
    assert "CLOUD_LAUNCH_ERR" in src
    assert "runStatus" in src
    assert "GCS_BOT_AGENT_ID" in src or "Bot CloudAgent" in src


def test_does_not_remint_followup_refuse() -> None:
    """LIV-41 launch-name refuse is not a remint of GCS #49 followup-refuse."""
    followup_sh = FOLLOWUP_SH.read_text(encoding="utf-8")
    followup_ts = FOLLOWUP_TS.read_text(encoding="utf-8")
    launch = LAUNCH.read_text(encoding="utf-8")
    assert "CLOUD_FOLLOWUP_ERR" not in launch
    assert "followup.sh" not in launch
    assert "twin remint" not in followup_sh
    assert "find_live_name_twin" not in followup_sh
    assert "find_live_name_twin" not in followup_ts
    assert NAME_TWIN.is_file()


def test_docs_launch_name_twin_living_sky() -> None:
    blob = "\n".join(
        p.read_text(encoding="utf-8") for p in (CLOUD_DOC, CLOUD_README, FOOTER, LAUNCH)
    )
    assert "runStatus=RUNNING" in blob
    assert "twin" in blob.lower()
    assert "ACTIVE" in blob and "FINISHED" in blob
    assert "Bot CloudAgent" in blob or "never Bot" in blob.lower()
    assert "Living Sky" in blob
    assert "LIV" in blob
    assert "grok-4.6" in blob
    assert "xhigh" in blob
