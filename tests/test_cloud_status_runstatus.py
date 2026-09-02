"""REST status.sh: print latest-run runStatus, not only agent ACTIVE.

list.sh / sdk/list.ts / MCP cloud_list already print runStatus on main
(#84 / #69 / #33). Unique remaining: REST status.sh used snake_case
run_status= (and omitted it when latestRunId was missing); a 404 on
GET /runs/{id} failed the command instead of printing runStatus=none.

Does not remint cloud_list. Does not vendor Hermes. Never Bot CloudAgent.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from test_cloud_launch import FAKE_KEY, MockCursorAPI, _run, _script_env

REPO = Path(__file__).resolve().parents[1]
CLOUD = REPO / "scripts" / "cloud"
STATUS_SH = CLOUD / "status.sh"
STATUS_ALIAS = CLOUD / "status-cloud-agent.sh"
STATUS_TS = CLOUD / "sdk" / "status.ts"
COLLECT_TS = CLOUD / "sdk" / "collect.ts"
MCP = REPO / "scripts" / "mcp" / "gcs_mcp.py"


def _items() -> dict[str, dict[str, Any]]:
    return {
        "leftover": {
            "id": "bc-leftover",
            "name": "done-grunt",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-leftover",
            "latestRunId": "run-done",
        },
        "live": {
            "id": "bc-live",
            "name": "busy-grunt",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-live",
            "latestRunId": "run-live",
        },
        "idle": {
            "id": "bc-idle",
            "name": "no-run",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-idle",
            "latestRunId": "",
        },
        "ghost": {
            "id": "bc-stale-id",
            "name": "ghost-run",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-stale-id",
            "latestRunId": "run-missing",
        },
    }


def parse_status_fields(stdout: str) -> dict[str, str]:
    """Parse compact status tokens (list-row or multi-line key=value)."""
    fields: dict[str, str] = {}
    for raw in stdout.replace("\n", " ").split():
        if "=" not in raw:
            continue
        key, _, value = raw.partition("=")
        fields[key] = value
    return fields


def _status(tmp_path: Path, api: MockCursorAPI, agent_id: str, script: Path = STATUS_SH):
    env = _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY)
    return _run(script, [agent_id], env)


def test_status_sh_leftover_active_finished_prints_run_status_finished(
    tmp_path: Path,
) -> None:
    """Leftover membership ACTIVE must still show latest-run FINISHED."""
    items = _items()
    with MockCursorAPI(
        list_items=[items["leftover"]],
        run_status_by_id={"run-done": "FINISHED"},
    ) as api:
        proc = _status(tmp_path, api, "bc-leftover")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    fields = parse_status_fields(proc.stdout)
    assert fields.get("status") == "ACTIVE"
    assert fields.get("runStatus") == "FINISHED"
    assert "runStatus=RUNNING" not in proc.stdout
    assert any(path.endswith("/runs/run-done") for path in api.gets), api.gets
    assert FAKE_KEY not in proc.stdout + proc.stderr


def test_status_sh_live_active_running_prints_run_status_running(tmp_path: Path) -> None:
    items = _items()
    with MockCursorAPI(
        list_items=[items["live"]],
        run_status_by_id={"run-live": "RUNNING"},
    ) as api:
        proc = _status(tmp_path, api, "bc-live")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    fields = parse_status_fields(proc.stdout)
    assert fields.get("status") == "ACTIVE"
    assert fields.get("runStatus") == "RUNNING"
    assert "runStatus=FINISHED" not in proc.stdout
    assert any(path.endswith("/runs/run-live") for path in api.gets), api.gets
    assert FAKE_KEY not in proc.stdout + proc.stderr


def test_status_cloud_agent_alias_prints_run_status(tmp_path: Path) -> None:
    items = _items()
    with MockCursorAPI(
        list_items=[items["live"]],
        run_status_by_id={"run-live": "RUNNING"},
    ) as api:
        proc = _status(tmp_path, api, "bc-live", script=STATUS_ALIAS)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert parse_status_fields(proc.stdout).get("runStatus") == "RUNNING"


def test_status_sh_missing_latest_run_id_prints_run_status_none(tmp_path: Path) -> None:
    items = _items()
    with MockCursorAPI(list_items=[items["idle"]]) as api:
        proc = _status(tmp_path, api, "bc-idle")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    fields = parse_status_fields(proc.stdout)
    assert fields.get("status") == "ACTIVE"
    assert fields.get("runStatus") == "none"
    assert not any("/runs/" in path for path in api.gets), api.gets
    assert FAKE_KEY not in proc.stdout + proc.stderr


def test_status_sh_404_run_prints_run_status_none(tmp_path: Path) -> None:
    """Stale latestRunId must not fail status; leftover is not live."""
    items = _items()
    with MockCursorAPI(
        list_items=[items["ghost"]],
        run_not_found_ids={"run-missing"},
    ) as api:
        proc = _status(tmp_path, api, "bc-stale-id")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    fields = parse_status_fields(proc.stdout)
    assert fields.get("status") == "ACTIVE"
    assert fields.get("runStatus") == "none"
    assert any(path.endswith("/runs/run-missing") for path in api.gets), api.gets
    assert FAKE_KEY not in proc.stdout + proc.stderr


def test_status_sh_unwraps_agent_and_run_envelopes(tmp_path: Path) -> None:
    items = _items()
    leftover = dict(items["leftover"])
    with MockCursorAPI(
        list_items=[leftover],
        run_status_by_id={"run-done": "finished"},
        wrap_agent=True,
        wrap_run=True,
    ) as api:
        proc = _status(tmp_path, api, "bc-leftover")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    fields = parse_status_fields(proc.stdout)
    assert fields.get("status") == "ACTIVE"
    assert fields.get("runStatus") == "FINISHED"
    assert any(path.endswith("/runs/run-done") for path in api.gets), api.gets


def test_sdk_status_ts_prints_run_status_not_only_agent_active() -> None:
    """SDK status path already on main; lock runStatus= from collectResult."""
    status_src = STATUS_TS.read_text(encoding="utf-8")
    collect_src = COLLECT_TS.read_text(encoding="utf-8")
    assert "runStatus=" in status_src
    assert "mapRunStatus" in collect_src
    assert "listRuns" in collect_src or "getRun" in collect_src


def test_sdk_list_ts_already_prints_run_status_on_main() -> None:
    """Do not remint list.ts / cloud_list; this PR is status REST remaining."""
    list_src = (CLOUD / "sdk" / "list.ts").read_text(encoding="utf-8")
    helper = (CLOUD / "list_helper.py").read_text(encoding="utf-8")
    assert "runStatus=" in list_src
    assert "listRuns" in list_src
    assert "runStatus" in helper


def _rpc(method: str, params: dict | None = None, env: dict[str, str] | None = None) -> dict:
    msg = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    merged = {**os.environ, "GCS_ROOT": str(REPO), "GCS_MCP_NDJSON": "1"}
    if env:
        merged.update(env)
    proc = subprocess.run(
        ["python3", str(MCP), "--plane", "cloud", "--ndjson"],
        cwd=str(REPO),
        input=json.dumps(msg) + "\n",
        capture_output=True,
        text=True,
        timeout=20,
        env=merged,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.splitlines()[0])


def test_cloud_mcp_advertises_cloud_status_with_run_status() -> None:
    reply = _rpc("tools/list")
    tools = {t["name"]: t for t in reply["result"]["tools"]}
    assert "cloud_status" in tools
    desc = tools["cloud_status"]["description"]
    assert "runStatus" in desc
    assert "RUNNING" in desc
    assert "FINISHED" in desc


def test_mcp_cloud_status_prints_run_status_not_only_agent_active(tmp_path: Path) -> None:
    items = _items()
    with MockCursorAPI(
        list_items=[items["leftover"], items["live"]],
        run_status_by_id={"run-done": "FINISHED", "run-live": "RUNNING"},
    ) as api:
        env = {
            "CURSOR_API_BASE": api.base,
            "CURSOR_API_KEY": FAKE_KEY,
            "HOME": str(tmp_path),
            "CLOUD_CURL_MAX_TIME": "5",
        }
        leftover = _rpc(
            "tools/call",
            {"name": "cloud_status", "arguments": {"id": "bc-leftover"}},
            env=env,
        )
        live = _rpc(
            "tools/call",
            {"name": "cloud_status", "arguments": {"id": "bc-live"}},
            env=env,
        )
    left_text = leftover["result"]["content"][0]["text"]
    live_text = live["result"]["content"][0]["text"]
    assert leftover["result"].get("isError") is False, leftover
    assert live["result"].get("isError") is False, live
    assert parse_status_fields(left_text).get("runStatus") == "FINISHED"
    assert parse_status_fields(live_text).get("runStatus") == "RUNNING"
    assert FAKE_KEY not in left_text + live_text
