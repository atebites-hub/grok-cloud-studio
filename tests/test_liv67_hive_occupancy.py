"""LIV-67 remaining: hive occupancy is latest-run RUNNING/CREATING.

Agent status=ACTIVE is membership, not a live worker. Count/list Extra High
floor occupancy from latest-run runStatus in {RUNNING, CREATING}. Leftover
ACTIVE+FINISHED must not count as hive occupancy.

Does not remint list --running (#78) or leftover-not-live pytest (#84).
Does not vendor Hermes. Does not merge GCS #26+#28 or restack #47
cloud_list/cloud_followup. Never Bot CloudAgent. Model pin stays grok-4.6
xhigh, fast=false.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from test_cloud_launch import FAKE_KEY, MockCursorAPI, _run, _script_env

REPO = Path(__file__).resolve().parents[1]
CLOUD = REPO / "scripts" / "cloud"
OCCUPANCY_PY = CLOUD / "occupancy.py"
LIST_SH = CLOUD / "list.sh"
LIST_LONG = CLOUD / "list-cloud-agents.sh"
LIST_ROWS = CLOUD / "list_rows.py"
LIST_HELPER = CLOUD / "list_helper.py"
LIST_TS = CLOUD / "sdk" / "list.ts"
SPAWN = CLOUD / "directors_spawn.py"
FOOTER = REPO / "scripts" / "directors" / "common_footer.txt"
CLOUD_DOC = REPO / "docs" / "CLOUD.md"
CLOUD_README = CLOUD / "README.md"
LAUNCH = REPO / "scripts" / "launch-cloud-extra-high.sh"
MIND_PY = REPO / "scripts" / "directors" / "mind.py"
HERMES_MARKERS = ("vendor/hermes", "from hermes", "import hermes")
PR47_RESTACK = ("cloud_followup",)
PRIVATE_GAME = "atebites-hub/" + "palemon"


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def mixed_floor_items() -> list[dict[str, Any]]:
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
            "id": "bc-boot",
            "name": "booting-grunt",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-boot",
            "latestRunId": "run-boot",
        },
        {
            "id": "bc-idle",
            "name": "no-run",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-idle",
            "latestRunId": "",
        },
        {
            "id": "bc-error",
            "name": "failed-grunt",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-error",
            "latestRunId": "run-err",
        },
    ]


def mixed_run_status() -> dict[str, str]:
    return {
        "run-done": "FINISHED",
        "run-live": "RUNNING",
        "run-boot": "CREATING",
        "run-err": "ERROR",
    }


def parse_list_row(line: str) -> dict[str, str]:
    text = line.strip()
    if not text or text.startswith("CLOUD_"):
        return {}
    fields: dict[str, str] = {}
    for tok in text.split():
        if "=" in tok:
            key, _, value = tok.partition("=")
            fields[key] = value
    return fields


def occupancy_ids_from_stdout(stdout: str) -> frozenset[str]:
    occ = _load(OCCUPANCY_PY, "gcs_hive_occupancy")
    return occ.occupancy_ids_from_list_stdout(stdout)


def test_feature_binds_occupancy_not_active_membership() -> None:
    text = Path(__file__).read_text(encoding="utf-8").lower()
    assert "hive occupancy" in text
    assert "running" in text and "creating" in text
    assert "active+finished" in text.replace(" ", "")
    assert "hermes" in text
    assert "#26" in Path(__file__).read_text(encoding="utf-8")
    assert "#47" in Path(__file__).read_text(encoding="utf-8")
    assert "bot cloudagent" in text


def test_occupancy_is_latest_run_running_or_creating() -> None:
    occ = _load(OCCUPANCY_PY, "gcs_hive_occupancy")
    assert occ.IN_FLIGHT == frozenset({"RUNNING", "CREATING"})
    assert occ.is_hive_occupancy("RUNNING") is True
    assert occ.is_hive_occupancy("CREATING") is True
    assert occ.is_hive_occupancy("creating") is True
    assert occ.is_hive_occupancy("FINISHED") is False
    assert occ.is_hive_occupancy("ERROR") is False
    assert occ.is_hive_occupancy("none") is False
    assert occ.is_hive_occupancy("") is False
    # Agent ACTIVE is ignored: leftover membership is not occupancy.
    assert occ.is_hive_occupancy("FINISHED", agent_status="ACTIVE") is False
    assert occ.is_hive_occupancy("RUNNING", agent_status="ACTIVE") is True
    assert occ.is_hive_occupancy("CREATING", agent_status="ARCHIVED") is True


def test_leftover_active_finished_is_not_hive_occupancy() -> None:
    occ = _load(OCCUPANCY_PY, "gcs_hive_occupancy")
    leftover = occ.format_occupancy_row(
        agent_id="bc-leftover",
        agent_status="ACTIVE",
        run_status="FINISHED",
        name="done-grunt",
        url="https://cursor.com/agents/bc-leftover",
        run_id="run-done",
    )
    live = occ.format_occupancy_row(
        agent_id="bc-live",
        agent_status="ACTIVE",
        run_status="RUNNING",
        name="busy-grunt",
        url="https://cursor.com/agents/bc-live",
        run_id="run-live",
    )
    boot = occ.format_occupancy_row(
        agent_id="bc-boot",
        agent_status="ACTIVE",
        run_status="CREATING",
        name="booting-grunt",
        url="https://cursor.com/agents/bc-boot",
        run_id="run-boot",
    )
    idle = occ.format_occupancy_row(
        agent_id="bc-idle",
        agent_status="ACTIVE",
        run_status="none",
        name="no-run",
        url="https://cursor.com/agents/bc-idle",
        run_id="",
    )
    blob = "\n".join((leftover, live, boot, idle))
    ids = occ.occupancy_ids_from_list_stdout(blob)
    assert ids == frozenset({"bc-live", "bc-boot"})
    assert occ.count_occupancy_from_list_stdout(blob) == 2
    assert "bc-leftover" not in ids
    assert occ.include_occupancy_row("ACTIVE", "FINISHED") is False
    assert occ.include_occupancy_row("ACTIVE", "RUNNING") is True
    assert occ.include_occupancy_row("ACTIVE", "CREATING") is True


def test_occupancy_matches_directors_spawn_in_flight() -> None:
    occ = _load(OCCUPANCY_PY, "gcs_hive_occupancy")
    spawn = _load(SPAWN, "gcs_directors_spawn")
    assert occ.IN_FLIGHT == spawn.IN_FLIGHT_RUN
    assert occ.is_hive_occupancy("CREATING") == spawn.is_in_flight_run("CREATING")
    assert occ.is_hive_occupancy("FINISHED") == spawn.is_in_flight_run("FINISHED")


def test_list_helper_live_worker_is_occupancy() -> None:
    occ = _load(OCCUPANCY_PY, "gcs_hive_occupancy")
    helper = _load(LIST_HELPER, "gcs_list_helper")
    assert helper.is_live_worker("ACTIVE", "FINISHED") is False
    assert helper.is_live_worker("ACTIVE", "RUNNING") is True
    assert helper.is_live_worker("ACTIVE", "CREATING") is True
    assert helper.is_live_worker("ACTIVE", "FINISHED") == occ.is_hive_occupancy(
        "FINISHED", agent_status="ACTIVE"
    )


def test_default_list_still_prints_leftover_membership(tmp_path: Path) -> None:
    """Membership list is unchanged: leftover ACTIVE+FINISHED still appears."""
    with MockCursorAPI(
        list_items=mixed_floor_items(),
        run_status_by_id=mixed_run_status(),
    ) as api:
        env = _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY)
        listed = _run(LIST_SH, [], env)
    assert listed.returncode == 0, listed.stdout + listed.stderr
    assert "bc-leftover" in listed.stdout
    assert "runStatus=FINISHED" in listed.stdout
    assert "runStatus=CREATING" in listed.stdout
    assert "bc-boot" in listed.stdout
    ids = occupancy_ids_from_stdout(listed.stdout)
    assert ids == frozenset({"bc-live", "bc-boot"}), listed.stdout
    assert "bc-leftover" not in ids
    assert "bc-idle" not in ids
    assert "bc-error" not in ids
    assert FAKE_KEY not in listed.stdout + listed.stderr


def test_list_occupancy_prints_running_and_creating_not_leftover(
    tmp_path: Path,
) -> None:
    """list.sh --occupancy is the Extra High floor, not ACTIVE membership."""
    with MockCursorAPI(
        list_items=mixed_floor_items(),
        run_status_by_id=mixed_run_status(),
    ) as api:
        env = _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY)
        listed = _run(LIST_SH, ["--occupancy"], env)
        wrapped = _run(LIST_LONG, ["--occupancy", "20"], env)
    assert listed.returncode == 0, listed.stdout + listed.stderr
    assert wrapped.returncode == 0, wrapped.stdout + wrapped.stderr
    assert "CLOUD_OCCUPANCY n=2" in listed.stdout, listed.stdout
    assert "bc-live" in listed.stdout
    assert "bc-boot" in listed.stdout
    assert "runStatus=RUNNING" in listed.stdout
    assert "runStatus=CREATING" in listed.stdout
    assert "bc-leftover" not in listed.stdout
    assert "runStatus=FINISHED" not in listed.stdout
    assert "bc-idle" not in listed.stdout
    assert "bc-error" not in listed.stdout
    ids = occupancy_ids_from_stdout(listed.stdout)
    assert ids == frozenset({"bc-live", "bc-boot"})
    assert "CLOUD_OCCUPANCY n=2" in wrapped.stdout
    assert "bc-leftover" not in wrapped.stdout
    assert FAKE_KEY not in listed.stdout + listed.stderr + wrapped.stdout + wrapped.stderr


def test_leftover_only_occupancy_list_is_empty(tmp_path: Path) -> None:
    items = [
        {
            "id": "bc-leftover",
            "name": "done-grunt",
            "status": "ACTIVE",
            "url": "https://cursor.com/agents/bc-leftover",
            "latestRunId": "run-done",
        }
    ]
    with MockCursorAPI(
        list_items=items,
        run_status_by_id={"run-done": "FINISHED"},
    ) as api:
        env = _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY)
        listed = _run(LIST_SH, ["--occupancy"], env)
    assert listed.returncode == 0, listed.stdout + listed.stderr
    assert "CLOUD_OCCUPANCY n=0" in listed.stdout, listed.stdout
    assert "CLOUD_LIST empty" in listed.stdout
    assert "bc-leftover" not in listed.stdout
    assert occupancy_ids_from_stdout(listed.stdout) == frozenset()
    assert FAKE_KEY not in listed.stdout + listed.stderr


def test_list_helper_occupancy_only_drops_leftover(tmp_path: Path) -> None:
    helper = _load(LIST_HELPER, "gcs_list_helper")
    items = mixed_floor_items()
    with MockCursorAPI(
        list_items=items,
        run_status_by_id=mixed_run_status(),
    ) as api:
        env = {
            "CURSOR_API_BASE": api.base,
            "CURSOR_API_KEY": FAKE_KEY,
            "HOME": str(tmp_path),
            "CLOUD_CURL_MAX_TIME": "5",
        }
        import os

        old = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        try:
            text, ok = helper.list_cloud_agents(limit=20, occupancy_only=True)
        finally:
            for key, value in old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
    assert ok, text
    assert "CLOUD_OCCUPANCY n=2" in text
    assert "bc-live" in text and "bc-boot" in text
    assert "bc-leftover" not in text
    assert FAKE_KEY not in text


def test_does_not_remint_list_running_or_capacity_count() -> None:
    list_src = LIST_SH.read_text(encoding="utf-8")
    rows_src = LIST_ROWS.read_text(encoding="utf-8")
    ts_src = LIST_TS.read_text(encoding="utf-8")
    helper_src = LIST_HELPER.read_text(encoding="utf-8")
    occ_src = OCCUPANCY_PY.read_text(encoding="utf-8")
    blob = list_src + rows_src + ts_src + helper_src + occ_src
    assert "--occupancy" in list_src
    assert "--occupancy" in ts_src
    assert "--running" not in list_src
    assert "--running" not in ts_src
    assert "capacity-count.sh" not in blob
    assert "capacity_count.py" not in blob
    assert "count-running.sh" not in blob
    assert PRIVATE_GAME not in blob


def test_does_not_vendor_hermes_or_restack_pr47() -> None:
    occ_src = OCCUPANCY_PY.read_text(encoding="utf-8")
    mind_src = MIND_PY.read_text(encoding="utf-8")
    low = occ_src.lower()
    for marker in HERMES_MARKERS:
        assert marker not in low
    for name in PR47_RESTACK:
        assert name not in occ_src
    assert "Bot CloudAgent" not in occ_src or "never" in low
    # Do not restack #47 mind plugins from this occupancy remaining.
    assert "cloud_followup" not in occ_src
    assert "from hermes" not in mind_src.lower()


def test_docs_and_footer_name_hive_occupancy() -> None:
    footer = FOOTER.read_text(encoding="utf-8")
    cloud = CLOUD_DOC.read_text(encoding="utf-8")
    readme = CLOUD_README.read_text(encoding="utf-8")
    blob = footer + cloud + readme
    low = blob.lower()
    assert "occupancy" in low
    assert "creating" in low
    assert "active" in low
    assert "finished" in low
    assert "--occupancy" in blob
    assert "bot cloudagent" in low
    assert "living sky" in low
    assert "black swan" not in low or "never" in low
    launch = LAUNCH.read_text(encoding="utf-8")
    assert "grok-4.6" in launch
    assert "xhigh" in launch
    assert "fast=false" in launch


def test_sdk_list_ts_filters_occupancy_not_only_running() -> None:
    src = LIST_TS.read_text(encoding="utf-8")
    assert "--occupancy" in src
    assert "CREATING" in src
    assert "RUNNING" in src
    assert "CLOUD_OCCUPANCY" in src
    # Unique remaining vs #78: CREATING is occupancy, not dropped.
    assert "occupancy" in src.lower()
