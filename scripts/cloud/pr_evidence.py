#!/usr/bin/env python3
"""MERGE_REQUEST / QA evidence: pasted pytest -q + secret_scan.

Empty GitHub leftover-green (MERGEABLE + check_runs=[]) is not a ship-gate.
A GitHub check named "pytest -q and secret_scan" is not a substitute for
paste (distinct from leftover LIV-94 #105/#88/#92). Do not rebase those
PRs. Do not twin beat1740 workflow files.

Never prints GH_TOKEN / GITHUB_TOKEN / CURSOR_API_KEY.
Never Bot CloudAgent. Palemon Linear is Living Sky (LIV), never Black Swan.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

_GITHUB_PULL_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/([^/]+)/([^/]+)/pulls?/(\d+)(?:[/?#].*)?$",
    re.IGNORECASE,
)
_PASSED_RE = re.compile(r"(?m)(?<![\d])([1-9][0-9]*) passed\b")
_FAILED_RE = re.compile(r"(?m)(?<![\d])([1-9][0-9]*) failed\b")
_BLOB_KEYS = (
    "result",
    "summary",
    "notes",
    "evidence",
    "paste",
    "body",
    "mergeRequest",
    "merge_request",
    "text",
    "prBody",
    "pr_body",
)
_CONFLICTING = frozenset({"dirty", "conflicting", "blocked"})


def parse_github_pull_url(pr_url: object) -> tuple[str, str, int] | None:
    """Parse https://github.com/<owner>/<repo>/pull/<n> (also /pulls/)."""
    if not isinstance(pr_url, str):
        return None
    match = _GITHUB_PULL_RE.match(pr_url.strip())
    if not match:
        return None
    return match.group(1), match.group(2), int(match.group(3))


def _as_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return str(value)


def evidence_text(payload: dict[str, Any] | str | None) -> str:
    """Concatenate Director/QA paste surfaces. GitHub leftover-green is not a paste."""
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload
    parts: list[str] = []
    for key in _BLOB_KEYS:
        if key in payload and payload[key] is not None:
            parts.append(_as_text(payload[key]))
    return "\n".join(p for p in parts if p)


def has_pasted_pytest(text: str) -> bool:
    """True when pytest -q paste shows N passed (N>=1) and no N failed (N>=1)."""
    if not isinstance(text, str) or not text.strip():
        return False
    if _FAILED_RE.search(text):
        return False
    return _PASSED_RE.search(text) is not None


def has_pasted_secret_scan(text: str) -> bool:
    return isinstance(text, str) and "secret_scan=clean" in text


def has_pasted_ship_gate(text: str) -> bool:
    """Pasted `.venv/bin/pytest -q` N passed AND secret_scan=clean."""
    return has_pasted_pytest(text) and has_pasted_secret_scan(text)


def _flag(payload: dict[str, Any], *keys: str) -> object:
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return None


def _mergeable_state(payload: dict[str, Any]) -> str:
    raw = _flag(payload, "mergeableState", "mergeable_state")
    if isinstance(raw, str):
        return raw.strip().lower()
    return ""


def is_empty_github_leftover_green(payload: dict[str, Any]) -> bool:
    """MERGEABLE / emptyChecks / check_runs=[] on a GitHub pull is leftover-green."""
    pr = payload.get("prUrl") or payload.get("pr_url")
    if parse_github_pull_url(pr) is None:
        return False
    empty = _flag(payload, "emptyChecks", "empty_checks")
    if empty is True:
        return True
    if isinstance(empty, str) and empty.strip().lower() in {"true", "1", "yes"}:
        return True
    runs = _flag(payload, "checkRuns", "check_runs")
    if runs == 0 or runs == []:
        return True
    return False


def may_squash(payload: dict[str, Any]) -> bool:
    """QA may squash-merge only with paste and a non-CONFLICTING GitHub state."""
    if _mergeable_state(payload) in _CONFLICTING:
        return False
    return has_pasted_ship_gate(evidence_text(payload))


def merge_request_ready(payload: dict[str, Any]) -> bool:
    """True only when pasted pytest -q + secret_scan exist and the PR is not CONFLICTING."""
    return may_squash(payload)


def should_hold_merge_request(payload: dict[str, Any]) -> bool:
    """GitHub pull without pasted ship-gate: HOLD, not QA MERGE_REQUEST."""
    pr = payload.get("prUrl") or payload.get("pr_url")
    if parse_github_pull_url(pr) is None:
        return False
    return not merge_request_ready(payload)


def hold_reason(payload: dict[str, Any]) -> str:
    if _mergeable_state(payload) in _CONFLICTING:
        return "conflicting"
    if not has_pasted_ship_gate(evidence_text(payload)):
        if is_empty_github_leftover_green(payload):
            return "leftover-green"
        return "no-paste"
    return "ok"


def judge(payload: dict[str, Any]) -> tuple[int, str]:
    """Return (exit_code, one-line verdict). Never dumps secrets."""
    if merge_request_ready(payload):
        return 0, "PR_EVIDENCE_OK"
    reason = hold_reason(payload)
    return 1, f"PR_EVIDENCE_HOLD reason={reason}"


def _load_payload(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {"result": raw}
    if isinstance(data, dict):
        return data
    return {"result": raw}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Judge MERGE_REQUEST paste evidence (not empty GitHub leftover-green)."
    )
    parser.add_argument("cmd", nargs="?", default="judge", choices=["judge"])
    parser.add_argument("--file", default="", help="JSON or text file (default: stdin)")
    args = parser.parse_args(argv)
    if args.file:
        raw = open(args.file, encoding="utf-8").read()
    else:
        raw = sys.stdin.read()
    payload = _load_payload(raw)
    code, line = judge(payload)
    print(line)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
