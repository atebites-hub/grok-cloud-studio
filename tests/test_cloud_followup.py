"""Follow-up must refuse a live RUNNING Extra High; leftover ACTIVE+FINISHED may send.

HTTP 409 / agent_busy must CLOUD_FOLLOWUP_ERR and must not launch a unique
--name twin. Distinct from leftover GCS #35 waiter 429 backoff. Does not
remint GCS #41/#44/#49/#59/#67. Never Bot CloudAgent.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

from test_cloud_launch import CLOUD, FAKE_KEY, MockCursorAPI, _run, _script_env

FOLLOWUP_SCRIPTS = (
    CLOUD / "followup.sh",
    CLOUD / "followup-cloud-agent.sh",
)
FOLLOWUP_BUSY = CLOUD / "followup_busy.py"
FOLLOWUP_TS = CLOUD / "sdk" / "followup.ts"

AGENT_BUSY_BODY = {"error": {"code": "agent_busy", "message": "agent is busy"}}


def _run_posts(api: MockCursorAPI) -> list[dict]:
    return [p for p in api.posts if str(p.get("path") or "").rstrip("/").endswith("/runs")]


def _create_posts(api: MockCursorAPI) -> list[dict]:
    return [p for p in api.posts if str(p.get("path") or "").rstrip("/") == "/v1/agents"]


def _listed(
    agent_id: str,
    *,
    latest_run_id: str,
    run_status: str,
    name: str = "mock-agent",
    **mock_kw: Any,
) -> MockCursorAPI:
    """Main occupancy mock: list_items + run_status_by_id, not a reminted agents dict."""
    return MockCursorAPI(
        list_items=[
            {
                "id": agent_id,
                "status": "ACTIVE",
                "latestRunId": latest_run_id,
                "name": name,
            }
        ],
        run_status_by_id={latest_run_id: run_status},
        **mock_kw,
    )


def _busy_err_line(stdout: str) -> str:
    err_lines = [ln for ln in stdout.splitlines() if ln.startswith("CLOUD_FOLLOWUP_ERR")]
    assert err_lines, stdout
    return err_lines[0]


@pytest.mark.parametrize("script", FOLLOWUP_SCRIPTS, ids=["followup.sh", "followup-cloud-agent.sh"])
def test_followup_refuses_running_worker(tmp_path: Path, script: Path) -> None:
    """Live runStatus=RUNNING must not stack a second run."""
    agent_id = "bc-running"
    with _listed(agent_id, latest_run_id="run-live", run_status="RUNNING", name="live-grunt") as api:
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
    with _listed(agent_id, latest_run_id="run-done", run_status="FINISHED", name="leftover-grunt") as api:
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
    with _listed(bot_id, latest_run_id="run-done", run_status="FINISHED") as api:
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
    assert "409" in src
    assert "agent_busy" in src


def test_followup_refuses_lowercase_running(tmp_path: Path) -> None:
    agent_id = "bc-running-lc"
    with _listed(agent_id, latest_run_id="run-live", run_status="running") as api:
        proc = _run(
            CLOUD / "followup.sh",
            [agent_id, "Do not stack."],
            _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY),
        )
    assert proc.returncode != 0
    refuse = [ln for ln in proc.stdout.splitlines() if ln.startswith("CLOUD_FOLLOWUP_ERR")][0]
    assert "runStatus=RUNNING" in refuse
    assert not _run_posts(api)


@pytest.mark.parametrize("script", FOLLOWUP_SCRIPTS, ids=["followup.sh", "followup-cloud-agent.sh"])
@pytest.mark.parametrize("latest_status", ["FINISHED", "CREATING"])
def test_followup_http_409_agent_busy_no_twin(
    tmp_path: Path, script: Path, latest_status: str
) -> None:
    """POST /runs HTTP 409 / agent_busy must CLOUD_FOLLOWUP_ERR; never create a --name twin.

    Probe may see leftover FINISHED or CREATING; the API can still 409. Distinct
    from #49 RUNNING probe refuse and leftover #35 waiter 429 backoff.
    """
    agent_id = "bc-busy"
    with _listed(
        agent_id,
        latest_run_id="run-done",
        run_status=latest_status,
        name="unique-grunt",
        followup_http=409,
        followup_body=AGENT_BUSY_BODY,
    ) as api:
        proc = _run(
            script,
            [agent_id, "Do not launch a second unique --name twin."],
            _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY),
        )
    combined = proc.stdout + proc.stderr
    assert proc.returncode != 0, combined
    assert "CLOUD_FOLLOWUP_OK" not in proc.stdout
    assert "CLOUD_LAUNCH_OK" not in combined
    refuse = _busy_err_line(proc.stdout)
    assert "http=409" in refuse, refuse
    assert "agent_busy=1" in refuse, refuse
    assert "runStatus=RUNNING" not in refuse
    assert len(_run_posts(api)) == 1, api.posts
    assert _run_posts(api)[0]["path"] == f"/v1/agents/{agent_id}/runs"
    assert not _create_posts(api), api.posts
    assert "CLOUD_WAITER_RETRY" not in combined
    assert FAKE_KEY not in combined


def test_followup_http_409_without_code_still_agent_busy(tmp_path: Path) -> None:
    """HTTP 409 is agent_busy even when the body omits the code token."""
    agent_id = "bc-conflict"
    with _listed(
        agent_id,
        latest_run_id="run-done",
        run_status="FINISHED",
        followup_http=409,
        followup_body={"error": "conflict"},
    ) as api:
        proc = _run(
            CLOUD / "followup.sh",
            [agent_id, "Still busy."],
            _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY),
        )
    refuse = _busy_err_line(proc.stdout)
    assert proc.returncode != 0
    assert "http=409" in refuse
    assert "agent_busy=1" in refuse
    assert not _create_posts(api)
    assert len(_run_posts(api)) == 1


def test_followup_http_400_is_not_agent_busy_line(tmp_path: Path) -> None:
    """Other create rejects stay generic CLOUD_FOLLOWUP_ERR (not the 409 busy line)."""
    agent_id = "bc-bad"
    with _listed(
        agent_id,
        latest_run_id="run-done",
        run_status="FINISHED",
        followup_http=400,
        followup_body={"error": "bad_request"},
    ) as api:
        proc = _run(
            CLOUD / "followup.sh",
            [agent_id, "Bad prompt."],
            _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY),
        )
    combined = proc.stdout + proc.stderr
    assert proc.returncode != 0, combined
    assert "CLOUD_FOLLOWUP_ERR" in proc.stdout
    assert "CLOUD_FOLLOWUP_OK" not in proc.stdout
    refuse = _busy_err_line(proc.stdout)
    assert "agent_busy=1" not in refuse
    assert "http=409" not in refuse
    assert not _create_posts(api)
    assert len(_run_posts(api)) == 1


def test_followup_http_429_is_not_waiter_backoff_or_twin(tmp_path: Path) -> None:
    """Follow-up 429 is not GCS #35 waiter backoff and must not remint a twin."""
    agent_id = "bc-rate"
    with _listed(
        agent_id,
        latest_run_id="run-done",
        run_status="FINISHED",
        followup_http=429,
        followup_body={"error": "rate_limit"},
    ) as api:
        proc = _run(
            CLOUD / "followup.sh",
            [agent_id, "Do not backoff-retry as a waiter."],
            _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY),
        )
    combined = proc.stdout + proc.stderr
    assert proc.returncode != 0, combined
    assert "CLOUD_FOLLOWUP_ERR" in proc.stdout
    assert "CLOUD_FOLLOWUP_OK" not in proc.stdout
    refuse = _busy_err_line(proc.stdout)
    assert "agent_busy=1" not in refuse
    assert "CLOUD_WAITER_RETRY" not in combined
    assert "CLOUD_WAITER_RESTART" not in combined
    assert not _create_posts(api)
    assert len(_run_posts(api)) == 1


def test_followup_agent_busy_code_on_non_409_still_no_twin(tmp_path: Path) -> None:
    """Body code=agent_busy without HTTP 409 still CLOUD_FOLLOWUP_ERR; no create twin."""
    agent_id = "bc-busy-code"
    with _listed(
        agent_id,
        latest_run_id="run-done",
        run_status="FINISHED",
        followup_http=503,
        followup_body=AGENT_BUSY_BODY,
    ) as api:
        proc = _run(
            CLOUD / "followup.sh",
            [agent_id, "Busy under 503."],
            _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY),
        )
    refuse = _busy_err_line(proc.stdout)
    assert proc.returncode != 0
    assert "agent_busy=1" in refuse
    assert "http=503" in refuse
    assert not _create_posts(api)
    assert len(_run_posts(api)) == 1


def test_sdk_followup_409_source_no_twin_create() -> None:
    """sdk/followup.ts must map 409/agent_busy to CLOUD_FOLLOWUP_ERR and never Agent.create."""
    src = FOLLOWUP_TS.read_text(encoding="utf-8")
    assert "409" in src
    assert "agent_busy" in src
    assert "CLOUD_FOLLOWUP_ERR" in src
    assert "Agent.create(" not in src
    assert "sdkCreateFailExitCode" not in src
    assert "CLOUD_WAITER_RETRY" not in src
    send_at = src.find("agent.send")
    busy_at = src.find("agent_busy")
    assert send_at != -1
    assert busy_at != -1


def test_followup_sh_409_source_no_twin_launch() -> None:
    src = (CLOUD / "followup.sh").read_text(encoding="utf-8")
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    assert "409" in src
    assert "agent_busy" in src
    assert "CLOUD_FOLLOWUP_ERR" in src
    assert "launch-cloud-extra-high" not in code
    assert "find_live_name_twin" not in src
    assert "twin remint" not in src
    assert "CLOUD_WAITER_RETRY" not in src
    assert "NousResearch/hermes-agent" not in src
    assert "Agent.create(" not in src


def test_followup_busy_helper_detects_409_not_429() -> None:
    """Pure helper: HTTP 409 / agent_busy vs 429 rate-limit. Does not remint #35."""
    assert FOLLOWUP_BUSY.is_file(), FOLLOWUP_BUSY
    spec = importlib.util.spec_from_file_location("gcs_followup_busy", FOLLOWUP_BUSY)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.is_busy_conflict(http_code=409, body=None) is True
    assert mod.is_busy_conflict(http_code="409", body={"error": "conflict"}) is True
    assert (
        mod.is_busy_conflict(http_code=201, body={"error": {"code": "agent_busy"}})
        is True
    )
    assert mod.is_busy_conflict(http_code=429, body={"error": "rate_limit"}) is False
    assert mod.is_busy_conflict(http_code=400, body={"error": "bad_request"}) is False
    assert mod.is_busy_conflict(http_code=201, body={"run": {"id": "run-ok"}}) is False
    line = mod.err_line(http_code=409)
    assert line.startswith("CLOUD_FOLLOWUP_ERR")
    assert "http=409" in line
    assert "agent_busy=1" in line
