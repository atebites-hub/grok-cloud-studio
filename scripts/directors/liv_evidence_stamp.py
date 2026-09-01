#!/usr/bin/env python3
"""Stamp Living Sky Linear (LIV-*) only after real hive evidence.

Evidence is a successful mind turn (runner exit 0, offset already advanced)
or a real Extra High launch (CLOUD_LAUNCH_OK + bc-id). Hub
TASK_STATE_COMPLETED / A2A ACK is a receipt (LIV-85), never a stamp trigger.

LINEAR_API_KEY may be unset: fail closed (LINEAR_STAMP_FAIL reason=no-key).
Never invent a comment id. Never write a success artifact for a stamp that
did not happen. Living Sky team ``LIV`` / linear.app/livingsky only — never
Black Swan. skipSeats (donald, orchestrator) do not stamp. Stdlib only.
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
from typing import Any, Callable

_LIB_DIR = Path(__file__).resolve().parents[1] / "a2a"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
from lib import canonical_seat, skip_seats  # noqa: E402

ROOT = Path(os.environ.get("GCS_ROOT", Path(__file__).resolve().parents[2]))

LINEAR_GRAPHQL_URL = "https://api.linear.app/graphql"
LIVING_SKY_TEAM_KEY = "LIV"
LIVING_SKY_HOST_NEEDLE = "livingsky"

LIV_ID_RE = re.compile(r"\bLIV-\d+\b")
LIV_NAME_RE = re.compile(r"(?i)\bliv-?(\d+)\b")
BSM_ID_RE = re.compile(r"\bBSM-\d+\b")
BLACK_SWAN_RE = re.compile(r"black\s*swan", re.I)
_SECRET_ASSIGN_RE = re.compile(
    r"(?i)\b(LINEAR_API_KEY|CURSOR_API_KEY|GCS_WEBHOOK_SECRET|"
    r"GCS_LINEAR_API_KEY|Authorization|Bearer|api[_-]?key)\s*[=:]\s*\S+"
)
_LIN_API_RE = re.compile(r"\blin_api_[A-Za-z0-9_\-]{8,}\b")

HUB_RECEIPT_KINDS = frozenset(
    {
        "hub_receipt",
        "task_state_completed",
        "a2a_ack",
        "a2a_ack_receipt",
        "receipt",
    }
)
EVIDENCE_KINDS = frozenset({"mind_turn", "cloud_launch"})
BOT_SKIP = frozenset({"donald", "orchestrator"})

GraphQLFn = Callable[[str, dict[str, Any], dict[str, str]], dict[str, Any]]

ISSUE_QUERY = """
query EvidenceIssue($id: String!) {
  issue(id: $id) {
    id
    identifier
    title
    url
    team { key name }
  }
}
""".strip()

COMMENT_MUTATION = """
mutation EvidenceComment($issueId: String!, $body: String!) {
  commentCreate(input: { issueId: $issueId, body: $body }) {
    success
    comment { id url }
  }
}
""".strip()


def _normalize_kind(kind: str) -> str:
    return re.sub(r"[\s-]+", "_", (kind or "").strip().lower())


def redact(text: str) -> str:
    """Strip credential assignments and lin_api tokens. Never print secrets."""
    if not text:
        return text
    blob = _SECRET_ASSIGN_RE.sub(lambda m: f"{m.group(1)}=[redacted]", text)
    return _LIN_API_RE.sub("lin_api_[redacted]", blob)


def extract_liv_identifiers(text: str) -> list[str]:
    """Canonical ``LIV-N`` identifiers only (case-sensitive Living Sky ids)."""
    if not text:
        return []
    seen: dict[str, None] = {}
    for match in LIV_ID_RE.finditer(text):
        seen.setdefault(match.group(0), None)
    return list(seen)


def extract_liv_from_name(name: str) -> list[str]:
    """Extra High ``--name`` tokens like gcs-liv82-… fold onto LIV-82."""
    if not name:
        return []
    seen: dict[str, None] = {}
    for match in LIV_NAME_RE.finditer(name):
        seen.setdefault(f"LIV-{int(match.group(1))}", None)
    return list(seen)


def collect_identifiers(*, text: str = "", name: str = "", turn: str = "") -> list[str]:
    seen: dict[str, None] = {}
    for ident in (
        *extract_liv_identifiers(text),
        *extract_liv_identifiers(turn),
        *extract_liv_from_name(name),
        *extract_liv_from_name(text),
    ):
        seen.setdefault(ident, None)
    return list(seen)


def linear_api_key() -> str:
    for name in ("LINEAR_API_KEY", "GCS_LINEAR_API_KEY"):
        raw = (os.environ.get(name) or "").strip()
        if raw:
            return raw
    return ""


def configured_team_key() -> str:
    raw = (os.environ.get("GCS_LINEAR_TEAM_KEY") or LIVING_SKY_TEAM_KEY).strip().upper()
    return raw or LIVING_SKY_TEAM_KEY


def _is_skip_seat(seat: str) -> bool:
    key = canonical_seat(seat, ROOT)
    skipped = skip_seats(ROOT)
    low = seat.strip().lower()
    return key in skipped or low in skipped or key in BOT_SKIP or low in BOT_SKIP


def _log(line: str) -> None:
    print(redact(line), flush=True)


def _result(
    *,
    ok: bool,
    posted: bool,
    reason: str,
    identifiers: list[str] | None = None,
    comment_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "posted": posted,
        "reason": reason,
        "identifiers": list(identifiers or []),
        "comment_ids": list(comment_ids or []),
    }


def _auth_headers(key: str) -> dict[str, str]:
    token = key.strip()
    if token.lower().startswith("bearer "):
        value = token
    else:
        value = token
    return {
        "Authorization": value,
        "Content-Type": "application/json",
    }


def post_graphql(
    query: str, variables: dict[str, Any], headers: dict[str, str]
) -> dict[str, Any]:
    url = (os.environ.get("GCS_LINEAR_GRAPHQL_URL") or LINEAR_GRAPHQL_URL).strip()
    if not url:
        url = LINEAR_GRAPHQL_URL
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"linear http {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("linear http") from exc
    try:
        body = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("linear graphql") from exc
    if body.get("errors"):
        raise RuntimeError("linear graphql")
    data = body.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("linear graphql")
    return data


def _living_sky_issue(issue: dict[str, Any] | None) -> str | None:
    """Return a refuse reason, or None if the issue is Living Sky LIV."""
    if not issue:
        return "no-issue"
    team = issue.get("team") if isinstance(issue.get("team"), dict) else {}
    key = str(team.get("key") or "").strip().upper()
    name = str(team.get("name") or "")
    url = str(issue.get("url") or "")
    if key != LIVING_SKY_TEAM_KEY:
        return "not-living-sky"
    if BLACK_SWAN_RE.search(name):
        return "black-swan"
    if url and LIVING_SKY_HOST_NEEDLE not in url.lower():
        return "not-living-sky"
    return None


def _comment_body(
    *,
    kind: str,
    seat: str,
    identifiers: list[str],
    text: str,
    turn: str,
    task_id: str,
    bc_id: str,
    name: str,
) -> str:
    excerpt = redact(" ".join((text or "").split())[:400])
    lines = [
        "Hive stamp (Living Sky). Evidence only — not a hub TASK_STATE_COMPLETED receipt.",
        f"kind={kind}",
        f"seat={seat}",
        f"liv={','.join(identifiers)}",
    ]
    if task_id:
        lines.append(f"task={task_id}")
    if bc_id:
        lines.append(f"bc-id={bc_id}")
    if name:
        lines.append(f"name={redact(name)[:120]}")
    if turn:
        lines.append(f"turn={redact(' '.join(turn.split())[:240])}")
    if excerpt:
        lines.append(f"notes={excerpt}")
    return "\n".join(lines)


def stamp_after_evidence(
    *,
    kind: str,
    seat: str,
    text: str = "",
    turn: str = "",
    name: str = "",
    task_id: str = "",
    bc_id: str = "",
    graphql: GraphQLFn | None = None,
) -> dict[str, Any]:
    """Post a Living Sky comment when *kind* is real evidence.

    Never posts on hub receipts. Missing LINEAR_API_KEY fails closed after a
    LIV-* identifier is present — no fake comment ids.
    """
    seat_key = canonical_seat(seat or "floor", ROOT)
    norm = _normalize_kind(kind)
    ident_text = "\n".join(part for part in (text, turn, name) if part)

    if norm in HUB_RECEIPT_KINDS:
        _log(f"LINEAR_STAMP_SKIP seat={seat_key} reason=hub-receipt")
        return _result(ok=False, posted=False, reason="hub-receipt")

    if norm not in EVIDENCE_KINDS:
        _log(f"LINEAR_STAMP_SKIP seat={seat_key} reason=not-evidence kind={norm}")
        return _result(ok=False, posted=False, reason="not-evidence")

    if _is_skip_seat(seat_key) or _is_skip_seat(seat):
        _log(f"LINEAR_STAMP_SKIP seat={seat_key} reason=skipSeats")
        return _result(ok=False, posted=False, reason="skipSeats")

    disable = (os.environ.get("GCS_LINEAR_STAMP") or "").strip().lower()
    if disable in {"0", "false", "no", "off"}:
        _log(f"LINEAR_STAMP_SKIP seat={seat_key} reason=disabled")
        return _result(ok=False, posted=False, reason="disabled")

    team_want = configured_team_key()
    if team_want != LIVING_SKY_TEAM_KEY or BLACK_SWAN_RE.search(team_want):
        _log(f"LINEAR_STAMP_FAIL seat={seat_key} reason=black-swan")
        return _result(ok=False, posted=False, reason="black-swan")

    identifiers = collect_identifiers(text=text, name=name, turn=turn)
    if not identifiers:
        if BSM_ID_RE.search(ident_text) or BLACK_SWAN_RE.search(ident_text):
            _log(f"LINEAR_STAMP_FAIL seat={seat_key} reason=black-swan")
            return _result(ok=False, posted=False, reason="black-swan")
        _log(f"LINEAR_STAMP_SKIP seat={seat_key} reason=no-issue")
        return _result(ok=False, posted=False, reason="no-issue")

    key = linear_api_key()
    if not key:
        _log(f"LINEAR_STAMP_FAIL seat={seat_key} reason=no-key")
        return _result(
            ok=False, posted=False, reason="no-key", identifiers=identifiers
        )

    poster = graphql if graphql is not None else post_graphql
    headers = _auth_headers(key)
    comment_ids: list[str] = []
    body = _comment_body(
        kind=norm.replace("_", "-"),
        seat=seat_key,
        identifiers=identifiers,
        text=text,
        turn=turn,
        task_id=task_id,
        bc_id=bc_id,
        name=name,
    )

    try:
        for ident in identifiers:
            looked = poster(ISSUE_QUERY, {"id": ident}, headers)
            issue = looked.get("issue") if isinstance(looked, dict) else None
            if not isinstance(issue, dict):
                _log(f"LINEAR_STAMP_FAIL seat={seat_key} reason=no-issue liv={ident}")
                return _result(
                    ok=False,
                    posted=False,
                    reason="no-issue",
                    identifiers=identifiers,
                )
            refuse = _living_sky_issue(issue)
            if refuse:
                _log(f"LINEAR_STAMP_FAIL seat={seat_key} reason={refuse} liv={ident}")
                return _result(
                    ok=False,
                    posted=False,
                    reason=refuse,
                    identifiers=identifiers,
                )
            issue_uuid = str(issue.get("id") or "").strip()
            if not issue_uuid:
                _log(f"LINEAR_STAMP_FAIL seat={seat_key} reason=no-issue liv={ident}")
                return _result(
                    ok=False,
                    posted=False,
                    reason="no-issue",
                    identifiers=identifiers,
                )
            created = poster(
                COMMENT_MUTATION,
                {"issueId": issue_uuid, "body": body},
                headers,
            )
            node = created.get("commentCreate") if isinstance(created, dict) else None
            if not isinstance(node, dict) or not node.get("success"):
                _log(f"LINEAR_STAMP_FAIL seat={seat_key} reason=graphql liv={ident}")
                return _result(
                    ok=False,
                    posted=False,
                    reason="graphql",
                    identifiers=identifiers,
                )
            comment = node.get("comment") if isinstance(node.get("comment"), dict) else {}
            cid = str(comment.get("id") or "").strip()
            if not cid:
                _log(f"LINEAR_STAMP_FAIL seat={seat_key} reason=graphql liv={ident}")
                return _result(
                    ok=False,
                    posted=False,
                    reason="graphql",
                    identifiers=identifiers,
                )
            comment_ids.append(cid)
    except RuntimeError as exc:
        why = str(exc)
        reason = "http" if "http" in why else "graphql"
        _log(f"LINEAR_STAMP_FAIL seat={seat_key} reason={reason}")
        return _result(
            ok=False, posted=False, reason=reason, identifiers=identifiers
        )
    except Exception:
        _log(f"LINEAR_STAMP_FAIL seat={seat_key} reason=graphql")
        return _result(
            ok=False, posted=False, reason="graphql", identifiers=identifiers
        )

    _log(
        f"LINEAR_STAMP_OK seat={seat_key} kind={norm.replace('_', '-')} "
        f"liv={','.join(identifiers)}"
    )
    return _result(
        ok=True,
        posted=True,
        reason="ok",
        identifiers=identifiers,
        comment_ids=comment_ids,
    )


def after_mind_turn(
    *,
    seat: str,
    mail: str,
    turn: str = "",
    task_id: str = "",
    graphql: GraphQLFn | None = None,
) -> dict[str, Any]:
    return stamp_after_evidence(
        kind="mind-turn",
        seat=seat,
        text=mail,
        turn=turn,
        task_id=task_id,
        graphql=graphql,
    )


def after_cloud_launch(
    *,
    seat: str,
    bc_id: str,
    name: str = "",
    prompt: str = "",
    graphql: GraphQLFn | None = None,
) -> dict[str, Any]:
    return stamp_after_evidence(
        kind="cloud-launch",
        seat=seat,
        text=prompt,
        name=name,
        bc_id=bc_id,
        graphql=graphql,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Stamp Living Sky LIV-* after mind-turn or cloud-launch evidence"
    )
    parser.add_argument("--kind", required=True, help="mind-turn | cloud-launch | hub-receipt")
    parser.add_argument("--seat", default="floor")
    parser.add_argument("--text", default="")
    parser.add_argument("--turn", default="")
    parser.add_argument("--name", default="")
    parser.add_argument("--task-id", default="")
    parser.add_argument("--bc-id", default="")
    args = parser.parse_args(argv)
    result = stamp_after_evidence(
        kind=args.kind,
        seat=args.seat,
        text=args.text,
        turn=args.turn,
        name=args.name,
        task_id=args.task_id,
        bc_id=args.bc_id,
    )
    if result.get("posted"):
        return 0
    if result.get("reason") in {"no-issue", "skipSeats", "disabled"}:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
