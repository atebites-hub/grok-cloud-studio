"""LIV-67: leftover ACTIVE+FINISHED must not count as a live worker.

Binding: tests parse scripts/cloud/list.sh stdout. Live workers are
latest-run runStatus=RUNNING only. Agent status=ACTIVE is membership.

#69/#73 already print runStatus on list rows. This file is the pytest that
fails when that output would still count a FINISHED leftover as live.
Does not remint list --running (#78) or the LIV-73/LIV-74 BDD suite (#82).
Never Bot CloudAgent. Model pin stays grok-4.6 xhigh, fast=false.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from test_cloud_launch import FAKE_KEY, MockCursorAPI, _run, _script_env

REPO = Path(__file__).resolve().parents[1]
CLOUD = REPO / "scripts" / "cloud"
LIST_SH = CLOUD / "list.sh"
LIST_LONG = CLOUD / "list-cloud-agents.sh"
LIST_TS = CLOUD / "sdk" / "list.ts"


def leftover_and_live_items() -> list[dict[str, Any]]:
    return [
        {
            "id": "bc-leftover",
            "name": "done-grunt",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-leftover",
            "latestRunId": "run-done",
        },
        {
            "id": "bc-live",
            "name": "busy-grunt",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-live",
            "latestRunId": "run-live",
        },
        {
            "id": "bc-idle",
            "name": "no-run",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-idle",
            "latestRunId": "",
        },
    ]


def parse_list_row(line: str) -> dict[str, str]:
    """Parse one list.sh row: key=value after LIV-67, or main-era TSV."""
    text = line.strip()
    if not text or text.startswith("CLOUD_"):
        return {}
    if "=" in text and "\t" not in text:
        fields: dict[str, str] = {}
        for tok in text.split():
            if "=" in tok:
                key, _, value = tok.partition("=")
                fields[key] = value
        return fields
    parts = text.split("\t")
    if len(parts) >= 2:
        return {
            "id": parts[0],
            "status": parts[1],
            "name": parts[2] if len(parts) > 2 else "",
            "url": parts[3] if len(parts) > 3 else "",
            "latestRunId": parts[4] if len(parts) > 4 else "",
            "runStatus": "",
        }
    return {}


def membership_active_ids(stdout: str) -> frozenset[str]:
    """Naive leftover-green counter: agent status=ACTIVE means 'live'."""
    ids: set[str] = set()
    for line in stdout.splitlines():
        fields = parse_list_row(line)
        agent_id = fields.get("id") or ""
        if agent_id and fields.get("status") == "ACTIVE":
            ids.add(agent_id)
    return frozenset(ids)


def live_ids_from_list_stdout(stdout: str) -> frozenset[str]:
    """Live workers: latest-run runStatus=RUNNING. ACTIVE is not liveness."""
    ids: set[str] = set()
    for line in stdout.splitlines():
        fields = parse_list_row(line)
        agent_id = fields.get("id") or ""
        if agent_id and fields.get("runStatus") == "RUNNING":
            ids.add(agent_id)
    return frozenset(ids)


def list_row(stdout: str, agent_id: str) -> str:
    rows = [line for line in stdout.splitlines() if agent_id in line]
    assert rows, stdout
    return rows[0]


def test_list_sh_output_does_not_count_finished_leftover_as_live(
    tmp_path: Path,
) -> None:
    """list.sh stdout must not count leftover ACTIVE+FINISHED as a live worker.

    Cloud Agents API v1 keeps agent status ACTIVE until archive. Counting
    ACTIVE rows treats leftover FINISHED grunts as spinning workers. Live
    is latest-run runStatus=RUNNING only.
    """
    items = leftover_and_live_items()
    with MockCursorAPI(
        list_items=items,
        run_status_by_id={"run-done": "FINISHED", "run-live": "RUNNING"},
    ) as api:
        env = _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY)
        listed = _run(LIST_SH, [], env)
        wrapped = _run(LIST_LONG, [], env)
    assert listed.returncode == 0, listed.stdout + listed.stderr
    assert wrapped.returncode == 0, wrapped.stdout + wrapped.stderr

    leftover = list_row(listed.stdout, "bc-leftover")
    live_row = list_row(listed.stdout, "bc-live")
    idle = list_row(listed.stdout, "bc-idle")

    naive = membership_active_ids(listed.stdout)
    live = live_ids_from_list_stdout(listed.stdout)

    # Existence: leftover is still listed (membership ACTIVE).
    assert "bc-leftover" in naive
    assert "ACTIVE" in leftover
    # The bug this binds: counting ACTIVE would treat leftover as live.
    assert "bc-leftover" in naive - live

    # Binding: leftover ACTIVE+FINISHED is not a live worker.
    assert "bc-leftover" not in live
    assert "bc-live" in live
    assert "bc-idle" not in live
    assert live == frozenset({"bc-live"})

    leftover_fields = parse_list_row(leftover)
    live_fields = parse_list_row(live_row)
    idle_fields = parse_list_row(idle)
    assert leftover_fields.get("status") == "ACTIVE"
    assert leftover_fields.get("runStatus") == "FINISHED"
    assert live_fields.get("status") == "ACTIVE"
    assert live_fields.get("runStatus") == "RUNNING"
    assert idle_fields.get("runStatus") == "none"

    wrap_live = live_ids_from_list_stdout(wrapped.stdout)
    assert "bc-leftover" not in wrap_live
    assert wrap_live == frozenset({"bc-live"})

    assert any(path.endswith("/runs/run-done") for path in api.gets), api.gets
    assert any(path.endswith("/runs/run-live") for path in api.gets), api.gets
    blob = listed.stdout + listed.stderr + wrapped.stdout + wrapped.stderr
    assert FAKE_KEY not in blob


def test_sdk_list_ts_prints_run_status_not_only_agent_active() -> None:
    """SDK list path must emit runStatus from latest run, not only ACTIVE."""
    src = LIST_TS.read_text(encoding="utf-8")
    assert "runStatus=" in src
    assert "mapRunStatus" in src
    assert "listRuns" in src or "getRun" in src
