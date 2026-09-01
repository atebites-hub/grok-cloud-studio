#!/usr/bin/env python3
"""Permanently delete closed Living Sky Linear issues (free-tier cap).

Linear archive still counts toward the Palemon Living Sky workspace cap
(LIV-76: 200). This script calls GraphQL ``issueDelete`` with
``permanentlyDelete=true``. Default is dry-run. Pass ``--apply`` to mutate.

Never issueArchive. Never deletes open Palemon/GCS work (triage / backlog /
unstarted / started). Never deletes non-Living-Sky teams. Never prints
``LINEAR_API_KEY``. Stdlib only.
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
from pathlib import Path
from typing import Any, Callable, TextIO

LINEAR_GRAPHQL = "https://api.linear.app/graphql"
FREE_TIER_CAP = 200
DELETE_STATE_NAMES = frozenset({"done", "canceled", "cancelled", "duplicate"})
CLOSED_STATE_TYPES = frozenset({"completed", "canceled", "duplicate"})
OPEN_STATE_TYPES = frozenset({"triage", "backlog", "unstarted", "started"})
DEFAULT_TEAM_KEYS = frozenset({"liv"})
DEFAULT_TEAM_NAMES = frozenset({"living sky", "livingsky"})
PAGE_SIZE = 100

QUERY_ISSUES = """
query GcsLinearIssues($after: String, $includeArchived: Boolean!, $first: Int!) {
  issues(first: $first, after: $after, includeArchived: $includeArchived) {
    nodes {
      id
      identifier
      title
      url
      archivedAt
      state { name type }
      team { id key name }
    }
    pageInfo { hasNextPage endCursor }
  }
}
""".strip()

MUTATION_ISSUE_DELETE = """
mutation GcsIssueDelete($id: String!, $permanentlyDelete: Boolean) {
  issueDelete(id: $id, permanentlyDelete: $permanentlyDelete) {
    success
  }
}
""".strip()


@dataclass(frozen=True)
class Decision:
    action: str
    reason: str
    archived: bool
    identifier: str
    title: str
    state_name: str
    state_type: str
    issue_id: str
    team_key: str


def redact(text: str, token: str) -> str:
    if not text:
        return text
    out = text
    if token:
        out = out.replace(token, "***")
    for marker in ("lin_api_", "lin_oauth_"):
        if marker in out.lower():
            rebuilt: list[str] = []
            i = 0
            lower = out.lower()
            while i < len(out):
                hit = lower.find(marker, i)
                if hit < 0:
                    rebuilt.append(out[i:])
                    break
                rebuilt.append(out[i:hit])
                rebuilt.append("***")
                j = hit
                while j < len(out) and (out[j].isalnum() or out[j] in "_-"):
                    j += 1
                i = j
            out = "".join(rebuilt)
    return out


def _unquote(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1].strip()
    return text


def _parse_key_blob(text: str) -> str:
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        for prefix in ("LINEAR_API_KEY=", "GCS_LINEAR_API_KEY="):
            if line.startswith(prefix):
                return _unquote(line[len(prefix) :])
        return line
    return text.strip()


def load_api_key() -> str:
    for name in ("GCS_LINEAR_API_KEY", "LINEAR_API_KEY"):
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    for name in ("LINEAR_API_KEY_FILE", "GCS_LINEAR_API_KEY_FILE"):
        raw = (os.environ.get(name) or "").strip()
        if raw:
            path = Path(raw)
            if path.is_file():
                parsed = _parse_key_blob(path.read_text(encoding="utf-8"))
                if parsed:
                    return parsed
    state = (os.environ.get("GCS_A2A_STATE") or "").strip()
    candidates: list[Path] = []
    if state:
        root = Path(state)
        candidates.extend(
            [
                root / "secrets" / "linear.api_key",
                root / "linear.env",
            ]
        )
    home = Path(os.environ.get("HOME") or "").expanduser()
    if str(home):
        candidates.append(home / ".config" / "linear" / "api_key")
    for path in candidates:
        if not path.is_file():
            continue
        parsed = _parse_key_blob(path.read_text(encoding="utf-8"))
        if parsed:
            return parsed
    return ""


def _team_name_norm(value: Any) -> str:
    return str(value or "").strip().lower()


def is_living_sky_team(
    team: dict[str, Any] | None,
    *,
    team_keys: frozenset[str] | None = None,
) -> bool:
    if not isinstance(team, dict):
        return False
    keys = team_keys if team_keys is not None else DEFAULT_TEAM_KEYS
    key = str(team.get("key") or "").strip().lower()
    name = _team_name_norm(team.get("name"))
    if key and key in keys:
        return True
    compact = name.replace(" ", "")
    if name in DEFAULT_TEAM_NAMES or compact in DEFAULT_TEAM_NAMES:
        return True
    return False


def classify_issue(
    issue: dict[str, Any],
    *,
    team_keys: frozenset[str] | None = None,
) -> Decision:
    team = issue.get("team") if isinstance(issue.get("team"), dict) else {}
    identifier = str(issue.get("identifier") or "").strip() or "?"
    title = " ".join(str(issue.get("title") or "").split())
    issue_id = str(issue.get("id") or "").strip()
    archived = bool(issue.get("archivedAt"))
    team_key = str(team.get("key") or "").strip()
    state = issue.get("state") if isinstance(issue.get("state"), dict) else None
    state_name = str((state or {}).get("name") or "").strip()
    state_type = str((state or {}).get("type") or "").strip().lower()
    if not is_living_sky_team(team if isinstance(team, dict) else None, team_keys=team_keys):
        return Decision(
            action="skip",
            reason="other_team",
            archived=archived,
            identifier=identifier,
            title=title,
            state_name=state_name,
            state_type=state_type,
            issue_id=issue_id,
            team_key=team_key,
        )
    name_key = state_name.strip().lower()
    closed = state_type in CLOSED_STATE_TYPES or name_key in DELETE_STATE_NAMES
    if state is None or state_type in OPEN_STATE_TYPES or not closed:
        return Decision(
            action="skip",
            reason="open",
            archived=archived,
            identifier=identifier,
            title=title,
            state_name=state_name or "unknown",
            state_type=state_type,
            issue_id=issue_id,
            team_key=team_key,
        )
    return Decision(
        action="delete",
        reason="closed",
        archived=archived,
        identifier=identifier,
        title=title,
        state_name=state_name,
        state_type=state_type,
        issue_id=issue_id,
        team_key=team_key,
    )


def authorization_header(token: str) -> str:
    raw = token.strip()
    if raw.lower().startswith("bearer "):
        return raw
    return raw


def graphql_request(
    query: str,
    variables: dict[str, Any] | None = None,
    *,
    token: str,
    endpoint: str = LINEAR_GRAPHQL,
    timeout: float = 30.0,
) -> dict[str, Any]:
    payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=payload,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": authorization_header(token),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise RuntimeError(
            redact(f"LINEAR_PURGE graphql HTTP {exc.code} {err_body}", token)
        ) from None
    except urllib.error.URLError as exc:
        raise RuntimeError(redact(f"LINEAR_PURGE graphql URL error {exc}", token)) from None
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(redact(f"LINEAR_PURGE graphql JSON {exc}", token)) from None
    if not isinstance(parsed, dict):
        raise RuntimeError("LINEAR_PURGE graphql unexpected payload")
    errors = parsed.get("errors")
    if errors:
        raise RuntimeError(redact(f"LINEAR_PURGE graphql errors {errors}", token))
    return parsed


def fetch_issues(
    graphql_fn: Callable[..., dict[str, Any]],
) -> list[dict[str, Any]]:
    after: str | None = None
    nodes: list[dict[str, Any]] = []
    while True:
        payload = graphql_fn(
            QUERY_ISSUES,
            {
                "after": after,
                "includeArchived": True,
                "first": PAGE_SIZE,
            },
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        issues = data.get("issues") if isinstance(data, dict) else None
        if not isinstance(issues, dict):
            raise RuntimeError("LINEAR_PURGE graphql missing issues connection")
        batch = issues.get("nodes") or []
        if not isinstance(batch, list):
            raise RuntimeError("LINEAR_PURGE graphql issues.nodes is not a list")
        nodes.extend([item for item in batch if isinstance(item, dict)])
        page = issues.get("pageInfo") if isinstance(issues.get("pageInfo"), dict) else {}
        if not page.get("hasNextPage"):
            break
        after = str(page.get("endCursor") or "") or None
        if not after:
            break
    return nodes


def _truncate(title: str, limit: int = 80) -> str:
    if len(title) <= limit:
        return title
    return title[: limit - 1] + "…"


def _emit(stream: TextIO, token: str, line: str) -> None:
    stream.write(redact(line, token) + "\n")
    stream.flush()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="linear_purge_closed.py",
        description=(
            "Permanently delete Done/Canceled/Duplicate Living Sky (LIV) Linear "
            "issues via GraphQL issueDelete so they stop counting toward the "
            f"free-tier cap ({FREE_TIER_CAP}). Archive still counts; this never "
            "archives. Default is dry-run. Open Palemon/GCS work is skipped."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Call issueDelete (permanentlyDelete=true). Default is dry-run.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List candidates only (default). Cannot combine with --apply.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        metavar="N",
        help="Delete or would-delete at most N candidates (0 = no cap).",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.15,
        metavar="SEC",
        help="Pause between issueDelete calls (default 0.15).",
    )
    parser.add_argument(
        "--team-key",
        default="LIV",
        help="Living Sky team key to target (default LIV).",
    )
    parser.add_argument(
        "--cap",
        type=int,
        default=FREE_TIER_CAP,
        help=f"Free-tier cap used in the summary line (default {FREE_TIER_CAP}).",
    )
    parser.add_argument(
        "--endpoint",
        default=LINEAR_GRAPHQL,
        help="Linear GraphQL endpoint.",
    )
    return parser


def main(
    argv: list[str] | None = None,
    *,
    graphql_fn: Callable[..., dict[str, Any]] | None = None,
    token_fn: Callable[[], str] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    args = build_parser().parse_args(argv)
    if args.apply and args.dry_run:
        _emit(stderr, "", "LINEAR_PURGE fail --apply and --dry-run are mutually exclusive")
        return 2
    apply = bool(args.apply)
    token = (token_fn or load_api_key)()
    if not token:
        _emit(
            stderr,
            "",
            "LINEAR_PURGE fail missing LINEAR_API_KEY "
            "(set GCS_LINEAR_API_KEY, LINEAR_API_KEY, or LINEAR_API_KEY_FILE)",
        )
        return 1
    team_keys = frozenset({str(args.team_key or "LIV").strip().lower() or "liv"})
    transport = graphql_fn
    if transport is None:
        endpoint = str(args.endpoint or LINEAR_GRAPHQL)

        def transport(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
            return graphql_request(query, variables, token=token, endpoint=endpoint)

    try:
        issues = fetch_issues(transport)
    except RuntimeError as exc:
        _emit(stderr, token, str(exc))
        return 1

    decisions = [classify_issue(item, team_keys=team_keys) for item in issues]
    candidates = [item for item in decisions if item.action == "delete"]
    skipped_open = sum(1 for item in decisions if item.reason == "open")
    other_team = sum(1 for item in decisions if item.reason == "other_team")
    if args.limit and args.limit > 0:
        candidates = candidates[: args.limit]
    mode = "apply" if apply else "dry-run"
    _emit(
        stdout,
        token,
        "LINEAR_PURGE "
        f"{mode} candidates={len(candidates)} skipped_open={skipped_open} "
        f"other_team={other_team} counted={len(issues)} cap={args.cap}",
    )
    deleted = 0
    failed = 0
    for item in decisions:
        if item.action == "skip":
            flag = "archived " if item.archived else ""
            _emit(
                stdout,
                token,
                f"LINEAR_PURGE skip {item.identifier} {item.reason} "
                f"{item.state_name} {flag}{_truncate(item.title)}".rstrip(),
            )
    for item in candidates:
        archived = " archived" if item.archived else ""
        if not apply:
            _emit(
                stdout,
                token,
                f"LINEAR_PURGE would-delete {item.identifier} {item.state_name}"
                f"{archived} {_truncate(item.title)}".rstrip(),
            )
            continue
        if not item.issue_id:
            failed += 1
            _emit(stderr, token, f"LINEAR_PURGE fail {item.identifier} missing id")
            continue
        try:
            payload = transport(
                MUTATION_ISSUE_DELETE,
                {"id": item.issue_id, "permanentlyDelete": True},
            )
        except RuntimeError as exc:
            failed += 1
            _emit(stderr, token, f"LINEAR_PURGE fail {item.identifier} {exc}")
            continue
        data = payload.get("data") if isinstance(payload, dict) else None
        result = data.get("issueDelete") if isinstance(data, dict) else None
        success = bool(isinstance(result, dict) and result.get("success"))
        if not success:
            failed += 1
            _emit(stderr, token, f"LINEAR_PURGE fail {item.identifier} issueDelete success=false")
            continue
        deleted += 1
        _emit(
            stdout,
            token,
            f"LINEAR_PURGE deleted {item.identifier} {item.state_name}"
            f"{archived} {_truncate(item.title)}".rstrip(),
        )
        if args.sleep and args.sleep > 0:
            sleep_fn(float(args.sleep))
    remaining = len(issues) - deleted
    if apply:
        _emit(stdout, token, f"LINEAR_PURGE apply deleted={deleted} failed={failed}")
    status = "LINEAR_PURGE_OK" if failed == 0 else "LINEAR_PURGE_FAIL"
    _emit(
        stdout,
        token,
        f"{status} deleted={deleted} remaining_est={remaining} cap={args.cap}",
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
