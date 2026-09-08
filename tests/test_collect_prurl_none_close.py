"""Collect prUrl URL vs none: leftover of merged shard is CLOSE.

Unique remaining vs origin/main: scripts/cloud/result-cloud-agent.sh
collect JSON with prUrl null/empty means Directors CLOSE. No
MERGE_REQUEST. No twin Extra High.

Distinct from waiter-owner-seat-tandem (GCS #172, already RUNNING) and
occupancy remint (#125 / #132 / #154). Do not remint those. Do not clone
LIV-41/67/85/82. Do not touch start-studio-bus. Do not vendor Hermes.
Do not merge GCS #26/#28. Do not land palemon leftover #165/#167.
Never Bot CloudAgent. Living Sky Linear (LIV). Extra High stays
grok-4.6 xhigh fast=false.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cloud"))

from collect_close import (  # noqa: E402
    CLOSE,
    attach_director_action,
    director_action,
    pr_url_or_none,
)
from fleet_ledger import notify_text  # noqa: E402
from result_payload import director_result  # noqa: E402
from test_cloud_launch import FAKE_KEY, MockCursorAPI, _run, _script_env  # noqa: E402

FEATURE = ROOT / "tests" / "features" / "collect_prurl_none_close.feature"
COLLECT_CLOSE = ROOT / "scripts" / "cloud" / "collect_close.py"
COLLECT_TS = ROOT / "scripts" / "cloud" / "sdk" / "collect.ts"
RESULT_SH = ROOT / "scripts" / "cloud" / "result-cloud-agent.sh"
RESULT_TS = ROOT / "scripts" / "cloud" / "sdk" / "result.ts"
WAIT_TS = ROOT / "scripts" / "cloud" / "sdk" / "wait-notify.ts"
FOOTER = ROOT / "scripts" / "directors" / "common_footer.txt"
CLOUD_DOC = ROOT / "docs" / "CLOUD.md"
CLOUD_README = ROOT / "scripts" / "cloud" / "README.md"
ARCH = ROOT / "docs" / "ARCHITECTURE.md"
SPAWN_WAITER = ROOT / "scripts" / "cloud" / "spawn-waiter.sh"
OCCUPANCY = ROOT / "scripts" / "cloud" / "occupancy-count.sh"
BUS = ROOT / "scripts" / "a2a" / "start-studio-bus.sh"
HERMES_VENDOR = ROOT / "NousResearch" / "hermes-agent"
GCS_PR = "https://github.com/atebites-hub/grok-cloud-studio/pull/172"
MERGE_READY = "ping QA (odd→qa-a, even→qa-b) MERGE_REQUEST"
BLACK_SWAN = "blackswan" + ".money"
_PASTE = (
    ".venv/bin/pytest -q\n"
    "3 passed in 0.01s\n"
    "python3 scripts/secret_scan.py\n"
    "secret_scan=clean\n"
)


def _result_json(home: Path, base: str, **extra: str) -> tuple[dict, str, str]:
    env = _script_env(
        home,
        base,
        CURSOR_API_KEY=FAKE_KEY,
        GITHUB_API_BASE="http://127.0.0.1:1",
        **extra,
    )
    proc = _run(RESULT_SH, ["bc-close"], env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    return payload, proc.stdout, proc.stderr


def test_feature_file_states_url_vs_none_and_leftover_close() -> None:
    text = FEATURE.read_text(encoding="utf-8")
    fold = " ".join(text.lower().split())
    assert FEATURE.is_file()
    assert "prurl" in fold and "url vs none" in fold
    assert "leftover of merged shard is close" in fold
    assert "result-cloud-agent.sh" in text
    assert "MERGE_REQUEST" in text
    assert "twin Extra High" in text or "twin extra high" in fold
    assert "waiter-owner-seat-tandem" in fold
    assert "occupancy remint" in fold
    assert "#125" in text and "#132" in text and "#154" in text
    assert "start-studio-bus" in fold
    assert "hermes" in fold
    assert "#26" in text and "#28" in text
    assert "#165" in text and "#167" in text
    assert "bot cloudagent" in fold
    assert "liv-41" in fold or "liv-41/67/85/82" in fold
    assert BLACK_SWAN not in fold


def test_pr_url_or_none_url_vs_none() -> None:
    assert pr_url_or_none(GCS_PR) == GCS_PR
    assert pr_url_or_none(GCS_PR + "/files") == GCS_PR + "/files"
    assert pr_url_or_none(None) is None
    assert pr_url_or_none("") is None
    assert pr_url_or_none("   ") is None
    assert pr_url_or_none("none") is None
    assert pr_url_or_none("NONE") is None
    assert pr_url_or_none("null") is None
    assert pr_url_or_none("not-a-url") is None


def test_director_action_finished_none_is_close() -> None:
    assert director_action({"runStatus": "FINISHED", "prUrl": None}) == CLOSE
    assert director_action({"runStatus": "FINISHED", "prUrl": ""}) == CLOSE
    assert director_action({"runStatus": "FINISHED", "prUrl": "none"}) == CLOSE
    assert director_action({"runStatus": "FINISHED", "prUrl": "  "}) == CLOSE


def test_director_action_finished_url_is_not_close() -> None:
    assert director_action({"runStatus": "FINISHED", "prUrl": GCS_PR}) is None
    attached = attach_director_action({"runStatus": "FINISHED", "prUrl": GCS_PR})
    assert attached["prUrl"] == GCS_PR
    assert attached["directorAction"] is None


def test_director_action_running_none_is_not_close() -> None:
    """Live Extra High with no PR yet must not CLOSE."""
    assert director_action({"runStatus": "RUNNING", "prUrl": None}) is None
    assert director_action({"runStatus": "CREATING", "prUrl": None}) is None


def test_notify_text_finished_prurl_none_is_close_not_merge_request() -> None:
    text = notify_text(
        "bc-none",
        {"runStatus": "FINISHED", "prUrl": None, "name": "merged-shard"},
    )
    assert text.startswith("FLEET_DONE / CLOSE:")
    assert "pr=none" in text
    assert MERGE_READY not in text
    assert "PR_READY" not in text
    assert "result-cloud-agent.sh bc-none" in text
    assert "leftover of merged shard is CLOSE" in text
    assert "twin Extra High" in text
    assert "do not ping QA MERGE_REQUEST" in text


def test_notify_text_finished_prurl_empty_and_none_token_are_close() -> None:
    for raw in ("", "none", "null", "  "):
        text = notify_text("bc-empty", {"runStatus": "FINISHED", "prUrl": raw, "name": "shard"})
        assert "FLEET_DONE / CLOSE:" in text, raw
        assert MERGE_READY not in text, raw
        assert "do not ping QA MERGE_REQUEST" in text, raw


def test_notify_text_finished_prurl_url_is_not_close() -> None:
    text = notify_text(
        "bc-url",
        {
            "runStatus": "FINISHED",
            "prUrl": GCS_PR,
            "name": "has-pr",
            "shipGateOk": True,
            "emptyChecks": False,
            "checkRuns": 1,
            "result": _PASTE,
        },
    )
    assert "FLEET_DONE / CLOSE:" not in text
    assert "PR_READY" in text
    assert MERGE_READY in text


def test_director_result_finished_without_git_is_close() -> None:
    payload = attach_director_action(
        director_result({"id": "bc-close", "name": "shard"}, {"id": "run-1", "status": "FINISHED"})
    )
    assert payload["prUrl"] is None
    assert payload["directorAction"] == CLOSE
    assert payload["runStatus"] == "FINISHED"


def test_director_result_finished_with_prurl_is_not_close() -> None:
    run = {
        "id": "run-1",
        "status": "FINISHED",
        "git": {"branches": [{"branch": "cursor/shard", "prUrl": GCS_PR}]},
    }
    payload = attach_director_action(director_result({"id": "bc-url"}, run))
    assert payload["prUrl"] == GCS_PR
    assert payload["directorAction"] is None


def test_result_cloud_agent_collect_prurl_none_is_close(tmp_path: Path) -> None:
    with MockCursorAPI(run_statuses=["FINISHED"]) as api:
        payload, out, err = _result_json(tmp_path, api.base)
    assert payload["prUrl"] is None
    assert payload["runStatus"] == "FINISHED"
    assert payload["directorAction"] == CLOSE
    assert FAKE_KEY not in out + err
    assert "MERGE_REQUEST" not in out


def test_result_cloud_agent_collect_prurl_url_is_not_close(tmp_path: Path) -> None:
    git = {
        "branches": [
            {
                "repoUrl": "github.com/atebites-hub/grok-cloud-studio",
                "branch": "cursor/has-pr",
                "prUrl": GCS_PR,
            }
        ]
    }
    with MockCursorAPI(run_statuses=["FINISHED"], run_git=git) as api:
        payload, out, err = _result_json(tmp_path, api.base)
    assert payload["prUrl"] == GCS_PR
    assert payload.get("directorAction") != CLOSE
    assert FAKE_KEY not in out + err


def test_result_cloud_agent_collect_running_prurl_none_is_not_close(tmp_path: Path) -> None:
    with MockCursorAPI(run_statuses=["RUNNING"]) as api:
        payload, _, err = _result_json(tmp_path, api.base)
    assert payload["prUrl"] is None
    assert payload["runStatus"] == "RUNNING"
    assert payload.get("directorAction") != CLOSE
    assert FAKE_KEY not in err


def test_collect_sources_attach_director_action() -> None:
    collect = COLLECT_TS.read_text(encoding="utf-8")
    helper = COLLECT_CLOSE.read_text(encoding="utf-8")
    result_sh = RESULT_SH.read_text(encoding="utf-8")
    result_ts = RESULT_TS.read_text(encoding="utf-8")
    waiter = WAIT_TS.read_text(encoding="utf-8")
    assert "directorAction" in collect or "attachDirectorAction" in collect
    assert "CLOSE" in collect
    assert "attach_director_action" in helper or "directorAction" in helper
    assert "collect_close" in result_sh or "directorAction" in result_sh or "result_payload" in result_sh
    assert "collectResult" in result_ts
    assert "attachDirectorAction" in waiter or "directorAction" in waiter
    assert "Bot CloudAgent" in helper
    assert "NousResearch/hermes-agent" not in collect
    assert "start-studio-bus" not in collect


def test_footer_and_docs_close_when_prurl_none() -> None:
    footer = FOOTER.read_text(encoding="utf-8")
    cloud = CLOUD_DOC.read_text(encoding="utf-8")
    readme = CLOUD_README.read_text(encoding="utf-8")
    arch = ARCH.read_text(encoding="utf-8")
    blob = "\n".join((footer, cloud, readme, arch))
    fold = blob.lower()
    assert "result-cloud-agent.sh" in blob
    assert "prurl" in fold or "prUrl" in blob
    assert "CLOSE" in blob
    assert "leftover of merged shard is CLOSE" in blob
    assert "MERGE_REQUEST" in blob
    assert "twin" in fold
    assert "Bot CloudAgent" in blob
    assert BLACK_SWAN not in fold


def test_does_not_remint_tandem_or_occupancy_or_bus() -> None:
    spawn = SPAWN_WAITER.read_text(encoding="utf-8")
    occ = OCCUPANCY.read_text(encoding="utf-8")
    bus = BUS.read_text(encoding="utf-8")
    helper = COLLECT_CLOSE.read_text(encoding="utf-8")
    assert "GCS_DIRECTOR_SEAT" in spawn
    assert "Do not remint" in spawn or "do not remint" in spawn.lower()
    assert "CLOUD_OCCUPANCY" in occ or "occupancy" in occ.lower()
    assert "nextCursor" in occ or "paginate" in occ.lower()
    assert BUS.is_file()
    assert "start-studio-bus" in bus or "hub" in bus.lower()
    assert "Do not remint" in helper or "do not remint" in helper.lower()
    assert "waiter-owner-seat-tandem" in helper
    assert "occupancy remint" in helper.lower() or "#125" in helper
    assert "#26" in helper and "#28" in helper
    assert "Bot CloudAgent" in helper
    assert not HERMES_VENDOR.exists()
    assert "NousResearch/hermes-agent" not in helper


def test_collect_close_never_prints_keys() -> None:
    helper = COLLECT_CLOSE.read_text(encoding="utf-8")
    assert "CURSOR_API_KEY=" not in helper or "never print" in helper.lower()
    assert "LINEAR_API_KEY=" not in helper or "never print" in helper.lower()
    assert BLACK_SWAN not in helper.lower()
