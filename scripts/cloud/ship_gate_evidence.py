#!/usr/bin/env python3
"""LIV-94: empty GitHub checks are not ship-gate evidence.

MERGEABLE (`mergeable_state=clean`) with `check_runs=[]` is not proof that
`.venv/bin/pytest -q` and `python3 scripts/secret_scan.py` ran. GCS #41,
#47, and #27 showed that shape. GCS #62 already added the pull_request
Actions job named "pytest -q and secret_scan"; do not remint it.

Never prints GH_TOKEN / GITHUB_TOKEN / CURSOR_API_KEY.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

_GITHUB_PULL_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/([^/]+)/([^/]+)/pulls?/(\d+)(?:[/?#].*)?$",
    re.IGNORECASE,
)

SHIP_GATE_EXAMPLE: dict[str, str] = {
    "on": "pull_request",
    "repo": "atebites-hub/grok-cloud-studio",
    "pytest": ".venv/bin/pytest -q",
    "secret_scan": "python3 scripts/secret_scan.py",
    "check_name": "pytest -q and secret_scan",
}


@dataclass(frozen=True)
class ShipGateSnapshot:
    """One-shot GitHub PR check snapshot. MERGEABLE is not a substitute."""

    pr_url: str | None
    mergeable_state: str | None
    head_sha: str | None
    check_runs: tuple[dict[str, Any], ...]
    statuses_total: int

    @property
    def empty_checks(self) -> bool:
        return len(self.check_runs) == 0 and int(self.statuses_total or 0) == 0

    @property
    def ship_gate_ok(self) -> bool:
        return any(is_ship_gate_check(run) for run in self.check_runs)


def parse_github_pull_url(pr_url: object) -> tuple[str, str, int] | None:
    """Parse https://github.com/<owner>/<repo>/pull/<n> (also /pulls/)."""
    if not isinstance(pr_url, str):
        return None
    match = _GITHUB_PULL_RE.match(pr_url.strip())
    if not match:
        return None
    return match.group(1), match.group(2), int(match.group(3))


def is_ship_gate_check(run: dict[str, Any]) -> bool:
    """True only for a successful check named like pytest + secret_scan."""
    name = str(run.get("name") or "").lower()
    conclusion = str(run.get("conclusion") or "").lower()
    if conclusion != "success":
        return False
    return "pytest" in name and "secret_scan" in name


def is_ship_gate_evidence(snapshot: ShipGateSnapshot) -> bool:
    """Empty GitHub checks are not evidence. MERGEABLE does not override."""
    if snapshot.empty_checks:
        return False
    return snapshot.ship_gate_ok


def _github_get(path: str) -> dict[str, Any] | None:
    base = (os.environ.get("GITHUB_API_BASE") or "https://api.github.com").rstrip("/")
    url = f"{base}{path}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "grok-cloud-studio-waiter",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read().decode("utf-8")
        body = json.loads(raw)
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(body, dict):
        return None
    return body


def github_pr_ship_gate(pr_url: object) -> ShipGateSnapshot | None:
    """GET pull + check-runs + combined status. None if not a GitHub pull.

    One-shot. Do not reuse Extra High get_agent_run 429 backoff.
    Fail closed: missing check-runs is empty checks, not a pass.
    """
    parsed = parse_github_pull_url(pr_url)
    if parsed is None:
        return None
    owner, repo, number = parsed
    pull = _github_get(f"/repos/{owner}/{repo}/pulls/{number}")
    if pull is None:
        return None
    head = pull.get("head") if isinstance(pull.get("head"), dict) else {}
    head_sha = str(head.get("sha") or "") or None
    mergeable_state = pull.get("mergeable_state")
    mergeable = str(mergeable_state) if isinstance(mergeable_state, str) else None
    runs: tuple[dict[str, Any], ...] = ()
    statuses_total = 0
    if head_sha:
        checks = _github_get(f"/repos/{owner}/{repo}/commits/{head_sha}/check-runs")
        if isinstance(checks, dict):
            raw_runs = checks.get("check_runs") or []
            if isinstance(raw_runs, list):
                runs = tuple(r for r in raw_runs if isinstance(r, dict))
        combined = _github_get(f"/repos/{owner}/{repo}/commits/{head_sha}/status")
        if isinstance(combined, dict):
            try:
                statuses_total = int(combined.get("total_count") or 0)
            except (TypeError, ValueError):
                statuses_total = 0
    return ShipGateSnapshot(
        pr_url=str(pr_url) if isinstance(pr_url, str) else None,
        mergeable_state=mergeable,
        head_sha=head_sha,
        check_runs=runs,
        statuses_total=statuses_total,
    )


def _flag(payload: dict[str, Any], *keys: str) -> object:
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return None


def payload_ship_gate_ok(payload: dict[str, Any]) -> bool:
    value = _flag(payload, "shipGateOk", "ship_gate_ok")
    if value is True:
        return True
    if isinstance(value, str) and value.strip().lower() in {"true", "1", "yes", "ok"}:
        return True
    return False


def payload_empty_checks(payload: dict[str, Any]) -> bool:
    value = _flag(payload, "emptyChecks", "empty_checks")
    if value is True:
        return True
    if isinstance(value, str) and value.strip().lower() in {"true", "1", "yes"}:
        return True
    runs = _flag(payload, "checkRuns", "check_runs")
    if runs == 0 or runs == []:
        return True
    return False


def payload_has_ship_gate_flags(payload: dict[str, Any]) -> bool:
    return (
        _flag(payload, "shipGateOk", "ship_gate_ok") is not None
        or _flag(payload, "emptyChecks", "empty_checks") is not None
        or _flag(payload, "checkRuns", "check_runs") is not None
    )


def should_hold_empty_checks(payload: dict[str, Any]) -> bool:
    """GitHub PR without a successful ship-gate check: HOLD, not MERGE_REQUEST."""
    if parse_github_pull_url(payload.get("prUrl") or payload.get("pr_url")) is None:
        return False
    if payload_ship_gate_ok(payload):
        return False
    return True


def resolve_ship_gate(payload: dict[str, Any]) -> dict[str, Any]:
    """Honor waiter-supplied flags; otherwise look up GitHub when prUrl is a pull."""
    if payload_has_ship_gate_flags(payload):
        return payload
    snap = github_pr_ship_gate(payload.get("prUrl") or payload.get("pr_url"))
    if snap is None:
        if parse_github_pull_url(payload.get("prUrl") or payload.get("pr_url")) is not None:
            payload["emptyChecks"] = True
            payload["shipGateOk"] = False
            payload["checkRuns"] = 0
        return payload
    payload["emptyChecks"] = snap.empty_checks
    payload["shipGateOk"] = snap.ship_gate_ok
    payload["checkRuns"] = len(snap.check_runs)
    if snap.mergeable_state is not None:
        payload["mergeableState"] = snap.mergeable_state
    return payload
