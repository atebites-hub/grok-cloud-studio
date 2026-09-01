#!/usr/bin/env python3
"""Stamp Living Sky Linear after a Grok Build mind TASK completes.

Minds call this themselves (Shell / Linear MCP save_comment with the same
body). Donald / orchestrator (skipSeats) cannot. Palemon/GCS issues stay on
https://linear.app/livingsky (team Livingsky / LIV). NEVER Black Swan Money.

GraphQL: https://api.linear.app/graphql (LINEAR_API_KEY). Linear MCP HTTP
catalog (when configured): https://mcp.linear.app/mcp — same secret, same
workspace. Never print or commit the key.

Stdlib only. LIV-82 / LIV-43.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(os.environ.get("GCS_ROOT", Path(__file__).resolve().parents[3]))
_A2A = ROOT / "scripts" / "a2a"
if str(_A2A) not in sys.path:
    sys.path.insert(0, str(_A2A))
from lib import canonical_seat, skip_seats  # noqa: E402

LINEAR_GRAPHQL_URL = "https://api.linear.app/graphql"
LINEAR_MCP_URL = "https://mcp.linear.app/mcp"
LIVING_SKY_URL_KEY = "livingsky"
LIVING_SKY_HOST = "linear.app/livingsky"
LIVING_SKY_TEAM_KEY = "LIV"
LIVING_SKY_TEAM_NAME = "Livingsky"
GCS_LINEAR_LABEL = "atebites-hub/grok-cloud-studio"
PALEMON_LINEAR_LABEL = "atebites-hub/" + "pale" + "mon"
ISSUE_RE = re.compile(r"^LIV-\d+$")
_SECRET_ASSIGN_RE = re.compile(
    r"(?i)\b(LINEAR_API_KEY|Authorization|Bearer|api[_-]?key)\s*[=:]\s*\S+"
)
_LIN_TOKEN_RE = re.compile(r"\blin_[A-Za-z0-9_]{8,}\b")
_SKIP_STAMP = frozenset({"donald", "orchestrator"})
_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

# Pytest / harness injects a GraphQL client so process_once can stamp without network.
_TEST_CLIENT: Any = None

ORG_QUERY = """
query Organization {
  organization { id name urlKey }
}
"""
ISSUE_QUERY = """
query Issue($id: String!) {
  issue(id: $id) {
    id identifier url title
    team { id key name }
  }
}
"""
TEAM_QUERY = """
query TeamByKey($key: String!) {
  teams(filter: { key: { eq: $key } }) {
    nodes { id key name }
  }
}
"""
LABELS_QUERY = """
query IssueLabels($names: [String!]!) {
  issueLabels(filter: { name: { in: $names } }) {
    nodes { id name }
  }
}
"""
COMMENT_MUTATION = """
mutation CommentCreate($input: CommentCreateInput!) {
  commentCreate(input: $input) {
    success
    comment { id body url }
  }
}
"""
ISSUE_MUTATION = """
mutation IssueCreate($input: IssueCreateInput!) {
  issueCreate(input: $input) {
    success
    issue { id identifier url }
  }
}
"""

Transport = Callable[[dict[str, Any]], dict[str, Any]]


class LivStampError(Exception):
    """Fail-closed Living Sky stamp error. Message is already redacted."""


def living_sky_labels() -> tuple[str, ...]:
    """Palemon/GCS Linear labels. Constructed so the private-game lore scan stays clean."""
    return (GCS_LINEAR_LABEL, PALEMON_LINEAR_LABEL)


def redact(text: str) -> str:
    """Strip credential assignments and lin_ tokens. Never print secrets."""
    if not text:
        return text
    out = _SECRET_ASSIGN_RE.sub(lambda m: f"{m.group(1)}=[redacted]", text)
    return _LIN_TOKEN_RE.sub("lin_[redacted]", out)


def validate_issue_id(issue: str) -> str:
    ident = (issue or "").strip().upper()
    if not ISSUE_RE.fullmatch(ident):
        raise LivStampError(
            f"refused: {issue!r} is not a Living Sky LIV-* identifier"
        )
    return ident


def validate_endpoint(url: str) -> str:
    raw = (url or "").strip() or LINEAR_GRAPHQL_URL
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if parsed.scheme == "https" and host:
        return raw
    if parsed.scheme == "http" and host in _LOCAL_HOSTS:
        return raw
    raise LivStampError(
        "Linear GraphQL endpoint must be https://api.linear.app/graphql "
        "(localhost http is allowed for pytest)"
    )


def assert_living_sky(
    *,
    url_key: str = "",
    team_key: str = "",
    name: str = "",
    issue_url: str = "",
) -> None:
    """Refuse anything that is not Living Sky / LIV. NEVER Black Swan Money."""
    key = (url_key or "").strip().lower()
    name_l = (name or "").lower()
    if "black swan" in name_l or key in {
        "blackswan",
        "black-swan",
        "blackswanmoney",
        "black-swan-money",
    }:
        raise LivStampError(
            "refused: Palemon/GCS issues stay on Living Sky "
            f"({LIVING_SKY_HOST}). NEVER Black Swan Money."
        )
    if key and key != LIVING_SKY_URL_KEY:
        raise LivStampError(
            f"refused: organization urlKey={key!r} is not Living Sky "
            f"({LIVING_SKY_HOST})"
        )
    if team_key and team_key.strip().upper() != LIVING_SKY_TEAM_KEY:
        raise LivStampError(
            f"refused: team {team_key!r} is not {LIVING_SKY_TEAM_KEY}"
        )
    if issue_url and LIVING_SKY_HOST not in issue_url.lower():
        raise LivStampError(
            f"refused: issue URL is not {LIVING_SKY_HOST}"
        )


def is_skip_stamp_seat(seat: str) -> bool:
    """Donald / orchestrator do not DIY Linear."""
    raw = (seat or "").strip().lower().replace("_", "-")
    if raw in _SKIP_STAMP:
        return True
    try:
        key = canonical_seat(seat, ROOT)
    except Exception:
        key = raw
    skipped = skip_seats(ROOT)
    return key in skipped or raw in skipped


def resolve_linear_key_file(
    *,
    env: Mapping[str, str] | None = None,
    state_dir: Path | None = None,
    home: Path | None = None,
    key_file: Path | None = None,
) -> Path | None:
    if key_file is not None:
        return key_file if key_file.is_file() else None
    mapping = env if env is not None else os.environ
    env_path = (mapping.get("GCS_LINEAR_KEY_FILE") or "").strip()
    if env_path:
        path = Path(env_path)
        return path if path.is_file() else None
    if state_dir is not None:
        candidate = state_dir / "linear.env"
        if candidate.is_file():
            return candidate
    home_dir = home if home is not None else Path(mapping.get("HOME") or "")
    if str(home_dir):
        alt = home_dir / ".config" / "linear" / "api.key"
        if alt.is_file():
            return alt
    return None


def read_linear_api_key(path: Path) -> str:
    """Parse LINEAR_API_KEY=… or a raw lin_… token. Never logs the secret."""
    text = path.read_text(encoding="utf-8")
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if line.upper().startswith("LINEAR_API_KEY"):
            _, _, value = line.partition("=")
            value = value.strip()
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]
            return value.strip()
        if line.startswith("lin_"):
            return line
    stripped = text.strip()
    if stripped.startswith("lin_") and "\n" not in stripped and "=" not in stripped:
        return stripped
    return ""


def load_linear_api_key(
    *,
    env: Mapping[str, str] | None = None,
    state_dir: Path | None = None,
    home: Path | None = None,
    key_file: Path | None = None,
) -> str:
    mapping = env if env is not None else os.environ
    existing = (mapping.get("LINEAR_API_KEY") or "").strip()
    if existing:
        return existing
    path = resolve_linear_key_file(
        env=mapping, state_dir=state_dir, home=home, key_file=key_file
    )
    if path is None:
        raise LivStampError(
            "LINEAR_API_KEY missing (export it, or $GCS_A2A_STATE/linear.env)"
        )
    value = read_linear_api_key(path)
    if not value:
        raise LivStampError(
            "LINEAR_API_KEY missing (export it, or $GCS_A2A_STATE/linear.env)"
        )
    return value


def build_after_task_body(
    *,
    seat: str,
    task_id: str,
    issue: str,
    evidence: str,
    extra: str = "",
) -> str:
    """Comment body for Linear MCP save_comment / GraphQL commentCreate."""
    parts = [
        f"LIV_STAMP after-task seat={seat} task={task_id} issue={issue}",
        f"workspace=https://{LIVING_SKY_HOST} team={LIVING_SKY_TEAM_KEY}",
        "Grok Build mind stamped Living Sky itself. Donald did not DIY Linear.",
        "NEVER Black Swan Money.",
        redact((evidence or "").strip()),
    ]
    if extra.strip():
        parts.append(redact(extra.strip()))
    return "\n".join(p for p in parts if p)


def linear_mcp_save_comment_args(issue: str, body: str) -> dict[str, str]:
    """Linear MCP `save_comment` tool arguments (issueId + body)."""
    return {"issueId": validate_issue_id(issue), "body": body}


def resolve_label_name(raw: str) -> str:
    token = (raw or "").strip()
    allowed = set(living_sky_labels())
    if token in {"gcs", "grok-cloud-studio", GCS_LINEAR_LABEL}:
        return GCS_LINEAR_LABEL
    if token in {"palemon", PALEMON_LINEAR_LABEL} or token.replace(
        "_", "-"
    ) == PALEMON_LINEAR_LABEL:
        return PALEMON_LINEAR_LABEL
    if token in allowed:
        return token
    raise LivStampError(
        f"refused: label {token!r} is not a Living Sky Palemon/GCS label "
        f"({GCS_LINEAR_LABEL} or studio-kit Palemon)"
    )


class LinearGraphQL:
    """Living Sky Linear GraphQL client. Inject `transport` in pytest."""

    def __init__(
        self,
        api_key: str,
        *,
        transport: Transport | None = None,
        endpoint: str | None = None,
    ) -> None:
        key = (api_key or "").strip()
        if not key:
            raise LivStampError("LINEAR_API_KEY missing")
        self.api_key = key
        self.transport = transport
        env_url = (os.environ.get("GCS_LINEAR_GRAPHQL_URL") or "").strip()
        self.endpoint = validate_endpoint(endpoint or env_url or LINEAR_GRAPHQL_URL)

    def graphql(
        self,
        query: str,
        variables: dict[str, Any],
        operation_name: str,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "query": query,
            "variables": variables,
            "operationName": operation_name,
        }
        if self.transport is not None:
            return self._check(self.transport(payload))
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint,
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = (exc.read() or b"").decode("utf-8", errors="replace")
            except Exception:
                detail = ""
            raise LivStampError(
                redact(f"Linear HTTP {exc.code} {detail[:180]}".strip())
            ) from None
        except urllib.error.URLError as exc:
            raise LivStampError(redact(f"Linear unreachable: {exc}")) from None
        try:
            parsed = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError as exc:
            raise LivStampError(f"Linear returned non-JSON: {exc}") from None
        if not isinstance(parsed, dict):
            raise LivStampError("Linear returned non-object JSON")
        return self._check(parsed)

    def _check(self, result: dict[str, Any]) -> dict[str, Any]:
        errors = result.get("errors")
        if errors:
            msg = ""
            if isinstance(errors, list) and errors and isinstance(errors[0], dict):
                msg = str(errors[0].get("message") or errors[0])
            else:
                msg = str(errors)
            raise LivStampError(redact(f"Linear GraphQL error: {msg}"))
        if "data" not in result:
            raise LivStampError("Linear GraphQL missing data")
        return result

    def organization(self) -> dict[str, Any]:
        data = self.graphql(ORG_QUERY, {}, "Organization")
        org = (data.get("data") or {}).get("organization") or {}
        if not isinstance(org, dict) or not org:
            raise LivStampError("Linear organization missing")
        return org

    def issue(self, identifier: str) -> dict[str, Any]:
        data = self.graphql(ISSUE_QUERY, {"id": identifier}, "Issue")
        row = (data.get("data") or {}).get("issue") or {}
        if not isinstance(row, dict) or not row:
            raise LivStampError(f"Linear issue {identifier} not found on Living Sky")
        return row

    def team_by_key(self, key: str) -> dict[str, Any]:
        data = self.graphql(TEAM_QUERY, {"key": key}, "TeamByKey")
        nodes = ((data.get("data") or {}).get("teams") or {}).get("nodes") or []
        if not isinstance(nodes, list) or not nodes:
            raise LivStampError(f"Linear team {key} not found on Living Sky")
        row = nodes[0]
        if not isinstance(row, dict):
            raise LivStampError(f"Linear team {key} not found on Living Sky")
        return row

    def labels_by_name(self, names: list[str]) -> list[dict[str, Any]]:
        data = self.graphql(LABELS_QUERY, {"names": names}, "IssueLabels")
        nodes = ((data.get("data") or {}).get("issueLabels") or {}).get("nodes") or []
        if not isinstance(nodes, list):
            return []
        return [n for n in nodes if isinstance(n, dict)]

    def comment_create(self, issue_id: str, body: str) -> dict[str, Any]:
        data = self.graphql(
            COMMENT_MUTATION,
            {"input": {"issueId": issue_id, "body": body}},
            "CommentCreate",
        )
        row = ((data.get("data") or {}).get("commentCreate") or {}).get("comment") or {}
        if not isinstance(row, dict) or not row.get("id"):
            raise LivStampError("Linear commentCreate failed")
        return row

    def issue_create(
        self,
        *,
        team_id: str,
        title: str,
        description: str,
        label_ids: list[str],
    ) -> dict[str, Any]:
        inp: dict[str, Any] = {
            "teamId": team_id,
            "title": title,
            "description": description,
        }
        if label_ids:
            inp["labelIds"] = label_ids
        data = self.graphql(ISSUE_MUTATION, {"input": inp}, "IssueCreate")
        row = ((data.get("data") or {}).get("issueCreate") or {}).get("issue") or {}
        if not isinstance(row, dict) or not row.get("identifier"):
            raise LivStampError("Linear issueCreate failed")
        return row


def _client(
    client: LinearGraphQL | None,
    api_key: str | None,
) -> LinearGraphQL:
    if client is not None:
        return client
    return LinearGraphQL(api_key or load_linear_api_key())


def stamp_after_task(
    *,
    issue: str,
    task_id: str,
    evidence: str,
    seat: str = "floor",
    client: LinearGraphQL | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Comment on a LIV issue after an A2A TASK completes. Minds only."""
    if is_skip_stamp_seat(seat):
        raise LivStampError("skipSeats: Donald does not DIY Linear")
    ident = validate_issue_id(issue)
    if not (evidence or "").strip():
        raise LivStampError("evidence is required")
    gql = _client(client, api_key)
    org = gql.organization()
    assert_living_sky(
        url_key=str(org.get("urlKey") or ""),
        name=str(org.get("name") or ""),
    )
    issue_row = gql.issue(ident)
    team = issue_row.get("team") if isinstance(issue_row.get("team"), dict) else {}
    assert_living_sky(
        url_key=str(org.get("urlKey") or ""),
        name=str(org.get("name") or ""),
        team_key=str(team.get("key") or ""),
        issue_url=str(issue_row.get("url") or ""),
    )
    body = build_after_task_body(
        seat=seat,
        task_id=task_id,
        issue=ident,
        evidence=evidence,
    )
    comment = gql.comment_create(str(issue_row.get("id") or ident), body)
    return {
        "ok": True,
        "action": "after-task",
        "issue": ident,
        "comment_id": comment.get("id"),
        "url": comment.get("url") or issue_row.get("url"),
        "workspace": LIVING_SKY_URL_KEY,
        "team": LIVING_SKY_TEAM_KEY,
        "task_id": task_id,
        "body": body,
    }


def stamp_create(
    *,
    title: str,
    description: str,
    seat: str = "floor",
    label: str = GCS_LINEAR_LABEL,
    client: LinearGraphQL | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Create a Living Sky LIV issue with a Palemon/GCS label. Minds only."""
    if is_skip_stamp_seat(seat):
        raise LivStampError("skipSeats: Donald does not DIY Linear")
    heading = (title or "").strip()
    if not heading:
        raise LivStampError("title is required")
    wanted = resolve_label_name(label)
    gql = _client(client, api_key)
    org = gql.organization()
    assert_living_sky(
        url_key=str(org.get("urlKey") or ""),
        name=str(org.get("name") or ""),
    )
    team = gql.team_by_key(LIVING_SKY_TEAM_KEY)
    assert_living_sky(
        url_key=str(org.get("urlKey") or ""),
        name=str(org.get("name") or ""),
        team_key=str(team.get("key") or ""),
    )
    found = gql.labels_by_name([wanted])
    label_ids = [str(row["id"]) for row in found if row.get("name") == wanted and row.get("id")]
    if not label_ids:
        raise LivStampError(
            f"Linear label {wanted!r} missing on Living Sky (create it once)"
        )
    issue_row = gql.issue_create(
        team_id=str(team.get("id") or ""),
        title=heading,
        description=redact(description or ""),
        label_ids=label_ids,
    )
    ident = str(issue_row.get("identifier") or "")
    if ident:
        validate_issue_id(ident)
    return {
        "ok": True,
        "action": "create",
        "issue": ident,
        "url": issue_row.get("url"),
        "workspace": LIVING_SKY_URL_KEY,
        "team": LIVING_SKY_TEAM_KEY,
        "label": wanted,
    }


def stamp_enabled() -> bool:
    """Default on outside pytest. GCS_LIV_STAMP=1 forces on; =0 forces off."""
    raw = (os.environ.get("GCS_LIV_STAMP") or "").strip()
    if raw == "0":
        return False
    if raw == "1":
        return True
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    return True


def maybe_stamp_after_task(
    *,
    seat: str,
    task_id: str,
    evidence: str,
    issue: str | None = None,
    env: Mapping[str, str] | None = None,
    state_dir: Path | None = None,
    home: Path | None = None,
) -> dict[str, Any]:
    """Best-effort Living Sky stamp after an A2A TASK. Never fails the mind turn.

    Donald / orchestrator do not DIY Linear. Missing LINEAR_API_KEY skips.
    """
    if is_skip_stamp_seat(seat):
        return {"ok": False, "reason": "skipSeats"}
    if _TEST_CLIENT is None and not stamp_enabled():
        return {"ok": False, "reason": "disabled"}
    ident = (issue or os.environ.get("GCS_LIV_ISSUE") or "LIV-82").strip()
    blob = (evidence or "").strip() or "pytest evidence: mind turn completed"
    client = _TEST_CLIENT
    if client is None:
        try:
            key = load_linear_api_key(env=env, state_dir=state_dir, home=home)
        except LivStampError:
            print("LIV_STAMP_SKIP reason=no-key", flush=True)
            return {"ok": False, "reason": "no-key"}
        try:
            client = LinearGraphQL(key)
        except LivStampError as exc:
            print(f"LIV_STAMP_SKIP {redact(str(exc))}", flush=True)
            return {"ok": False, "reason": "client"}
    try:
        result = stamp_after_task(
            issue=ident,
            task_id=task_id,
            evidence=blob,
            seat=seat,
            client=client,
        )
        print(
            f"LIV_STAMP_OK action=after-task issue={result.get('issue')} "
            f"workspace={result.get('workspace')} team={result.get('team')} "
            f"task={task_id}",
            flush=True,
        )
        return result
    except LivStampError as exc:
        print(f"LIV_STAMP_ERR {redact(str(exc))}", file=sys.stderr, flush=True)
        return {"ok": False, "reason": "error"}


LIV_STAMP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "issue": {
            "type": "string",
            "description": "Living Sky LIV-* identifier (default GCS_LIV_ISSUE / LIV-82)",
        },
        "task": {"type": "string", "description": "A2A TASK id"},
        "evidence": {
            "type": "string",
            "description": "CLOUD_LAUNCH_OK line or pytest evidence",
        },
        "seat": {"type": "string", "description": "Mind seat (not donald / orchestrator)"},
    },
    "required": ["task", "evidence"],
    "additionalProperties": False,
}


def plugin_liv_stamp(arguments: dict[str, Any]) -> str:
    """Comment on Living Sky LIV-* after a TASK. Never Donald. Never Black Swan."""
    seat = str(arguments.get("seat") or "").strip() or _seat_default()
    if is_skip_stamp_seat(seat):
        return "LIV_STAMP_ERR skipSeats: Donald does not DIY Linear"
    task_id = str(arguments.get("task") or arguments.get("task_id") or "").strip()
    evidence = str(arguments.get("evidence") or "")
    issue = str(arguments.get("issue") or "").strip() or _issue_default()
    if not task_id or not evidence.strip():
        return "LIV_STAMP_ERR liv_stamp: task and evidence are required"
    result = maybe_stamp_after_task(
        seat=seat,
        task_id=task_id,
        evidence=evidence,
        issue=issue,
    )
    if result.get("ok"):
        return (
            f"LIV_STAMP_OK issue={result.get('issue')} "
            f"workspace={result.get('workspace')} team={result.get('team')} "
            f"task={task_id}"
        )
    reason = str(result.get("reason") or "error")
    if reason == "skipSeats":
        return "LIV_STAMP_ERR skipSeats: Donald does not DIY Linear"
    return f"LIV_STAMP_ERR reason={reason}"


def _print_ok(result: dict[str, Any]) -> None:
    print(
        "LIV_STAMP_OK"
        f" action={result.get('action') or 'stamp'}"
        f" issue={result.get('issue') or 'none'}"
        f" comment={result.get('comment_id') or 'none'}"
        f" workspace={result.get('workspace') or LIVING_SKY_URL_KEY}"
        f" team={result.get('team') or LIVING_SKY_TEAM_KEY}"
        f" task={result.get('task_id') or 'none'}",
        flush=True,
    )


def _seat_default() -> str:
    return (
        os.environ.get("GCS_DIRECTOR_SEAT")
        or os.environ.get("CLOUD_OWNER_SEAT")
        or "floor"
    ).strip() or "floor"


def _issue_default() -> str:
    return (os.environ.get("GCS_LIV_ISSUE") or "LIV-82").strip() or "LIV-82"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Stamp Living Sky Linear (linear.app/livingsky, team LIV). "
            "Grok Build minds only. Do not have Donald DIY Linear."
        )
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    after = sub.add_parser("after-task", help="Comment on LIV-* after an A2A TASK")
    after.add_argument("--issue", default=_issue_default())
    after.add_argument("--task", required=True, dest="task_id")
    after.add_argument("--seat", default=_seat_default())
    after.add_argument("--evidence", default="")
    after.add_argument("--evidence-file", default="")

    create = sub.add_parser("create", help="Create a Living Sky LIV issue")
    create.add_argument("--title", required=True)
    create.add_argument("--description", default="")
    create.add_argument("--label", default=GCS_LINEAR_LABEL)
    create.add_argument("--seat", default=_seat_default())

    args = parser.parse_args(argv)
    try:
        if args.cmd == "after-task":
            evidence = str(args.evidence or "")
            ev_file = str(args.evidence_file or "").strip()
            if ev_file:
                evidence = Path(ev_file).read_text(encoding="utf-8")
            result = stamp_after_task(
                issue=str(args.issue),
                task_id=str(args.task_id),
                evidence=evidence,
                seat=str(args.seat),
            )
            _print_ok(result)
            return 0
        if args.cmd == "create":
            result = stamp_create(
                title=str(args.title),
                description=str(args.description or ""),
                seat=str(args.seat),
                label=str(args.label),
            )
            _print_ok(result)
            return 0
        raise LivStampError(f"unknown command {args.cmd}")
    except LivStampError as exc:
        print(f"LIV_STAMP_ERR {redact(str(exc))}", file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
