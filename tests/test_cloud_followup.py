"""Follow-up must refuse a live RUNNING Extra High; leftover ACTIVE+FINISHED may send.

Never Bot CloudAgent. Do not remint GCS #29/#33/#41/#44 (list/MCP/capacity/send-pin).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from test_cloud_launch import CLOUD, FAKE_KEY, MockCursorAPI, _run, _script_env

FOLLOWUP_SCRIPTS = (
    CLOUD / "followup.sh",
    CLOUD / "followup-cloud-agent.sh",
)


def _run_posts(api: MockCursorAPI) -> list[dict]:
    return [p for p in api.posts if str(p.get("path") or "").rstrip("/").endswith("/runs")]


@pytest.mark.parametrize("script", FOLLOWUP_SCRIPTS, ids=["followup.sh", "followup-cloud-agent.sh"])
def test_followup_refuses_running_worker(tmp_path: Path, script: Path) -> None:
    """Live runStatus=RUNNING must not stack a second run."""
    agent_id = "bc-running"
    with MockCursorAPI(
        agents={
            agent_id: {
                "status": "ACTIVE",
                "latestRunId": "run-live",
                "runStatus": "RUNNING",
                "name": "live-grunt",
            }
        }
    ) as api:
        proc = _run(
            script,
            [agent_id, "Keep going; do not remint."],
            _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY),
        )
    combined = proc.stdout + proc.stderr
    assert proc.returncode != 0, combined
    assert "CLOUD_FOLLOWUP_OK" not in proc.stdout
    err_lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("CLOUD_FOLLOWUP_ERR")]
    assert err_lines, combined
    refuse = err_lines[0]
    assert "runStatus=RUNNING" in refuse, refuse
    assert not _run_posts(api), api.posts
    assert any("/runs/run-live" in path for path in api.gets), api.gets
    assert FAKE_KEY not in combined


@pytest.mark.parametrize("script", FOLLOWUP_SCRIPTS, ids=["followup.sh", "followup-cloud-agent.sh"])
def test_followup_allows_active_finished_leftover(tmp_path: Path, script: Path) -> None:
    """Agent membership ACTIVE + latest run FINISHED is idle leftover, not a live worker."""
    agent_id = "bc-leftover"
    with MockCursorAPI(
        agents={
            agent_id: {
                "status": "ACTIVE",
                "latestRunId": "run-done",
                "runStatus": "FINISHED",
                "name": "leftover-grunt",
            }
        }
    ) as api:
        proc = _run(
            script,
            [agent_id, "Keep the PR; fix the failing check."],
            _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY),
        )
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, combined
    assert "CLOUD_FOLLOWUP_OK" in proc.stdout
    assert "CLOUD_FOLLOWUP_ERR" not in proc.stdout
    posts = _run_posts(api)
    assert len(posts) == 1, api.posts
    assert posts[0]["path"] == f"/v1/agents/{agent_id}/runs"
    assert FAKE_KEY not in combined


def test_followup_refuses_bot_cloudagent(tmp_path: Path) -> None:
    """Grok Bot orchestrator id is never an Extra High follow-up target."""
    bot_id = "bot-orchestrator-not-a-cloud-agent"
    with MockCursorAPI(
        agents={
            bot_id: {
                "status": "ACTIVE",
                "latestRunId": "run-done",
                "runStatus": "FINISHED",
            }
        }
    ) as api:
        proc = _run(
            CLOUD / "followup.sh",
            [bot_id, "Do not treat Bot as Extra High."],
            _script_env(
                tmp_path,
                api.base,
                CURSOR_API_KEY=FAKE_KEY,
                GCS_BOT_AGENT_ID=bot_id,
            ),
        )
    combined = proc.stdout + proc.stderr
    assert proc.returncode != 0, combined
    assert "CLOUD_FOLLOWUP_ERR" in proc.stdout
    assert "CLOUD_FOLLOWUP_OK" not in proc.stdout
    assert "Bot CloudAgent" in combined or "never Bot" in combined.lower()
    assert not _run_posts(api), api.posts
    assert FAKE_KEY not in combined


def test_sdk_followup_refuses_running_before_send() -> None:
    """Direct sdk/run.sh followup must check latest runStatus before agent.send."""
    src = (CLOUD / "sdk" / "followup.ts").read_text(encoding="utf-8")
    running_at = src.find("RUNNING")
    send_at = src.find("agent.send")
    assert running_at != -1
    assert send_at != -1
    assert running_at < send_at
    assert "CLOUD_FOLLOWUP_ERR" in src
    assert "runStatus" in src
    assert "GCS_BOT_AGENT_ID" in src or "Bot CloudAgent" in src


def test_followup_wrapper_execs_followup_sh() -> None:
    src = (CLOUD / "followup-cloud-agent.sh").read_text(encoding="utf-8")
    assert "followup.sh" in src
    assert "RUNNING" in src


def test_followup_refuses_lowercase_running(tmp_path: Path) -> None:
    agent_id = "bc-running-lc"
    with MockCursorAPI(
        agents={
            agent_id: {
                "status": "ACTIVE",
                "latestRunId": "run-live",
                "runStatus": "running",
            }
        }
    ) as api:
        proc = _run(
            CLOUD / "followup.sh",
            [agent_id, "Do not stack."],
            _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY),
        )
    assert proc.returncode != 0
    refuse = [ln for ln in proc.stdout.splitlines() if ln.startswith("CLOUD_FOLLOWUP_ERR")][0]
    assert "runStatus=RUNNING" in refuse
    assert not _run_posts(api)
