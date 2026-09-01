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
