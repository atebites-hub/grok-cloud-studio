#!/usr/bin/env bash
# LIV-82 remaining vs OPEN GitHub #109 (hive stamps Living Sky after each mind turn).
#
# This script stamps linear.app/livingsky AFTER a real Extra High CLOUD_LAUNCH_OK
# (spawn-waiter / launch hook) or a dump that records CLOUD_LAUNCH_OK.
# It is not a every-chatter / every-mind-turn stamp. Do not copy #109's mind.py hook.
#
# Default issue: LIV-69. Optional: GCS_LINEAR_STAMP_ISSUES=LIV-69,LIV-63,LIV-82,LIV-96.
# Living Sky only (team LIV). NEVER Black Swan. Never print credentials.
# LINEAR_API_KEY unset → LINEAR_STAMP_FAIL, local evidence still recorded.
# GraphQL commentCreate only. Do not fake Linear MCP save_comment.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export GCS_ROOT="${GCS_ROOT:-$ROOT}"

python3 - "$@" <<'PY'
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

DEFAULT_API = "https://api.linear.app/graphql"
LIVING_SKY_HOST = "linear.app/livingsky"
LIVING_SKY_URL_KEY = "livingsky"
LIVING_SKY_TEAM = "LIV"
DEFAULT_ISSUE = "LIV-69"
TRUSTED_SOURCES = frozenset({"spawn-waiter", "launch"})
STUDIO_ENV_KEYS = (
    "LINEAR_API_KEY",
    "GCS_LINEAR_API",
    "GCS_LINEAR_STAMP_ISSUES",
    "GCS_LINEAR_TIMEOUT",
)
BLACK_SWAN_KEYS = frozenset(
    {"blackswan", "black-swan", "blackswanmoney", "black-swan-money"}
)
ISSUE_RE = re.compile(r"^LIV-\d+$")
ID_RE = re.compile(r"\bid=([A-Za-z0-9._-]+)")
RUN_RE = re.compile(r"\b(?:run_id|run)=([A-Za-z0-9._-]+)")
NAME_RE = re.compile(r"\bname=([^\s]+)")
_SECRET_ASSIGN_RE = re.compile(
    r"(?i)\b(CURSOR_API_KEY|LINEAR_API_KEY|GCS_WEBHOOK_SECRET|Authorization|"
    r"Bearer|api[_-]?key)\s*[=:]\s*\S+"
)
_LIN_TOKEN_RE = re.compile(r"\blin_[A-Za-z0-9_]{8,}\b")

ISSUE_QUERY = """
query LivingSkyIssue($id: String!) {
  organization { id name urlKey }
  issue(id: $id) {
    id identifier url title
    team { id key name }
  }
}
"""
COMMENT_MUTATION = """
mutation CommentCreate($input: CommentCreateInput!) {
  commentCreate(input: $input) {
    success
    comment { id url }
  }
}
"""


def redact(text: str) -> str:
    if not text:
        return text
    out = _SECRET_ASSIGN_RE.sub(lambda m: f"{m.group(1)}=[redacted]", text)
    key = (os.environ.get("LINEAR_API_KEY") or "").strip()
    if key:
        out = out.replace(key, "[redacted]")
    cursor = (os.environ.get("CURSOR_API_KEY") or "").strip()
    if cursor:
        out = out.replace(cursor, "[redacted]")
    return _LIN_TOKEN_RE.sub("lin_[redacted]", out)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def root_dir() -> Path:
    raw = (os.environ.get("GCS_ROOT") or "").strip()
    return Path(raw) if raw else Path.cwd()


def state_dir() -> Path:
    raw = (os.environ.get("GCS_A2A_STATE") or "").strip()
    return Path(raw) if raw else root_dir() / ".a2a-state"


def evidence_path() -> Path:
    return state_dir() / "linear-stamps" / "after-launch.jsonl"


def parse_args(argv: list[str]) -> dict[str, str]:
    out = {"id": "", "run": "", "name": "", "source": "", "evidence": "", "issues": ""}
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in {
            "--id",
            "--run",
            "--name",
            "--source",
            "--evidence",
            "--issues",
        } and i + 1 < len(argv):
            out[arg[2:]] = argv[i + 1]
            i += 2
            continue
        if arg in {"-h", "--help"}:
            print(
                "Usage: linear_stamp_after_launch_beat1740.sh "
                "[--id ID] [--run RUN] [--name NAME] "
                "[--source spawn-waiter|launch] [--evidence FILE] [--issues LIV-69,...]",
                file=sys.stderr,
            )
            raise SystemExit(0)
        print(f"unknown arg: {arg}", file=sys.stderr)
        raise SystemExit(2)
    return out


def parse_issues(raw: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    blob = raw or os.environ.get("GCS_LINEAR_STAMP_ISSUES") or DEFAULT_ISSUE
    for part in blob.replace(";", ",").split(","):
        ident = part.strip().upper()
        if not ident:
            continue
        if not ISSUE_RE.fullmatch(ident):
            continue
        if ident in seen:
            continue
        seen.add(ident)
        found.append(ident)
    return found or [DEFAULT_ISSUE]


def apply_studio_env() -> None:
    """Fill Linear knobs from $GCS_A2A_STATE/studio.env when unset. Never print values."""
    path = state_dir() / "studio.env"
    if not path.is_file():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, val = stripped.split("=", 1)
        key = key.strip()
        if key not in STUDIO_ENV_KEYS:
            continue
        if (os.environ.get(key) or "").strip():
            continue
        val = val.strip().strip("'\"")
        if val:
            os.environ[key] = val


def authorization_header(api_key: str) -> str:
    """Personal Linear keys are Authorization: <key> with no Bearer prefix.

    OAuth tokens may already include 'Bearer '; leave those unchanged.
    """
    return api_key.strip()


def linear_api_url() -> str:
    raw = (os.environ.get("GCS_LINEAR_API") or DEFAULT_API).strip() or DEFAULT_API
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if parsed.scheme == "https" and host:
        return raw
    if parsed.scheme == "http" and host in {"127.0.0.1", "localhost", "::1"}:
        return raw
    return ""


def linear_timeout() -> float:
    raw = (os.environ.get("GCS_LINEAR_TIMEOUT") or "").strip()
    try:
        return max(1.0, float(raw)) if raw else 10.0
    except ValueError:
        return 10.0


def fill_from_dump(text: str, fields: dict[str, str]) -> None:
    if not fields.get("id"):
        match = ID_RE.search(text)
        if match:
            fields["id"] = match.group(1)
    if not fields.get("run"):
        match = RUN_RE.search(text)
        if match:
            fields["run"] = match.group(1)
    if not fields.get("name"):
        match = NAME_RE.search(text)
        if match:
            fields["name"] = match.group(1)


def record(row: dict[str, Any]) -> None:
    rec = dict(row)
    rec.setdefault("ts", now_iso())
    rec.setdefault("event", "after-launch")
    rec.setdefault("save_comment", False)
    rec.setdefault("workspace", LIVING_SKY_URL_KEY)
    path = evidence_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def emit(line: str) -> None:
    print(redact(line), flush=True)


def fail(
    reason: str,
    fields: dict[str, str],
    issues: list[str],
    *,
    graphql: bool = False,
    extra: dict[str, Any] | None = None,
) -> int:
    rec: dict[str, Any] = {
        "id": fields.get("id") or "",
        "run": fields.get("run") or "",
        "name": fields.get("name") or "",
        "source": fields.get("source") or "",
        "issues": issues,
        "status": "fail",
        "reason": reason,
        "graphql": graphql,
        "save_comment": False,
    }
    if extra:
        rec.update(extra)
    record(rec)
    bits = [
        "LINEAR_STAMP_FAIL",
        f"reason={reason}",
    ]
    if fields.get("id"):
        bits.append(f"id={fields['id']}")
    if issues:
        bits.append("issues=" + ",".join(issues))
    emit(" ".join(bits))
    return 1


def living_sky_ok(org: dict[str, Any], issue: dict[str, Any]) -> str:
    url_key = str(org.get("urlKey") or "").strip().lower()
    org_name = str(org.get("name") or "")
    name_l = org_name.lower()
    team = issue.get("team") if isinstance(issue.get("team"), dict) else {}
    team_key = str(team.get("key") or "").strip().upper()
    team_name = str(team.get("name") or "").lower()
    issue_url = str(issue.get("url") or "").lower()
    if "black swan" in name_l or "black swan" in team_name or url_key in BLACK_SWAN_KEYS:
        return "black-swan"
    if url_key and url_key != LIVING_SKY_URL_KEY:
        return "not-living-sky"
    if team_key and team_key != LIVING_SKY_TEAM:
        return "not-living-sky"
    if issue_url and LIVING_SKY_HOST not in issue_url:
        return "not-living-sky"
    if url_key != LIVING_SKY_URL_KEY:
        return "not-living-sky"
    if team_key != LIVING_SKY_TEAM:
        return "not-living-sky"
    return ""


def graphql_post(payload: dict[str, Any], api_url: str, api_key: str) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        api_url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": authorization_header(api_key),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=linear_timeout()) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = redact(exc.read().decode("utf-8", errors="replace"))[:400]
        return {"errors": [{"message": f"http-{exc.code} {body}"}]}
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {"errors": [{"message": redact(type(exc).__name__)}]}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"errors": [{"message": "invalid-json"}]}
    return parsed if isinstance(parsed, dict) else {"errors": [{"message": "unexpected-graphql"}]}


def comment_body(fields: dict[str, str], issue: str) -> str:
    return "\n".join(
        [
            "Extra High launch (Living Sky stamp after CLOUD_LAUNCH_OK).",
            "Not a mind-turn chatter stamp. Not Linear MCP save_comment.",
            "",
            f"issue={issue} id={fields.get('id') or ''} run={fields.get('run') or ''} "
            f"name={fields.get('name') or ''} source={fields.get('source') or 'evidence'}",
        ]
    )


def main(argv: list[str]) -> int:
    fields = parse_args(argv)
    apply_studio_env()
    issues = parse_issues(fields.get("issues") or "")
    dump_text = ""
    evidence = fields.get("evidence") or ""
    if evidence:
        path = Path(evidence)
        if not path.is_file():
            return fail("no-evidence", fields, issues)
        dump_text = path.read_text(encoding="utf-8", errors="replace")
        fill_from_dump(dump_text, fields)
        if "CLOUD_LAUNCH_OK" not in dump_text:
            return fail("no-launch", fields, issues)

    source = (fields.get("source") or "").strip().lower()
    trusted = source in TRUSTED_SOURCES or (
        bool(evidence) and "CLOUD_LAUNCH_OK" in dump_text
    )
    if not trusted:
        return fail("no-launch", fields, issues)

    emit(
        "LINEAR_STAMP_ATTEMPT "
        f"id={fields.get('id') or ''} run={fields.get('run') or ''} "
        f"source={source or 'evidence'} issues={','.join(issues)}"
    )

    api_key = (os.environ.get("LINEAR_API_KEY") or "").strip()
    if not api_key:
        return fail("no-key", fields, issues, graphql=False)

    api_url = linear_api_url()
    if not api_url:
        return fail("bad-endpoint", fields, issues, graphql=False)

    comments: list[dict[str, str]] = []
    for ident in issues:
        parsed = graphql_post(
            {"query": ISSUE_QUERY, "variables": {"id": ident}},
            api_url,
            api_key,
        )
        errors = parsed.get("errors") if isinstance(parsed, dict) else None
        if errors:
            msg = ""
            if isinstance(errors, list) and errors and isinstance(errors[0], dict):
                msg = str(errors[0].get("message") or "")
            return fail(
                "graphql-error",
                fields,
                issues,
                graphql=True,
                extra={"error": redact(msg)[:240]},
            )
        data = parsed.get("data") if isinstance(parsed.get("data"), dict) else {}
        org = data.get("organization") if isinstance(data.get("organization"), dict) else {}
        issue = data.get("issue") if isinstance(data.get("issue"), dict) else {}
        if not issue:
            return fail("no-issue", fields, issues, graphql=True)
        refused = living_sky_ok(org, issue)
        if refused:
            return fail(refused, fields, issues, graphql=True)
        issue_id = str(issue.get("id") or "")
        created = graphql_post(
            {
                "query": COMMENT_MUTATION,
                "variables": {
                    "input": {
                        "issueId": issue_id,
                        "body": comment_body(fields, ident),
                    }
                },
            },
            api_url,
            api_key,
        )
        c_err = created.get("errors") if isinstance(created, dict) else None
        if c_err:
            return fail("graphql-error", fields, issues, graphql=True)
        c_data = created.get("data") if isinstance(created.get("data"), dict) else {}
        payload = (
            c_data.get("commentCreate")
            if isinstance(c_data.get("commentCreate"), dict)
            else {}
        )
        comment = payload.get("comment") if isinstance(payload.get("comment"), dict) else {}
        if not payload.get("success"):
            return fail("linear-fail", fields, issues, graphql=True)
        comments.append(
            {
                "issue": ident,
                "comment_id": str(comment.get("id") or ""),
                "url": str(comment.get("url") or ""),
            }
        )

    record(
        {
            "id": fields.get("id") or "",
            "run": fields.get("run") or "",
            "name": fields.get("name") or "",
            "source": source or "evidence",
            "issues": issues,
            "status": "ok",
            "reason": "ok",
            "graphql": True,
            "save_comment": False,
            "comments": comments,
        }
    )
    emit(
        "LINEAR_STAMP_OK "
        f"id={fields.get('id') or ''} issues={','.join(issues)} "
        f"comments={len(comments)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
PY
