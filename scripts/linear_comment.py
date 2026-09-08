#!/usr/bin/env python3
"""LIV-82: post a comment on a Living Sky Linear issue via GraphQL.

Directors call this instead of waiting for Donald DIY. Uses
scripts/directors/linear_key.py ($GCS_A2A_STATE/linear.env). Never prints
the API key. Refuses non-Living-Sky teams (never Black Swan Money).
Dry-run is the default; pass --apply to mutate. Stdlib only. Not Linear MCP.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, MutableMapping, TextIO

_DIRECTORS = Path(__file__).resolve().parent / "directors"
if str(_DIRECTORS) not in sys.path:
    sys.path.insert(0, str(_DIRECTORS))

from linear_key import apply_linear_key_env  # noqa: E402

LINEAR_GRAPHQL = "https://api.linear.app/graphql"
LIVING_SKY_TEAM_KEY = "LIV"
ISSUE_REF_RE = re.compile(r"([A-Za-z][A-Za-z0-9]*-\d+)")
ISSUE_URL_RE = re.compile(r"/issue/([A-Za-z][A-Za-z0-9]*-\d+)", re.I)

QUERY_ISSUE = """
query Issue($id: String!) {
  issue(id: $id) {
    id
    identifier
    url
    title
    team { id key name }
  }
}
"""

MUTATION_COMMENT_CREATE = """
mutation CommentCreate($input: CommentCreateInput!) {
  commentCreate(input: $input) {
    success
    comment { id url body }
  }
}
"""

GraphQLFn = Callable[[str, dict[str, Any] | None], dict[str, Any]]
TokenFn = Callable[[], str]


def redact(text: str, token: str | None) -> str:
    out = str(text)
    if token:
        out = out.replace(token, "<redacted>")
        if token.lower().startswith("bearer "):
            out = out.replace(token.split(None, 1)[-1], "<redacted>")
    return out


def _nested(data: dict[str, Any], *keys: str) -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def parse_issue_ref(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        raise RuntimeError("LINEAR_COMMENT fail missing --issue")
    url_hit = ISSUE_URL_RE.search(text)
    if url_hit:
        return url_hit.group(1).upper()
    direct = re.fullmatch(r"([A-Za-z][A-Za-z0-9]*-\d+)", text)
    if direct:
        return direct.group(1).upper()
    loose = ISSUE_REF_RE.search(text)
    if loose:
        return loose.group(1).upper()
    raise RuntimeError(f"LINEAR_COMMENT fail invalid --issue {text}")


def is_living_sky_identifier(identifier: str) -> bool:
    return str(identifier or "").upper().startswith(f"{LIVING_SKY_TEAM_KEY}-")


def is_living_sky_team(team: dict[str, Any] | None) -> bool:
    if not isinstance(team, dict):
        return False
    name = str(team.get("name") or "")
    if "black swan" in name.lower():
        return False
    key = str(team.get("key") or "").upper()
    return key == LIVING_SKY_TEAM_KEY


def load_api_key(
    *,
    environ: MutableMapping[str, str] | None = None,
    home: Path | None = None,
) -> str:
    env = environ if environ is not None else os.environ
    for name in ("LINEAR_API_KEY", "GCS_LINEAR_API_KEY"):
        value = str(env.get(name) or "").strip()
        if value:
            return value
    state = str(env.get("GCS_A2A_STATE") or "").strip()
    state_dir = Path(state) if state else None
    home_path = home
    if home_path is None:
        home_raw = str(env.get("HOME") or os.environ.get("HOME") or "")
        home_path = Path(home_raw) if home_raw else None
    apply_linear_key_env(env, state_dir=state_dir, home=home_path)
    value = str(env.get("LINEAR_API_KEY") or "").strip()
    if value:
        return value
    raise RuntimeError(
        "LINEAR_COMMENT fail missing LINEAR_API_KEY "
        "(set LINEAR_API_KEY or $GCS_A2A_STATE/linear.env via linear_key.py)"
    )


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
        try:
            err_body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            err_body = str(exc)
        raise RuntimeError(
            redact(f"LINEAR_COMMENT graphql HTTP {exc.code} {err_body}", token)
        ) from None
    except urllib.error.URLError as exc:
        raise RuntimeError(
            redact(f"LINEAR_COMMENT graphql URL error {exc}", token)
        ) from None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(redact(f"LINEAR_COMMENT graphql JSON {exc}", token)) from None
    if not isinstance(parsed, dict):
        raise RuntimeError("LINEAR_COMMENT graphql unexpected payload")
    errors = parsed.get("errors")
    if errors:
        raise RuntimeError(redact(f"LINEAR_COMMENT graphql errors {errors}", token))
    return parsed


def _emit(stream: TextIO, token: str | None, message: str) -> None:
    stream.write(redact(message, token) + "\n")
    stream.flush()


def main(
    argv: list[str] | None = None,
    *,
    graphql_fn: GraphQLFn | None = None,
    token_fn: TokenFn | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        prog="linear_comment.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "LIV-82 Living Sky GraphQL commentCreate. Uses linear_key.py "
            "($GCS_A2A_STATE/linear.env). Never prints LINEAR_API_KEY. "
            "Refuses non-Living-Sky teams (never Black Swan Money). "
            "Dry-run default. Not Linear MCP."
        ),
        epilog=(
            "Examples:\n"
            '  python3 scripts/linear_comment.py --issue LIV-82 --body "..."\n'
            '  python3 scripts/linear_comment.py --issue LIV-82 --body "..." --apply\n'
        ),
    )
    parser.add_argument(
        "--issue",
        required=True,
        help="Living Sky identifier (LIV-82) or linear.app/livingsky issue URL",
    )
    parser.add_argument(
        "--body",
        required=True,
        help="Markdown comment body (dry-run does not post)",
    )
    parser.add_argument("--apply", action="store_true", help="post commentCreate")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="look up the issue and print would-comment (default)",
    )
    parser.add_argument("--endpoint", default=LINEAR_GRAPHQL)
    args = parser.parse_args(argv)
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    if args.apply and args.dry_run:
        _emit(err, None, "LINEAR_COMMENT fail --apply and --dry-run are mutually exclusive")
        return 2
    body = str(args.body or "").strip()
    if not body:
        _emit(err, None, "LINEAR_COMMENT fail --body is empty")
        return 2
    try:
        identifier = parse_issue_ref(args.issue)
    except Exception as exc:
        _emit(err, None, str(exc))
        return 2
    if not is_living_sky_identifier(identifier):
        _emit(
            err,
            None,
            f"LINEAR_COMMENT fail {identifier} not-living-sky (never Black Swan)",
        )
        return 2
    token = ""
    getter = token_fn if token_fn is not None else load_api_key
    try:
        token = getter()
    except Exception as exc:
        _emit(err, None, str(exc))
        return 2
    apply = bool(args.apply)
    mode = "apply" if apply else "dry-run"
    if graphql_fn is None:
        endpoint = str(args.endpoint or LINEAR_GRAPHQL)
        graphql_fn = lambda q, v=None: graphql_request(  # noqa: E731
            q, v, token=token, endpoint=endpoint
        )
    try:
        payload = graphql_fn(QUERY_ISSUE, {"id": identifier})
    except Exception as exc:
        _emit(err, token, f"LINEAR_COMMENT fail {exc}")
        return 2
    issue = _nested(payload, "data", "issue")
    if not isinstance(issue, dict):
        _emit(err, token, f"LINEAR_COMMENT fail {identifier} issue-not-found")
        return 2
    issue_id = str(issue.get("id") or "").strip()
    found_id = str(issue.get("identifier") or identifier).strip() or identifier
    team = issue.get("team") if isinstance(issue.get("team"), dict) else {}
    if not is_living_sky_identifier(found_id) or not is_living_sky_team(team):
        _emit(
            err,
            token,
            f"LINEAR_COMMENT fail {found_id} not-living-sky (never Black Swan)",
        )
        return 2
    if not issue_id:
        _emit(err, token, f"LINEAR_COMMENT fail {found_id} missing id")
        return 2
    if not apply:
        _emit(err, token, f"LINEAR_COMMENT {mode} issue={found_id}")
        _emit(out, token, f"LINEAR_COMMENT would-comment {found_id}")
        _emit(out, token, f"LINEAR_COMMENT_OK issue={found_id} comment=none mode={mode}")
        return 0
    try:
        created = graphql_fn(
            MUTATION_COMMENT_CREATE,
            {"input": {"issueId": issue_id, "body": body}},
        )
    except Exception as exc:
        _emit(err, token, f"LINEAR_COMMENT fail {found_id} {exc}")
        return 1
    node = _nested(created, "data", "commentCreate")
    if not isinstance(node, dict) or not node.get("success"):
        _emit(err, token, f"LINEAR_COMMENT fail {found_id} commentCreate success=false")
        return 1
    comment = node.get("comment") if isinstance(node.get("comment"), dict) else {}
    comment_id = str(comment.get("id") or "")
    comment_url = str(comment.get("url") or "")
    _emit(
        err,
        token,
        f"LINEAR_COMMENT apply {found_id} comment={comment_id} {comment_url}".strip(),
    )
    _emit(
        out,
        token,
        f"LINEAR_COMMENT_OK issue={found_id} comment={comment_id} mode={mode}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
