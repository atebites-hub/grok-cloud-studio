"""LIV-76: archive Done/Canceled for the 200 cap; never delete.

GCS #45 purge-delete (issueDelete / permanentlyDelete) is the wrong mechanic.
Close stale Living Sky tickets, then GraphQL issueArchive. Linear MCP has no
archive mutation. Never Black Swan Money.
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "linear_archive_closed.py"
sys.path.insert(0, str(ROOT / "scripts"))

from linear_archive_closed import (  # noqa: E402
    ARCHIVE_STATE_NAMES,
    FREE_TIER_CAP,
    LINEAR_GRAPHQL,
    MUTATION_ISSUE_ARCHIVE,
    MUTATION_ISSUE_UPDATE,
    STALE_DAYS_DEFAULT,
    classify_issue,
    load_api_key,
    main,
    redact,
)

NOW = datetime(2026, 9, 2, 1, 0, tzinfo=timezone.utc)
BLACK_SWAN = "Black Swan Money"
PRIVATE_GAME = "atebites-hub/" + "palemon"


def _iso(days_ago: int) -> str:
    return (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _issue(
    *,
    identifier: str = "LIV-1",
    title: str = "closed living sky bug",
    state_name: str = "Done",
    state_type: str = "completed",
    team_key: str = "LIV",
    team_name: str = "Living Sky",
    archived: bool = False,
    issue_id: str = "issue-uuid-1",
    updated_days_ago: int = 40,
) -> dict[str, Any]:
    return {
        "id": issue_id,
        "identifier": identifier,
        "title": title,
        "url": f"https://linear.app/livingsky/issue/{identifier}",
        "updatedAt": _iso(updated_days_ago),
        "archivedAt": "2026-01-01T00:00:00.000Z" if archived else None,
        "state": {"name": state_name, "type": state_type},
        "team": {"id": "team-liv", "key": team_key, "name": team_name},
    }


class FakeGraphQL:
    def __init__(self, pages: list[list[dict[str, Any]]]) -> None:
        self.pages = pages
        self.queries: list[str] = []
        self.variables: list[dict[str, Any]] = []
        self.archive_ids: list[str] = []
        self.update_ids: list[str] = []
        self.update_state_ids: list[str] = []
        self.delete_ids: list[str] = []

    def __call__(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        variables = variables or {}
        self.queries.append(query)
        self.variables.append(variables)
        if "issueDelete" in query or "permanentlyDelete" in query:
            self.delete_ids.append(str(variables.get("id") or ""))
            raise AssertionError("LIV-76 must not call issueDelete/permanentlyDelete")
        if "issueArchive" in query:
            if "trash" in query.lower() and "true" in query.lower():
                raise AssertionError("LIV-76 must not trash issues")
            issue_id = str(variables.get("id") or "")
            self.archive_ids.append(issue_id)
            return {"data": {"issueArchive": {"success": True}}}
        if "issueUpdate" in query:
            issue_id = str(variables.get("id") or "")
            self.update_ids.append(issue_id)
            payload = variables.get("input") or {}
            self.update_state_ids.append(str(payload.get("stateId") or ""))
            return {
                "data": {
                    "issueUpdate": {
                        "success": True,
                        "issue": {"id": issue_id, "identifier": "LIV-updated"},
                    }
                }
            }
        if "teams(" in query or "workflowStates" in query or "states" in query:
            return {
                "data": {
                    "teams": {
                        "nodes": [
                            {
                                "id": "team-liv",
                                "key": "LIV",
                                "name": "Living Sky",
                                "states": {
                                    "nodes": [
                                        {
                                            "id": "state-canceled",
                                            "name": "Canceled",
                                            "type": "canceled",
                                        },
                                        {
                                            "id": "state-done",
                                            "name": "Done",
                                            "type": "completed",
                                        },
                                    ]
                                },
                            }
                        ]
                    }
                }
            }
        after = variables.get("after")
        index = 0
        if after:
            index = int(str(after).split("-")[-1]) + 1
        nodes = self.pages[index] if index < len(self.pages) else []
        has_next = index + 1 < len(self.pages)
        return {
            "data": {
                "issues": {
                    "nodes": nodes,
                    "pageInfo": {
                        "hasNextPage": has_next,
                        "endCursor": f"cursor-{index}" if has_next else None,
                    },
                }
            }
        }


def _run_main(
    argv: list[str],
    graphql: FakeGraphQL,
    *,
    env: dict[str, str] | None = None,
    token: str = "lin_api_test_token_not_a_real_secret",
) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    monkey_env = env or {}
    old = {k: os.environ.get(k) for k in monkey_env}
    try:
        for key, value in monkey_env.items():
            os.environ[key] = value
        code = main(
            argv,
            graphql_fn=graphql,
            token_fn=lambda: token,
            sleep_fn=lambda _s: None,
            now_fn=lambda: NOW,
            stdout=stdout,
            stderr=stderr,
        )
    finally:
        for key, prev in old.items():
            if prev is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prev
    return code, stdout.getvalue(), stderr.getvalue()


def test_script_exists_stdlib_and_never_deletes() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env python3")
    assert "import requests" not in text
    assert "issueArchive" in text
    assert "issueUpdate" in text
    assert "issueDelete" not in text
    assert "permanentlyDelete" not in text
    assert "linear_purge_closed" not in text
    assert BLACK_SWAN not in text or "never" in text.lower()
    assert PRIVATE_GAME not in text
    assert "mcp.linear.app" not in text
    assert FREE_TIER_CAP == 200
    assert STALE_DAYS_DEFAULT >= 1
    assert LINEAR_GRAPHQL == "https://api.linear.app/graphql"
    assert "issueArchive" in MUTATION_ISSUE_ARCHIVE
    assert "issueUpdate" in MUTATION_ISSUE_UPDATE
    assert "issueDelete" not in MUTATION_ISSUE_ARCHIVE
    assert "issueDelete" not in MUTATION_ISSUE_UPDATE


def test_purge_script_must_not_land() -> None:
    assert not (ROOT / "scripts" / "linear_purge_closed.py").exists()
    assert not (ROOT / "tests" / "test_linear_purge_closed.py").exists()


def test_done_canceled_duplicate_living_sky_are_archive() -> None:
    kwargs = {"now": NOW, "stale_days": STALE_DAYS_DEFAULT}
    assert classify_issue(_issue(state_name="Done", state_type="completed"), **kwargs).action == "archive"
    assert classify_issue(
        _issue(state_name="Canceled", state_type="canceled", identifier="LIV-2"), **kwargs
    ).action == "archive"
    assert classify_issue(
        _issue(state_name="Cancelled", state_type="canceled", identifier="LIV-3"), **kwargs
    ).action == "archive"
    assert classify_issue(
        _issue(state_name="Duplicate", state_type="canceled", identifier="LIV-4"), **kwargs
    ).action == "archive"
    for name in ARCHIVE_STATE_NAMES:
        assert name.lower() in {"done", "canceled", "cancelled", "duplicate"}


def test_already_archived_is_skip() -> None:
    decision = classify_issue(
        _issue(archived=True, state_name="Done", state_type="completed"),
        now=NOW,
        stale_days=STALE_DAYS_DEFAULT,
    )
    assert decision.action == "skip"
    assert "archiv" in decision.reason.lower()


def test_stale_open_living_sky_is_close() -> None:
    decision = classify_issue(
        _issue(
            identifier="LIV-9",
            state_name="Backlog",
            state_type="backlog",
            updated_days_ago=45,
        ),
        now=NOW,
        stale_days=30,
    )
    assert decision.action == "close"
    assert "stale" in decision.reason.lower()


def test_recent_open_and_started_are_skip() -> None:
    kwargs = {"now": NOW, "stale_days": 30}
    recent = classify_issue(
        _issue(state_name="Todo", state_type="unstarted", updated_days_ago=2),
        **kwargs,
    )
    started = classify_issue(
        _issue(
            identifier="LIV-10",
            state_name="In Progress",
            state_type="started",
            updated_days_ago=90,
        ),
        **kwargs,
    )
    assert recent.action == "skip"
    assert started.action == "skip"


def test_black_swan_and_other_teams_are_skip() -> None:
    kwargs = {"now": NOW, "stale_days": 30}
    swan = classify_issue(
        _issue(
            identifier="BSM-1",
            team_key="BSM",
            team_name=BLACK_SWAN,
            state_name="Done",
            state_type="completed",
        ),
        **kwargs,
    )
    other = classify_issue(
        _issue(identifier="OTH-1", team_key="OTH", team_name="Other Team"),
        **kwargs,
    )
    assert swan.action == "skip"
    assert other.action == "skip"
    assert "living" in swan.reason.lower() or "black swan" in swan.reason.lower()


def test_dry_run_lists_close_and_archive_without_mutations() -> None:
    graphql = FakeGraphQL(
        [
            [
                _issue(issue_id="done-1", identifier="LIV-1", state_name="Done", state_type="completed"),
                _issue(
                    issue_id="stale-1",
                    identifier="LIV-9",
                    state_name="Backlog",
                    state_type="backlog",
                    updated_days_ago=45,
                ),
                _issue(
                    issue_id="live-1",
                    identifier="LIV-10",
                    state_name="In Progress",
                    state_type="started",
                    updated_days_ago=90,
                ),
            ]
        ]
    )
    code, out, err = _run_main([], graphql)
    combined = out + err
    assert code == 0
    assert "LINEAR_ARCHIVE" in combined
    assert "LIV-1" in combined
    assert "LIV-9" in combined
    assert graphql.archive_ids == []
    assert graphql.update_ids == []
    assert graphql.delete_ids == []
    assert "would-archive" in combined
    assert "would-close" in combined


def test_apply_closes_stale_then_archives_done_never_deletes() -> None:
    graphql = FakeGraphQL(
        [
            [
                _issue(issue_id="done-1", identifier="LIV-1", state_name="Done", state_type="completed"),
                _issue(
                    issue_id="stale-1",
                    identifier="LIV-9",
                    state_name="Todo",
                    state_type="unstarted",
                    updated_days_ago=60,
                ),
                _issue(
                    issue_id="swan-1",
                    identifier="BSM-1",
                    team_key="BSM",
                    team_name=BLACK_SWAN,
                    state_name="Done",
                    state_type="completed",
                ),
            ]
        ]
    )
    code, out, err = _run_main(["--apply"], graphql)
    combined = out + err
    assert code == 0
    assert graphql.delete_ids == []
    assert "done-1" in graphql.archive_ids
    assert "stale-1" in graphql.update_ids
    assert graphql.update_state_ids == ["state-canceled"]
    assert "stale-1" in graphql.archive_ids
    assert "swan-1" not in graphql.archive_ids
    assert "swan-1" not in graphql.update_ids
    assert "LINEAR_ARCHIVE_OK" in combined
    assert "issueDelete" not in combined


def test_apply_limit_and_missing_key_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    graphql = FakeGraphQL(
        [
            [
                _issue(issue_id="a", identifier="LIV-1"),
                _issue(issue_id="b", identifier="LIV-2"),
            ]
        ]
    )
    code, out, err = _run_main(["--apply", "--limit", "1"], graphql)
    assert code == 0
    assert len(graphql.archive_ids) == 1

    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    monkeypatch.delenv("GCS_LINEAR_API_KEY", raising=False)
    monkeypatch.delenv("LINEAR_API_KEY_FILE", raising=False)
    monkeypatch.delenv("GCS_LINEAR_API_KEY_FILE", raising=False)
    monkeypatch.delenv("GCS_A2A_STATE", raising=False)
    with pytest.raises(RuntimeError):
        load_api_key()


def test_apply_and_dry_run_are_exclusive() -> None:
    graphql = FakeGraphQL([[]])
    code, out, err = _run_main(["--apply", "--dry-run"], graphql)
    assert code != 0
    assert graphql.archive_ids == []
    assert "mutually exclusive" in (out + err).lower() or "exclusive" in (out + err).lower()


def test_help_names_archive_not_delete() -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=15,
    )
    blob = proc.stdout + proc.stderr
    assert proc.returncode == 0, blob
    low = blob.lower()
    assert "archive" in low
    assert "stale" in low
    assert "delete" in low
    assert "black swan" in low
    assert "living sky" in low or "liv" in low
    assert "mcp" in low


def test_redact_strips_token() -> None:
    token = "lin_api_test_token_not_a_real_secret"
    assert token not in redact(f"boom {token} extra", token)


def test_load_api_key_from_env_and_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    monkeypatch.delenv("GCS_LINEAR_API_KEY", raising=False)
    monkeypatch.delenv("LINEAR_API_KEY_FILE", raising=False)
    monkeypatch.setenv("GCS_LINEAR_API_KEY", "from-gcs-env")
    assert load_api_key() == "from-gcs-env"
    monkeypatch.delenv("GCS_LINEAR_API_KEY")
    key_file = tmp_path / "linear.api_key"
    key_file.write_text("from-file\n", encoding="utf-8")
    monkeypatch.setenv("LINEAR_API_KEY_FILE", str(key_file))
    assert load_api_key() == "from-file"
    monkeypatch.delenv("LINEAR_API_KEY_FILE")
    monkeypatch.setenv("GCS_A2A_STATE", str(tmp_path))
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    (secrets / "linear.api_key").write_text("LINEAR_API_KEY=from-state\n", encoding="utf-8")
    assert load_api_key() == "from-state"


def test_docs_and_wiring_are_archive_not_purge() -> None:
    doc = ROOT / "docs" / "studio" / "LINEAR.md"
    text = doc.read_text(encoding="utf-8")
    low = text.lower()
    assert "liv-76" in low
    assert "200" in text
    assert "issuearchive" in low.replace("_", "")
    assert "linear_archive_closed.py" in text
    assert "do not delete" in low or "never delete" in low
    assert "purge" in low or "#45" in text or "wrong mechanic" in low
    assert "black swan" in low
    assert "living sky" in low
    assert "mcp" in low
    assert "no archive mutation" in low or "has no archive" in low
    assert "close" in low and "stale" in low
    doctor = (ROOT / "doctor.sh").read_text(encoding="utf-8")
    install = (ROOT / "install.sh").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    arch = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    wipe = (ROOT / "docs" / "studio" / "WIPE.md").read_text(encoding="utf-8")
    env_ex = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "linear_archive_closed.py" in doctor
    assert "docs/studio/LINEAR.md" in doctor
    assert "linear_archive_closed.py" in install
    assert "linear_archive_closed.py" in readme
    assert "LINEAR.md" in arch
    assert "LINEAR.md" in wipe
    assert "linear_purge_closed.py" not in doctor
    assert "linear_purge_closed.py" not in install
    assert "GCS_LINEAR_API_KEY" in env_ex
    assert BLACK_SWAN in env_ex
    for line in env_ex.splitlines():
        stripped = line.strip()
        if stripped.startswith("LINEAR_API_KEY=") or stripped.startswith("GCS_LINEAR_API_KEY="):
            raise AssertionError("env example must not assign Linear keys")
