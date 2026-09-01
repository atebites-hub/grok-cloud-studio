"""Batch status: multiple bc-ids / --ids, runStatus per id, no serial get_agent_run.

LIV-41 / LIV-67 (Living Sky): capacity beats must not serial-timeout ten
GET /v1/agents/{id}/runs/{latestRunId} calls. status.sh and
status-cloud-agent.sh accept several ids in one invocation and print
runStatus on the same line as id=. Do not remint GCS #29 list runStatus.
Never Bot CloudAgent. Model remains grok-4.6 xhigh fast=false.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from test_cloud_launch import CLOUD, EXAMPLE_REPO, FAKE_KEY, MockCursorAPI, _run, _script_env

REPO = Path(__file__).resolve().parents[1]
STATUS = CLOUD / "status.sh"
STATUS_LONG = CLOUD / "status-cloud-agent.sh"
LIST_SH = CLOUD / "list.sh"
LIST_TS = CLOUD / "sdk" / "list.ts"
STATUS_TS = CLOUD / "sdk" / "status.ts"
FOOTER = REPO / "scripts" / "directors" / "common_footer.txt"
CLOUD_README = CLOUD / "README.md"


def _items(*pairs: tuple[str, str, str]) -> list[dict[str, str]]:
    rows = []
    for agent_id, run_id, name in pairs:
        rows.append(
            {
                "id": agent_id,
                "name": name,
                "status": "ACTIVE",
                "url": f"https://cursor.com/agents/{agent_id}",
                "latestRunId": run_id,
                "repos": [{"url": EXAMPLE_REPO}],
            }
        )
    return rows


def _row(stdout: str, agent_id: str) -> str:
    needle = f"id={agent_id}"
    hits = [line for line in stdout.splitlines() if needle in line]
    assert hits, f"missing {needle} in {stdout!r}"
    with_run = [line for line in hits if "runStatus=" in line]
    return with_run[0] if with_run else hits[0]


def test_status_help_mentions_ids(tmp_path: Path) -> None:
    env = _script_env(tmp_path, "http://127.0.0.1:9", CURSOR_API_KEY=FAKE_KEY)
    proc = _run(STATUS, ["-h"], env)
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "--ids" in blob
    assert "AGENT_ID" in blob or "bc-id" in blob.lower() or "ID" in blob


def test_status_prints_runstatus_on_same_line_as_id(tmp_path: Path) -> None:
    items = _items(("bc-1", "run-1", "one"))
    with MockCursorAPI(list_items=items, run_status_by_id={"run-1": "FINISHED"}) as api:
        proc = _run(STATUS, ["bc-1"], _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY))
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    row = _row(proc.stdout, "bc-1")
    assert "runStatus=FINISHED" in row
    assert "run_status=" not in blob
    assert FAKE_KEY not in blob


def test_status_accepts_multiple_positional_ids(tmp_path: Path) -> None:
    items = _items(
        ("bc-live", "run-live", "busy"),
        ("bc-done", "run-done", "leftover"),
    )
    with MockCursorAPI(
        list_items=items,
        run_status_by_id={"run-live": "RUNNING", "run-done": "FINISHED"},
    ) as api:
        proc = _run(
            STATUS,
            ["bc-live", "bc-done"],
            _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY),
        )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    assert "runStatus=RUNNING" in _row(proc.stdout, "bc-live")
    assert "runStatus=FINISHED" in _row(proc.stdout, "bc-done")
    assert FAKE_KEY not in blob


def test_status_cloud_agent_accepts_ids_flag(tmp_path: Path) -> None:
    items = _items(
        ("bc-a", "run-a", "a"),
        ("bc-b", "run-b", "b"),
        ("bc-c", "run-c", "c"),
    )
    with MockCursorAPI(
        list_items=items,
        run_status_by_id={"run-a": "RUNNING", "run-b": "FINISHED", "run-c": "CREATING"},
    ) as api:
        env = _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY)
        comma = _run(STATUS_LONG, ["--ids", "bc-a,bc-b"], env)
        equals = _run(STATUS, ["--ids=bc-b,bc-c"], env)
    assert comma.returncode == 0, comma.stdout + comma.stderr
    assert equals.returncode == 0, equals.stdout + equals.stderr
    assert "runStatus=RUNNING" in _row(comma.stdout, "bc-a")
    assert "runStatus=FINISHED" in _row(comma.stdout, "bc-b")
    assert "runStatus=FINISHED" in _row(equals.stdout, "bc-b")
    assert "runStatus=CREATING" in _row(equals.stdout, "bc-c")


def test_status_json_array_for_multiple_ids(tmp_path: Path) -> None:
    items = _items(("bc-1", "run-1", "one"), ("bc-2", "run-2", "two"))
    with MockCursorAPI(
        list_items=items,
        run_status_by_id={"run-1": "FINISHED", "run-2": "RUNNING"},
    ) as api:
        proc = _run(
            STATUS,
            ["--json", "--ids", "bc-1,bc-2"],
            _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY),
        )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert isinstance(payload, list)
    by_id = {row["id"]: row for row in payload}
    assert by_id["bc-1"]["runStatus"] == "FINISHED"
    assert by_id["bc-2"]["runStatus"] == "RUNNING"
    assert FAKE_KEY not in proc.stdout + proc.stderr


def test_status_batch_does_not_serial_timeout_ten_get_agent_run(tmp_path: Path) -> None:
    n = 10
    delay = 0.4
    items = _items(*((f"bc-{i}", f"run-{i}", f"g{i}") for i in range(n)))
    run_status_by_id = {f"run-{i}": "RUNNING" if i % 2 == 0 else "FINISHED" for i in range(n)}
    ids = [f"bc-{i}" for i in range(n)]
    with MockCursorAPI(
        list_items=items,
        run_status_by_id=run_status_by_id,
        run_delay_sec=delay,
    ) as api:
        env = _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY)
        started = time.monotonic()
        proc = _run(STATUS, ["--ids", ",".join(ids)], env, timeout=8)
        elapsed = time.monotonic() - started
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    serial_floor = delay * n * 0.8
    assert elapsed < serial_floor, (
        f"status --ids serial-timed out-ish: elapsed={elapsed:.2f}s "
        f"serial~{delay * n:.1f}s for {n} get_agent_run calls"
    )
    run_gets = [path for path in api.gets if "/runs/" in path]
    assert len(run_gets) == n
    assert "runStatus=RUNNING" in _row(proc.stdout, "bc-0")
    assert "runStatus=FINISHED" in _row(proc.stdout, "bc-1")
    assert FAKE_KEY not in blob


def test_list_does_not_remint_issue_29_runstatus(tmp_path: Path) -> None:
    """Capacity path is status --ids, not list.sh serial get_agent_run (#29)."""
    items = _items(*((f"bc-{i}", f"run-{i}", f"g{i}") for i in range(3)))
    with MockCursorAPI(list_items=items, run_delay_sec=0.4) as api:
        proc = _run(LIST_SH, [], _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY), timeout=5)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not any("/runs/" in path for path in api.gets)
    list_ts = LIST_TS.read_text(encoding="utf-8")
    list_sh = LIST_SH.read_text(encoding="utf-8")
    assert "runStatus=" not in list_ts
    assert "runStatus=" not in list_sh


def test_sdk_status_source_batches_ids() -> None:
    src = STATUS_TS.read_text(encoding="utf-8")
    assert "--ids" in src
    assert "Promise.all" in src or "allSettled" in src
    assert "runStatus=" in src


def test_docs_and_footer_show_batch_status() -> None:
    footer = FOOTER.read_text(encoding="utf-8")
    readme = CLOUD_README.read_text(encoding="utf-8")
    assert "--ids" in footer
    assert "runStatus" in footer
    assert "--ids" in readme
    assert "runStatus" in readme
    assert "never bot cloudagent" in footer.lower()
    assert "grok-4.6" in footer and "xhigh" in footer
    assert "fast=false" in footer
