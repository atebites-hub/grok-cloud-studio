"""Linear free-tier purge: issueDelete Done/Canceled/Duplicate Living Sky only.

Archive is treated as still counting toward the workspace cap, so the script
must call issueDelete (permanentlyDelete) and never issueArchive.
Open Palemon/GCS work is never deleted.
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "linear_purge_closed.py"
sys.path.insert(0, str(ROOT / "scripts"))

from linear_purge_closed import (  # noqa: E402
    DELETE_STATE_NAMES,
    FREE_TIER_CAP,
    LINEAR_GRAPHQL,
    MUTATION_ISSUE_DELETE,
    QUERY_ISSUES,
    classify_issue,
    load_api_key,
    main,
    redact,
)

PRIVATE_GAME = "atebites-hub/" + "palemon"


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
) -> dict[str, Any]:
    return {
        "id": issue_id,
        "identifier": identifier,
        "title": title,
        "url": f"https://linear.app/livingsky/issue/{identifier}",
        "archivedAt": "2026-01-01T00:00:00.000Z" if archived else None,
        "state": {"name": state_name, "type": state_type},
        "team": {"id": "team-liv", "key": team_key, "name": team_name},
    }


class FakeGraphQL:
    def __init__(self, pages: list[list[dict[str, Any]]], *, delete_ok: bool = True) -> None:
        self.pages = pages
        self.delete_ok = delete_ok
        self.queries: list[str] = []
        self.variables: list[dict[str, Any]] = []
        self.delete_ids: list[str] = []

    def __call__(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        variables = variables or {}
        self.queries.append(query)
        self.variables.append(variables)
        if "issueDelete" in query:
            issue_id = str(variables.get("id") or "")
            self.delete_ids.append(issue_id)
            if "issueArchive" in query:
                raise AssertionError("must not call issueArchive")
            return {
                "data": {
                    "issueDelete": {
                        "success": self.delete_ok,
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


def test_script_exists_and_is_stdlib() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env python3")
    assert "import requests" not in text
    assert "issueDelete" in text
    assert "permanentlyDelete" in text
    assert "issueArchive" not in text.split("issueDelete")[0] or "never issueArchive" in text.lower()
    assert "issueArchive(" not in text
    assert PRIVATE_GAME not in text


def test_done_canceled_duplicate_living_sky_are_delete() -> None:
    assert classify_issue(_issue(state_name="Done", state_type="completed")).action == "delete"
    assert classify_issue(_issue(state_name="Canceled", state_type="canceled")).action == "delete"
    assert classify_issue(
        _issue(state_name="Cancelled", state_type="canceled", identifier="LIV-2")
    ).action == "delete"
    assert classify_issue(
        _issue(state_name="Duplicate", state_type="canceled", identifier="LIV-3")
    ).action == "delete"
    assert "done" in DELETE_STATE_NAMES
    assert "duplicate" in DELETE_STATE_NAMES


def test_archived_done_still_counts_and_is_delete() -> None:
    decision = classify_issue(
        _issue(identifier="LIV-9", title="old archived", archived=True)
    )
    assert decision.action == "delete"
    assert decision.archived is True


def test_open_palemon_gcs_work_is_skipped() -> None:
    palemon = classify_issue(
        _issue(
            identifier="LIV-76",
            title="Palemon studio wipe remaining",
            state_name="In Progress",
            state_type="started",
        )
    )
    gcs = classify_issue(
        _issue(
            identifier="LIV-10",
            title="GCS A2A hub follow-up",
            state_name="Todo",
            state_type="unstarted",
        )
    )
    backlog = classify_issue(
        _issue(
            identifier="LIV-11",
            title="GCS mind seat",
            state_name="Backlog",
            state_type="backlog",
        )
    )
    assert palemon.action == "skip"
    assert palemon.reason == "open"
    assert gcs.action == "skip"
    assert gcs.reason == "open"
    assert backlog.action == "skip"
    assert backlog.reason == "open"


def test_other_team_never_deleted_even_if_done() -> None:
    decision = classify_issue(
        _issue(
            identifier="GCS-1",
            title="control plane ticket",
            state_name="Done",
            state_type="completed",
            team_key="GCS",
            team_name="Grok Cloud Studio",
        )
    )
    assert decision.action == "skip"
    assert decision.reason == "other_team"


def test_livingsky_team_name_alias() -> None:
    decision = classify_issue(
        _issue(team_key="LIV", team_name="Livingsky", state_name="Done")
    )
    assert decision.action == "delete"


def test_missing_state_is_skip_fail_closed() -> None:
    raw = _issue()
    raw["state"] = None
    decision = classify_issue(raw)
    assert decision.action == "skip"
    assert decision.reason == "open"


def test_redact_never_echoes_token() -> None:
    token = "lin_api_test_token_not_a_real_secret"
    assert token not in redact(f"Authorization {token} rejected", token)
    assert "***" in redact(token, token)


def test_load_api_key_from_env_and_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    state = tmp_path / "state"
    secrets = state / "secrets"
    secrets.mkdir(parents=True)
    (secrets / "linear.api_key").write_text("LINEAR_API_KEY=from-state\n", encoding="utf-8")
    monkeypatch.setenv("GCS_A2A_STATE", str(state))
    assert load_api_key() == "from-state"


def test_dry_run_lists_candidates_and_does_not_delete() -> None:
    pages = [
        [
            _issue(identifier="LIV-1", issue_id="id-1"),
            _issue(
                identifier="LIV-76",
                title="open Palemon GCS work",
                state_name="In Progress",
                state_type="started",
                issue_id="id-open",
            ),
            _issue(
                identifier="LIV-2",
                title="dup",
                state_name="Duplicate",
                state_type="canceled",
                issue_id="id-2",
                archived=True,
            ),
        ]
    ]
    graphql = FakeGraphQL(pages)
    code, out, err = _run_main(["--sleep", "0"], graphql)
    assert code == 0, err
    assert "LINEAR_PURGE" in out
    assert "dry-run" in out
    assert "LIV-1" in out
    assert "LIV-2" in out
    assert "LIV-76" in out
    assert "skipped_open=" in out
    assert graphql.delete_ids == []
    assert any("includeArchived" in q or "includeArchived" in json.dumps(v) for q, v in zip(graphql.queries, graphql.variables))
    assert FREE_TIER_CAP == 200
    assert str(FREE_TIER_CAP) in out
    token = "lin_api_test_token_not_a_real_secret"
    assert token not in out
    assert token not in err


def test_apply_deletes_only_closed_living_sky_via_issue_delete() -> None:
    pages = [
        [
            _issue(identifier="LIV-1", issue_id="id-1"),
            _issue(
                identifier="LIV-76",
                title="open Palemon GCS work",
                state_name="In Progress",
                state_type="started",
                issue_id="id-open",
            ),
            _issue(
                identifier="GCS-9",
                title="other team done",
                state_name="Done",
                state_type="completed",
                team_key="GCS",
                team_name="Grok Cloud Studio",
                issue_id="id-gcs",
            ),
            _issue(
                identifier="LIV-8",
                title="canceled",
                state_name="Canceled",
                state_type="canceled",
                issue_id="id-8",
            ),
        ]
    ]
    graphql = FakeGraphQL(pages)
    code, out, err = _run_main(["--apply", "--sleep", "0"], graphql)
    assert code == 0, err
    assert "apply" in out
    assert graphql.delete_ids == ["id-1", "id-8"]
    assert "id-open" not in graphql.delete_ids
    assert "id-gcs" not in graphql.delete_ids
    assert all("permanentlyDelete" in q or v.get("permanentlyDelete") is True for q, v in zip(graphql.queries, graphql.variables) if "issueDelete" in q)
    for query in graphql.queries:
        assert "issueArchive" not in query
    assert MUTATION_ISSUE_DELETE.strip().startswith("mutation")
    assert "issueDelete" in MUTATION_ISSUE_DELETE
    assert "permanentlyDelete" in MUTATION_ISSUE_DELETE
    assert LINEAR_GRAPHQL == "https://api.linear.app/graphql"
    assert "LINEAR_PURGE_OK" in out
    assert "deleted=2" in out
    token = "lin_api_test_token_not_a_real_secret"
    assert token not in out + err


def test_apply_limit_caps_deletes() -> None:
    pages = [
        [
            _issue(identifier="LIV-1", issue_id="id-1"),
            _issue(identifier="LIV-2", issue_id="id-2", title="second"),
        ]
    ]
    graphql = FakeGraphQL(pages)
    code, out, _err = _run_main(["--apply", "--limit", "1", "--sleep", "0"], graphql)
    assert code == 0
    assert graphql.delete_ids == ["id-1"]
    assert "deleted=1" in out


def test_missing_api_key_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    monkeypatch.delenv("GCS_LINEAR_API_KEY", raising=False)
    monkeypatch.delenv("LINEAR_API_KEY_FILE", raising=False)
    monkeypatch.delenv("GCS_A2A_STATE", raising=False)
    monkeypatch.setenv("HOME", "/tmp/gcs-no-linear-home")
    proc = subprocess.run(
        ["python3", str(SCRIPT), "--sleep", "0"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=10,
        env={
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": "/tmp/gcs-no-linear-home",
            "GCS_ROOT": str(ROOT),
        },
    )
    assert proc.returncode != 0
    combined = proc.stdout + proc.stderr
    assert "LINEAR_PURGE" in combined
    assert "api_key" in combined.lower() or "LINEAR_API_KEY" in combined


def test_help_documents_dry_run_and_apply() -> None:
    proc = subprocess.run(
        ["python3", str(SCRIPT), "--help"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0
    text = proc.stdout + proc.stderr
    assert "--apply" in text
    assert "dry-run" in text.lower() or "dry run" in text.lower()
    assert "issueDelete" in text
    assert "Living Sky" in text or "LIV" in text
    assert "200" in text


def test_query_includes_archived_and_does_not_archive() -> None:
    assert "includeArchived" in QUERY_ISSUES
    assert "issueArchive" not in QUERY_ISSUES
    assert "issueDelete" not in QUERY_ISSUES


def test_docs_and_doctor_point_at_script() -> None:
    doc = ROOT / "docs" / "studio" / "LINEAR.md"
    assert doc.is_file()
    text = doc.read_text(encoding="utf-8")
    assert "issueDelete" in text
    assert "permanentlyDelete" in text
    assert "--apply" in text
    assert "linear_purge_closed.py" in (ROOT / "doctor.sh").read_text(encoding="utf-8")
    assert "linear_purge_closed.py" in (ROOT / "install.sh").read_text(encoding="utf-8")
    assert "linear_purge_closed.py" in (ROOT / "README.md").read_text(encoding="utf-8")
    assert PRIVATE_GAME not in text
