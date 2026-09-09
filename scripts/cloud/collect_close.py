#!/usr/bin/env python3
"""Director collect: prUrl URL vs none. none → CLOSE.

``scripts/cloud/result-cloud-agent.sh`` / SDK ``collect.ts`` JSON is the
Director evidence path. When Extra High ``runStatus=FINISHED`` and
``prUrl`` is null/empty/none, Directors CLOSE. No MERGE_REQUEST. No twin
Extra High. Leftover of a merged shard is CLOSE.

Live ``runStatus=RUNNING`` with prUrl none is not CLOSE (the grunt has
not opened a PR yet).

Distinct from waiter-owner-seat-tandem (GCS #172, already RUNNING) and
occupancy remint (#125 / #132 / #154). Do not remint those. Do not clone
LIV-41/67/85/82. Do not vendor Hermes. Do not merge GCS #26/#28. Do not
land palemon leftover #165/#167. Never Bot CloudAgent. Living Sky Linear
(LIV). Never print CURSOR_API_KEY / LINEAR_API_KEY.
"""
from __future__ import annotations

from typing import Any

CLOSE = "CLOSE"
NONE_TOKENS = frozenset({"none", "null", "nil"})
CLOSE_STATUSES = frozenset({"FINISHED"})


def pr_url_or_none(value: object) -> str | None:
    """Return a PR URL, or None when the collect field is none/empty."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.lower() in NONE_TOKENS:
        return None
    if "://" not in text and not text.startswith("github.com/"):
        return None
    return text


def _run_status(payload: dict[str, Any]) -> str:
    raw = str(payload.get("runStatus") or payload.get("status") or "").strip().upper()
    if raw == "CANCELED":
        return "CANCELLED"
    return raw


def director_action(payload: dict[str, Any]) -> str | None:
    """CLOSE when FINISHED collect JSON has prUrl none. URL is not CLOSE."""
    pr = pr_url_or_none(payload.get("prUrl"))
    if pr is None:
        pr = pr_url_or_none(payload.get("pr_url"))
    if pr is not None:
        return None
    if _run_status(payload) in CLOSE_STATUSES:
        return CLOSE
    return None


def attach_director_action(payload: dict[str, Any]) -> dict[str, Any]:
    """Stamp directorAction and normalize prUrl to a URL or None."""
    if "prUrl" in payload or "pr_url" in payload:
        payload["prUrl"] = pr_url_or_none(payload.get("prUrl", payload.get("pr_url")))
    else:
        payload["prUrl"] = None
    payload["directorAction"] = director_action(payload)
    return payload
