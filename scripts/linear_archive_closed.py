#!/usr/bin/env python3
"""LIV-76: close stale Living Sky tickets; archive Done/Canceled; never delete.

Linear free-tier cap is 200 issues. GCS #45 purge-delete is the wrong
mechanic. Close stale open LIV tickets, then call GraphQL issueArchive.
Linear MCP has no archive mutation. Never operate on Black Swan Money.
Never print the API key.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TextIO

LINEAR_GRAPHQL = "https://api.linear.app/graphql"
FREE_TIER_CAP = 200
STALE_DAYS_DEFAULT = 30
LIVING_SKY_TEAM_KEY = "LIV"
ARCHIVE_STATE_NAMES = frozenset({"Done", "Canceled", "Cancelled", "Duplicate"})
OPEN_STATE_TYPES = frozenset({"triage", "backlog", "unstarted"})
LIVE_STATE_TYPES = frozenset({"started"})
CLOSED_STATE_TYPES = frozenset({"completed", "canceled"})

QUERY_ISSUES = """
query Issues($after: String) {
  issues(
    first: 50
    after: $after
    includeArchived: false
    filter: { team: { key: { eq: "LIV" } } }
  ) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id
      identifier
      title
      url
      updatedAt
      archivedAt
      state { name type }
      team { id key name }
    }
  }
}
"""

QUERY_TEAM_STATES = """
query TeamStates($key: String!) {
  teams(filter: { key: { eq: $key } }) {
    nodes {
      id
      key
      name
      states {
        nodes { id name type }
      }
    }
  }
}
"""

MUTATION_ISSUE_ARCHIVE = """
mutation IssueArchive($id: String!) {
  issueArchive(id: $id) {
    success
  }
}
"""

MUTATION_ISSUE_UPDATE = """
mutation IssueUpdate($id: String!, $input: IssueUpdateInput!) {
  issueUpdate(id: $id, input: $input) {
    success
    issue { id identifier }
  }
}
"""

GraphQLFn = Callable[[str, dict[str, Any] | None], dict[str, Any]]
TokenFn = Callable[[], str]
SleepFn = Callable[[float], None]
NowFn = Callable[[], datetime]


@dataclass(frozen=True)
class Decision:
    action: str
    reason: str
    identifier: str = ""
    issue_id: str = ""
    state_name: str = ""
    state_type: str = ""


def redact(text: str, token: str | None) -> str:
    out = str(text)
    if token:
        out = out.replace(token, "<redacted>")
        if token.lower().startswith("bearer "):
            out = out.replace(token.split(None, 1)[-1], "<redacted>")
    return out


def _read_key_blob(raw: str) -> str:
    text = raw.strip()
    for prefix in ("LINEAR_API_KEY=", "GCS_LINEAR_API_KEY="):
        if text.startswith(prefix):
            text = text.split("=", 1)[1].strip().strip('"').strip("'")
            break
    return text.strip()


def load_api_key(*, environ: dict[str, str] | None = None) -> str:
    env = environ if environ is not None else os.environ
    for name in ("GCS_LINEAR_API_KEY", "LINEAR_API_KEY"):
        value = _read_key_blob(str(env.get(name) or ""))
        if value:
            return value
    for name in ("LINEAR_API_KEY_FILE", "GCS_LINEAR_API_KEY_FILE"):
        path = str(env.get(name) or "").strip()
        if not path:
            continue
        blob = Path(path).read_text(encoding="utf-8")
        value = _read_key_blob(blob)
        if value:
            return value
    state = str(env.get("GCS_A2A_STATE") or "").strip()
    if state:
        path = Path(state) / "secrets" / "linear.api_key"
        if path.is_file():
            value = _read_key_blob(path.read_text(encoding="utf-8"))
            if value:
                return value
    raise RuntimeError(
        "LINEAR_ARCHIVE fail missing LINEAR_API_KEY "
        "(set GCS_LINEAR_API_KEY, LINEAR_API_KEY, or LINEAR_API_KEY_FILE)"
    )


def _nested(data: dict[str, Any], *keys: str) -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def graphql_request(
    query: str,
    variables: dict[str, Any] | None = None,
    *,
    token: str,
    endpoint: str = LINEAR_GRAPHQL,
) -> dict[str, Any]:
    payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    auth = token if token.lower().startswith("bearer ") else token
    req = urllib.request.Request(
        endpoint,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": auth,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            redact(f"LINEAR_ARCHIVE graphql HTTP {exc.code} {err_body}", token)
        ) from None
    except urllib.error.URLError as exc:
        raise RuntimeError(
            redact(f"LINEAR_ARCHIVE graphql URL error {exc}", token)
        ) from None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(redact(f"LINEAR_ARCHIVE graphql JSON {exc}", token)) from None
    if not isinstance(parsed, dict):
        raise RuntimeError("LINEAR_ARCHIVE graphql unexpected payload")
    errors = parsed.get("errors")
    if errors:
        raise RuntimeError(redact(f"LINEAR_ARCHIVE graphql errors {errors}", token))
    return parsed


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def classify_issue(
    issue: dict[str, Any],
    *,
    now: datetime,
    stale_days: int = STALE_DAYS_DEFAULT,
) -> Decision:
    identifier = str(issue.get("identifier") or "")
    issue_id = str(issue.get("id") or "")
    team = issue.get("team") if isinstance(issue.get("team"), dict) else {}
    team_key = str(team.get("key") or "")
    team_name = str(team.get("name") or "")
    state = issue.get("state") if isinstance(issue.get("state"), dict) else {}
    state_name = str(state.get("name") or "")
    state_type = str(state.get("type") or "").lower()
    base = Decision(
        action="skip",
        reason="unclassified",
        identifier=identifier,
        issue_id=issue_id,
        state_name=state_name,
        state_type=state_type,
    )
    if "black swan" in team_name.lower() or team_key.upper() != LIVING_SKY_TEAM_KEY:
        return Decision(
            action="skip",
            reason="not-living-sky",
            identifier=identifier,
            issue_id=issue_id,
            state_name=state_name,
            state_type=state_type,
        )
    if not identifier.upper().startswith("LIV-"):
        return Decision(
            action="skip",
            reason="not-living-sky-id",
            identifier=identifier,
            issue_id=issue_id,
            state_name=state_name,
            state_type=state_type,
        )
    if issue.get("archivedAt"):
        return Decision(
            action="skip",
            reason="already-archived",
            identifier=identifier,
            issue_id=issue_id,
            state_name=state_name,
            state_type=state_type,
        )
    if state_type in CLOSED_STATE_TYPES or state_name in ARCHIVE_STATE_NAMES:
        return Decision(
            action="archive",
            reason="done-canceled",
            identifier=identifier,
            issue_id=issue_id,
            state_name=state_name,
            state_type=state_type,
        )
    if state_type in LIVE_STATE_TYPES:
        return Decision(
            action="skip",
            reason="live-work",
            identifier=identifier,
            issue_id=issue_id,
            state_name=state_name,
            state_type=state_type,
        )
    if state_type in OPEN_STATE_TYPES:
        updated = _parse_dt(issue.get("updatedAt"))
        if updated is None:
            return Decision(
                action="skip",
                reason="missing-updatedAt",
                identifier=identifier,
                issue_id=issue_id,
                state_name=state_name,
                state_type=state_type,
            )
        age = now - updated
        if age.days >= stale_days:
            return Decision(
                action="close",
                reason=f"stale-{age.days}d",
                identifier=identifier,
                issue_id=issue_id,
                state_name=state_name,
                state_type=state_type,
            )
        return Decision(
            action="skip",
            reason="not-stale",
            identifier=identifier,
            issue_id=issue_id,
            state_name=state_name,
            state_type=state_type,
        )
    return base


def list_issues(graphql_fn: GraphQLFn) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    after: str | None = None
    while True:
        payload = graphql_fn(QUERY_ISSUES, {"after": after})
        conn = _nested(payload, "data", "issues")
        if not isinstance(conn, dict):
            raise RuntimeError("LINEAR_ARCHIVE graphql missing issues connection")
        page_nodes = conn.get("nodes")
        if not isinstance(page_nodes, list):
            raise RuntimeError("LINEAR_ARCHIVE graphql issues.nodes is not a list")
        for item in page_nodes:
            if isinstance(item, dict):
                nodes.append(item)
        page = conn.get("pageInfo") if isinstance(conn.get("pageInfo"), dict) else {}
        if not page.get("hasNextPage"):
            break
        after = page.get("endCursor")
        if not after:
            break
    return nodes


def canceled_state_id(graphql_fn: GraphQLFn, *, team_key: str = LIVING_SKY_TEAM_KEY) -> str:
    payload = graphql_fn(QUERY_TEAM_STATES, {"key": team_key})
    teams = _nested(payload, "data", "teams", "nodes")
    if not isinstance(teams, list):
        raise RuntimeError("LINEAR_ARCHIVE fail missing canceled workflow state")
    named = ""
    typed = ""
    for team in teams:
        if not isinstance(team, dict):
            continue
        states = _nested(team, "states", "nodes")
        if not isinstance(states, list):
            continue
        for state in states:
            if not isinstance(state, dict):
                continue
            sid = str(state.get("id") or "")
            name = str(state.get("name") or "")
            stype = str(state.get("type") or "").lower()
            if stype == "canceled" and sid:
                if name.lower() in {"canceled", "cancelled"}:
                    named = sid
                typed = typed or sid
    chosen = named or typed
    if not chosen:
        raise RuntimeError("LINEAR_ARCHIVE fail missing canceled workflow state")
    return chosen


def _emit(stream: TextIO, token: str | None, message: str) -> None:
    stream.write(redact(message, token) + "\n")
    stream.flush()


def _success(payload: dict[str, Any], *path: str) -> bool:
    node = _nested(payload, "data", *path)
    if isinstance(node, dict):
        return bool(node.get("success"))
    return False


def main(
    argv: list[str] | None = None,
    *,
    graphql_fn: GraphQLFn | None = None,
    token_fn: TokenFn | None = None,
    sleep_fn: SleepFn | None = None,
    now_fn: NowFn | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        prog="linear_archive_closed.py",
        description=(
            "LIV-76 Living Sky 200-issue cap: close stale tickets and archive "
            "Done/Canceled. Do not delete. Linear MCP has no archive mutation "
            "(this script uses GraphQL issueArchive). Never Black Swan Money."
        ),
    )
    parser.add_argument("--apply", action="store_true", help="close stale then archive")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="list candidates only (default when --apply is omitted)",
    )
    parser.add_argument("--limit", type=int, default=0, help="max tickets to mutate (0=all)")
    parser.add_argument(
        "--stale-days",
        type=int,
        default=STALE_DAYS_DEFAULT,
        help=f"close open LIV tickets idle this many days (default {STALE_DAYS_DEFAULT})",
    )
    parser.add_argument("--endpoint", default=LINEAR_GRAPHQL)
    args = parser.parse_args(argv)
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    if args.apply and args.dry_run:
        _emit(err, None, "LINEAR_ARCHIVE fail --apply and --dry-run are mutually exclusive")
        return 2
    apply = bool(args.apply)
    stale_days = int(args.stale_days)
    if stale_days < 1:
        _emit(err, None, "LINEAR_ARCHIVE fail --stale-days must be >= 1")
        return 2
    token = ""
    getter = token_fn if token_fn is not None else load_api_key
    try:
        token = getter()
    except Exception as exc:
        _emit(err, None, str(exc))
        return 2
    sleep = sleep_fn if sleep_fn is not None else time.sleep
    now = (now_fn if now_fn is not None else (lambda: datetime.now(timezone.utc)))()
    if graphql_fn is None:
        endpoint = str(args.endpoint or LINEAR_GRAPHQL)
        graphql_fn = lambda q, v=None: graphql_request(  # noqa: E731
            q, v, token=token, endpoint=endpoint
        )
    try:
        issues = list_issues(graphql_fn)
    except Exception as exc:
        _emit(err, token, f"LINEAR_ARCHIVE fail {exc}")
        return 2
    decisions = [
        classify_issue(item, now=now, stale_days=stale_days) for item in issues
    ]
    actionable = [d for d in decisions if d.action in {"close", "archive"}]
    skipped = [d for d in decisions if d.action == "skip"]
    limit = int(args.limit or 0)
    canceled_id = ""
    closed = 0
    archived = 0
    failed = 0
    mutated = 0
    mode = "apply" if apply else "dry-run"
    _emit(
        err,
        token,
        f"LINEAR_ARCHIVE {mode} cap={FREE_TIER_CAP} stale-days={stale_days} "
        f"candidates={len(actionable)} skipped={len(skipped)}",
    )
    for item in skipped:
        _emit(
            err,
            token,
            f"LINEAR_ARCHIVE skip {item.identifier} {item.reason} {item.state_name}",
        )
    for item in actionable:
        if limit > 0 and mutated >= limit:
            _emit(err, token, f"LINEAR_ARCHIVE skip {item.identifier} limit")
            continue
        if not apply:
            verb = "would-close" if item.action == "close" else "would-archive"
            _emit(
                out,
                token,
                f"LINEAR_ARCHIVE {verb} {item.identifier} {item.state_name} {item.reason}",
            )
            mutated += 1
            continue
        if not item.issue_id:
            _emit(err, token, f"LINEAR_ARCHIVE fail {item.identifier} missing id")
            failed += 1
            mutated += 1
            continue
        try:
            if item.action == "close":
                if not canceled_id:
                    canceled_id = canceled_state_id(graphql_fn)
                update_payload = graphql_fn(
                    MUTATION_ISSUE_UPDATE,
                    {"id": item.issue_id, "input": {"stateId": canceled_id}},
                )
                if not _success(update_payload, "issueUpdate"):
                    raise RuntimeError("issueUpdate success=false")
                closed += 1
                _emit(
                    err,
                    token,
                    f"LINEAR_ARCHIVE closed {item.identifier} {item.state_name}",
                )
                sleep(0.2)
            archive_payload = graphql_fn(
                MUTATION_ISSUE_ARCHIVE, {"id": item.issue_id}
            )
            if not _success(archive_payload, "issueArchive"):
                raise RuntimeError("issueArchive success=false")
            archived += 1
            _emit(
                err,
                token,
                f"LINEAR_ARCHIVE archived {item.identifier} {item.state_name}",
            )
            mutated += 1
            sleep(0.2)
        except Exception as exc:
            failed += 1
            mutated += 1
            _emit(err, token, f"LINEAR_ARCHIVE fail {item.identifier} {exc}")
    if apply:
        _emit(
            out,
            token,
            f"LINEAR_ARCHIVE apply closed={closed} archived={archived} failed={failed}",
        )
    status = "LINEAR_ARCHIVE_OK" if failed == 0 else "LINEAR_ARCHIVE_FAIL"
    _emit(
        out,
        token,
        f"{status} closed={closed} archived={archived} failed={failed} mode={mode}",
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
