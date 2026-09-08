"""LIV-82: director GraphQL commentCreate on Living Sky issues.

Posts via api.linear.app/graphql. Uses scripts/directors/linear_key.py.
Never prints the key. Refuses non-Living-Sky teams. Dry-run default.
Never issueDelete. Never Black Swan Money. Linear MCP leftover is not
this slice.
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import urllib.error
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "linear_comment.py"
sys.path.insert(0, str(ROOT / "scripts"))

from linear_comment import (  # noqa: E402
    LINEAR_GRAPHQL,
    MUTATION_COMMENT_CREATE,
    QUERY_ISSUE,
    is_living_sky_identifier,
    is_living_sky_team,
    load_api_key,
    main,
    parse_issue_ref,
    redact,
)

TOKEN = "lin_api_test_token_not_a_real_secret"
BLACK_SWAN = "Black Swan Money"
PRIVATE_GAME = "atebites-hub/" + "palemon"
BODY = "jay1502 LIV-82 GraphQL comment stamp"


def _liv_issue(
    *,
    issue_id: str = "issue-uuid-82",
    identifier: str = "LIV-82",
    team_key: str = "LIV",
    team_name: str = "Living Sky",
) -> dict[str, Any]:
    return {
        "id": issue_id,
        "identifier": identifier,
        "title": "Linear comment via GraphQL",
        "url": f"https://linear.app/livingsky/issue/{identifier}",
        "team": {"id": "team-liv", "key": team_key, "name": team_name},
    }


def _issue_payload(issue: dict[str, Any] | None) -> dict[str, Any]:
    return {"data": {"issue": issue}}


def _comment_payload(
    *,
    comment_id: str = "comment-uuid-1",
    url: str = "https://linear.app/livingsky/comment/comment-uuid-1",
) -> dict[str, Any]:
    return {
        "data": {
            "commentCreate": {
                "success": True,
                "comment": {"id": comment_id, "url": url, "body": BODY},
            }
        }
    }


class FakeHTTPResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._body = json.dumps(payload).encode("utf-8")
        self.status = 200

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> FakeHTTPResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


_ISSUE_UNSET = object()


class MockLinearHTTP:
    def __init__(
        self,
        *,
        issue: dict[str, Any] | None | object = _ISSUE_UNSET,
        comment: dict[str, Any] | None = None,
        http_error: BaseException | None = None,
    ) -> None:
        self.issue = _liv_issue() if issue is _ISSUE_UNSET else issue
        self.comment = comment if comment is not None else _comment_payload()
        self.http_error = http_error
        self.calls: list[dict[str, Any]] = []

    def __call__(self, req: Any, timeout: float | None = None) -> FakeHTTPResponse:
        raw = req.data or b"{}"
        if isinstance(raw, bytes):
            body = json.loads(raw.decode("utf-8"))
        else:
            body = json.loads(str(raw))
        query = str(body.get("query") or "")
        variables = body.get("variables") or {}
        auth = ""
        if hasattr(req, "get_header"):
            auth = str(req.get_header("Authorization") or "")
        headers = {}
        if hasattr(req, "header_items"):
            headers = {str(k): str(v) for k, v in req.header_items()}
        record = {
            "url": str(getattr(req, "full_url", "")),
            "query": query,
            "variables": variables,
            "authorization": auth,
            "headers": headers,
            "timeout": timeout,
        }
        self.calls.append(record)
        if "issueDelete" in query or "permanentlyDelete" in query:
            raise AssertionError("LIV-82 must not call issueDelete/permanentlyDelete")
        if self.http_error is not None:
            raise self.http_error
        if "commentCreate" in query:
            return FakeHTTPResponse(self.comment)
        if "issue(" in query or "issue (" in query:
            return FakeHTTPResponse(_issue_payload(self.issue))
        raise AssertionError(f"unexpected GraphQL query: {query}")


def _run_main(
    argv: list[str],
    http: MockLinearHTTP,
    *,
    env: dict[str, str] | None = None,
    token_fn: Any | None = None,
) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    extra = env or {}
    old = {k: os.environ.get(k) for k in extra}
    try:
        for key, value in extra.items():
            os.environ[key] = value
        with patch("linear_comment.urllib.request.urlopen", http):
            code = main(
                argv,
                token_fn=token_fn if token_fn is not None else (lambda: TOKEN),
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


def test_script_exists_stdlib_uses_linear_key_never_deletes() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env python3")
    assert "import requests" not in text
    assert "commentCreate" in text
    assert "linear_key" in text
    assert "issueDelete" not in text
    assert "permanentlyDelete" not in text
    assert "mcp.linear.app" not in text
    assert "issueArchive" not in text
    assert LINEAR_GRAPHQL == "https://api.linear.app/graphql"
    assert "commentCreate" in MUTATION_COMMENT_CREATE
    assert "issue(" in QUERY_ISSUE
    assert PRIVATE_GAME not in text
    low = text.lower()
    assert "black swan" in low
    assert "never" in low


def test_parse_and_living_sky_gates() -> None:
    assert parse_issue_ref("LIV-82") == "LIV-82"
    assert parse_issue_ref("liv-82") == "LIV-82"
    assert parse_issue_ref("https://linear.app/livingsky/issue/LIV-82/slug") == "LIV-82"
    assert parse_issue_ref("BSM-1") == "BSM-1"
    assert is_living_sky_identifier("LIV-82") is True
    assert is_living_sky_identifier("BSM-1") is False
    assert is_living_sky_team({"key": "LIV", "name": "Living Sky"}) is True
    assert is_living_sky_team({"key": "BSM", "name": BLACK_SWAN}) is False
    assert is_living_sky_team({"key": "LIV", "name": BLACK_SWAN}) is False
    assert is_living_sky_team({"key": "OTH", "name": "Other Team"}) is False


def test_dry_run_default_queries_issue_not_comment_create() -> None:
    http = MockLinearHTTP()
    code, out, err = _run_main(
        ["--issue", "LIV-82", "--body", BODY],
        http,
    )
    combined = out + err
    assert code == 0
    assert "LINEAR_COMMENT" in combined
    assert "LIV-82" in combined
    assert "would-comment" in combined
    assert "LINEAR_COMMENT_OK" in combined
    queries = [c["query"] for c in http.calls]
    assert queries
    assert all("commentCreate" not in q for c in http.calls for q in [c["query"]])
    assert any("issue(" in c["query"] or "issue (" in c["query"] for c in http.calls)
    assert all(c["url"].startswith("https://api.linear.app/graphql") for c in http.calls)
    assert TOKEN not in combined


def test_apply_posts_comment_create_on_living_sky_uuid() -> None:
    http = MockLinearHTTP()
    code, out, err = _run_main(
        ["--issue", "LIV-82", "--body", BODY, "--apply"],
        http,
    )
    combined = out + err
    assert code == 0
    assert "LINEAR_COMMENT_OK" in combined
    assert "comment-uuid-1" in combined
    mutations = [c for c in http.calls if "commentCreate" in c["query"]]
    assert len(mutations) == 1
    variables = mutations[0]["variables"]
    payload = variables.get("input") or variables
    assert payload.get("issueId") == "issue-uuid-82"
    assert payload.get("body") == BODY
    assert TOKEN not in combined
    auth = mutations[0]["authorization"] or mutations[0]["headers"].get("Authorization", "")
    assert TOKEN in auth or TOKEN in str(mutations[0]["headers"])
    assert all("issueDelete" not in c["query"] for c in http.calls)


def test_refuses_black_swan_and_other_teams_without_comment_create() -> None:
    swan = MockLinearHTTP(
        issue=_liv_issue(identifier="BSM-1", team_key="BSM", team_name=BLACK_SWAN),
    )
    code, out, err = _run_main(
        ["--issue", "BSM-1", "--body", BODY, "--apply"],
        swan,
    )
    combined = (out + err).lower()
    assert code != 0
    assert "living" in combined or "black swan" in combined or "refuse" in combined
    assert all("commentCreate" not in c["query"] for c in swan.calls)
    assert TOKEN not in out + err

    other = MockLinearHTTP(
        issue=_liv_issue(identifier="OTH-9", team_key="OTH", team_name="Other Team"),
    )
    code, out, err = _run_main(
        ["--issue", "OTH-9", "--body", BODY, "--apply"],
        other,
    )
    assert code != 0
    assert all("commentCreate" not in c["query"] for c in other.calls)

    liv_but_swan_name = MockLinearHTTP(
        issue=_liv_issue(team_name=BLACK_SWAN),
    )
    code, out, err = _run_main(
        ["--issue", "LIV-82", "--body", BODY, "--apply"],
        liv_but_swan_name,
    )
    assert code != 0
    assert all("commentCreate" not in c["query"] for c in liv_but_swan_name.calls)


def test_liv_identifier_with_foreign_team_is_refused_after_lookup() -> None:
    http = MockLinearHTTP(
        issue=_liv_issue(identifier="LIV-82", team_key="BSM", team_name=BLACK_SWAN),
    )
    code, out, err = _run_main(
        ["--issue", "LIV-82", "--body", BODY, "--apply"],
        http,
    )
    assert code != 0
    assert http.calls, "must look up the issue before refusing"
    assert all("commentCreate" not in c["query"] for c in http.calls)


def test_missing_key_fail_closed_loads_linear_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    monkeypatch.delenv("GCS_LINEAR_API_KEY", raising=False)
    monkeypatch.delenv("GCS_LINEAR_KEY_FILE", raising=False)
    monkeypatch.delenv("GCS_A2A_STATE", raising=False)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    with pytest.raises(RuntimeError):
        load_api_key()

    state = tmp_path / "a2a-state"
    state.mkdir()
    (state / "linear.env").write_text(f"LINEAR_API_KEY={TOKEN}\n", encoding="utf-8")
    monkeypatch.setenv("GCS_A2A_STATE", str(state))
    assert load_api_key() == TOKEN

    http = MockLinearHTTP()
    stdout = io.StringIO()
    stderr = io.StringIO()
    with patch("linear_comment.urllib.request.urlopen", http):
        code = main(
            ["--issue", "LIV-82", "--body", BODY],
            stdout=stdout,
            stderr=stderr,
        )
    combined = stdout.getvalue() + stderr.getvalue()
    assert code == 0
    assert TOKEN not in combined
    assert "would-comment" in combined


def test_apply_and_dry_run_are_exclusive() -> None:
    http = MockLinearHTTP()
    code, out, err = _run_main(
        ["--issue", "LIV-82", "--body", BODY, "--apply", "--dry-run"],
        http,
    )
    assert code != 0
    assert http.calls == []
    assert "exclusive" in (out + err).lower()


def test_empty_body_and_missing_issue_fail() -> None:
    http = MockLinearHTTP()
    code, out, err = _run_main(["--issue", "LIV-82", "--body", "  ", "--apply"], http)
    assert code != 0
    assert http.calls == []
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--body", BODY],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=15,
        env={**os.environ, "LINEAR_API_KEY": TOKEN, "HOME": "/tmp"},
    )
    assert proc.returncode != 0


def test_http_error_redacts_token() -> None:
    fp = io.BytesIO(f'{{"errors":[{{"message":"nope {TOKEN}"}}]}}'.encode("utf-8"))
    err = urllib.error.HTTPError(
        LINEAR_GRAPHQL,
        401,
        "Unauthorized",
        hdrs=None,  # type: ignore[arg-type]
        fp=fp,
    )
    http = MockLinearHTTP(http_error=err)
    code, out, stderr = _run_main(
        ["--issue", "LIV-82", "--body", BODY, "--apply"],
        http,
    )
    combined = out + stderr
    assert code != 0
    assert TOKEN not in combined
    assert "<redacted>" in combined or "LINEAR_COMMENT" in combined


def test_issue_not_found_fail_closed() -> None:
    http = MockLinearHTTP(issue=None)
    code, out, err = _run_main(
        ["--issue", "LIV-82", "--body", BODY, "--apply"],
        http,
    )
    assert code != 0
    assert all("commentCreate" not in c["query"] for c in http.calls)


def test_help_stamp_path_living_sky_not_mcp() -> None:
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
    assert "--issue" in blob
    assert "--body" in blob
    assert "LIV-82" in blob
    assert "linear_comment.py" in blob
    assert "commentcreate" in low.replace("_", "") or "comment" in low
    assert "dry-run" in low or "dry run" in low
    assert "living sky" in low or "liv" in low
    assert "black swan" in low
    assert "linear_key" in low or "linear.env" in low
    assert "mcp.linear.app" not in low


def test_redact_strips_token() -> None:
    assert TOKEN not in redact(f"boom {TOKEN} extra", TOKEN)


def test_docs_and_wiring_name_graphql_comment_not_mcp() -> None:
    doc = (ROOT / "docs" / "studio" / "LINEAR.md").read_text(encoding="utf-8")
    doctor = (ROOT / "doctor.sh").read_text(encoding="utf-8")
    install = (ROOT / "install.sh").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    arch = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    low = doc.lower()
    assert "linear_comment.py" in doc
    assert "commentcreate" in low.replace("_", "")
    assert "liv-82" in low
    assert "--issue" in doc and "--body" in doc
    assert "linear_key.py" in doc
    assert "linear.env" in low
    assert "black swan" in low
    assert "dry-run" in low or "dry run" in low
    assert "issueDelete" in doc
    assert "scripts/linear_comment.py" in doctor
    assert "scripts/linear_comment.py" in install
    assert "linear_comment.py" in readme
    assert "linear_comment.py" in arch or "commentCreate" in arch
    assert PRIVATE_GAME not in doc
