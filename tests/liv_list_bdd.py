"""Shared helpers for LIV-67 / LIV-73 / LIV-74 list runStatus BDD evidence.

Not a test module. Palemon Linear is Living Sky LIV. Never Bot CloudAgent.
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
LIST_ROWS = CLOUD / "list_rows.py"
FEATURE_67 = REPO / "tests" / "features" / "liv67_list_prints_runstatus.feature"
FEATURE_73 = REPO / "tests" / "features" / "liv73_failing_then_passing.feature"
FEATURE_74 = REPO / "tests" / "features" / "liv74_demonstrated_n.feature"
DEMONSTRATE = REPO / "scripts" / "studio" / "demonstrate_bdd.sh"
PYTEST_INI = REPO / "pytest.ini"
PRIVATE_GAME = "atebites-hub/" + "palemon"
SIBLING_NEEDLES = ("--repo", "--running", "MUST_LAUNCH", "count-running", "cloud_list")


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


def list_row(stdout: str, agent_id: str) -> str:
    rows = [line for line in stdout.splitlines() if agent_id in line]
    assert rows, stdout
    return rows[0]


def main_era_tsv_row(item: dict[str, Any]) -> str:
    """Membership-only TSV that list.sh printed on main before LIV-67."""
    return "\t".join(
        [
            str(item.get("id") or ""),
            str(item.get("status") or ""),
            str(item.get("name") or ""),
            str(item.get("url") or ""),
            str(item.get("latestRunId") or ""),
        ]
    )


def run_list(
    tmp_path: Path, items: list[dict[str, Any]], **mock_kw: Any
) -> tuple[MockCursorAPI, Any, Any]:
    with MockCursorAPI(list_items=items, **mock_kw) as api:
        env = _script_env(tmp_path, api.base, CURSOR_API_KEY=FAKE_KEY)
        listed = _run(LIST_SH, [], env)
        long_name = _run(LIST_LONG, [], env)
    return api, listed, long_name


def list_source_blob() -> str:
    parts = [LIST_SH, LIST_LONG, LIST_TS]
    if LIST_ROWS.is_file():
        parts.append(LIST_ROWS)
    return "".join(path.read_text(encoding="utf-8") for path in parts)
