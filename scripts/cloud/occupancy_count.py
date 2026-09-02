#!/usr/bin/env python3
"""Occupancy counts from a paginated Agent.list / GET /v1/agents catalog.

Walks nextCursor beyond the API max of 100 (hive dump was 439). Counts
latest-run runStatus via GET /v1/agents/{id}/runs/{latestRunId}. Existence
ACTIVE/IDLE is not liveness. Fail-closed if a catalog page errors — never
fake running=0 from a partial list.

Distinct from leftover occupancy GCS #132 (listRuns concurrency/timeout).
Palemon Linear is Living Sky (LIV). Never prints API keys.
Never Grok Bot as Extra High occupancy (skip GCS_BOT_AGENT_ID).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
import list_catalog  # noqa: E402

FetchRun = Callable[[str, str], str]
MEMBERSHIP_NOT_LIVENESS = frozenset({"ACTIVE", "IDLE", ""})


class OccupancyError(RuntimeError):
    """Run probe failed; occupancy is unknown (fail closed)."""

    def __init__(self, message: str, reason: str = "err") -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class OccupancySummary:
    running: int
    leftover_active: int
    creating: int
    listed: int
    pages: int


def normalize_run_status(raw: Any) -> str:
    status = str(raw or "").strip()
    if not status or status.upper() == "NONE":
        return "none"
    return status.upper()


def normalize_agent_status(raw: Any) -> str:
    status = str(raw or "").strip()
    return status.upper() if status else ""


def classify_row(agent_status: str, run_status: str) -> str:
    run = normalize_run_status(run_status)
    if run == "RUNNING":
        return "running"
    if run == "CREATING":
        return "creating"
    membership = normalize_agent_status(agent_status)
    if membership in MEMBERSHIP_NOT_LIVENESS:
        return "leftover_active"
    return "other"


def format_occupancy_line(summary: OccupancySummary) -> str:
    return (
        f"CLOUD_OCCUPANCY running={summary.running} leftover_active={summary.leftover_active} "
        f"creating={summary.creating} listed={summary.listed} pages={summary.pages}"
    )


def format_occupancy_err(reason: str, message: str = "") -> str:
    extra = f" {message}" if message else ""
    return f"CLOUD_OCCUPANCY_ERR reason={reason}{extra}".rstrip()


def count_running(summary: OccupancySummary) -> int:
    """RUNNING latest-runs only. CREATING is separate (creating=)."""
    return summary.running


def _agent_id(raw: dict[str, Any]) -> str:
    return str(raw.get("id") or raw.get("agentId") or "").strip()


def _agent_status(raw: dict[str, Any]) -> str:
    return str(raw.get("status") or raw.get("agentStatus") or "")


def _latest_run_id(raw: dict[str, Any]) -> str:
    run_id = str(raw.get("latestRunId") or raw.get("latest_run_id") or "")
    if run_id:
        return run_id
    latest = raw.get("latestRun") or raw.get("latest_run")
    if isinstance(latest, dict):
        return str(latest.get("id") or latest.get("runId") or latest.get("run_id") or "")
    return ""


def occupancy_from_catalog(
    catalog: list_catalog.CatalogResult,
    fetch_run_status: FetchRun,
    *,
    bot_id: str = "",
) -> OccupancySummary:
    """Count occupancy from a complete paginated catalog.

    Callers must pass a catalog that already walked nextCursor. A page error
    must raise before this helper so we never print running=0 from leftovers.
    """
    bot = (bot_id or "").strip()
    running = leftover_active = creating = 0
    listed = 0
    for raw in catalog.items:
        if not isinstance(raw, dict):
            continue
        row = list_catalog.unwrap_entity(raw, "agent")
        if not isinstance(row, dict):
            row = raw
        agent_id = _agent_id(row)
        if not agent_id:
            continue
        if bot and agent_id == bot:
            continue
        listed += 1
        run_id = _latest_run_id(row)
        if run_id:
            run_status = normalize_run_status(fetch_run_status(agent_id, run_id))
        else:
            inline = row.get("runStatus") or row.get("run_status")
            run_status = normalize_run_status(inline)
        kind = classify_row(_agent_status(row), run_status)
        if kind == "running":
            running += 1
        elif kind == "creating":
            creating += 1
        elif kind == "leftover_active":
            leftover_active += 1
    return OccupancySummary(
        running=running,
        leftover_active=leftover_active,
        creating=creating,
        listed=listed,
        pages=catalog.pages,
    )


def _run_timeout() -> float:
    try:
        raw = float(os.environ.get("CLOUD_CURL_MAX_TIME") or "120")
    except ValueError:
        raw = 120.0
    return min(max(raw, 1.0), 15.0)


def _api_get(path: str, timeout: float) -> dict[str, Any] | None:
    """JSON object, or None on 404. OccupancyError on other failures."""
    base = (os.environ.get("CURSOR_API_BASE") or list_catalog.DEFAULT_API_BASE).rstrip("/")
    key = os.environ.get("CURSOR_API_KEY") or ""
    url = f"{base}{path}"
    token = base64.b64encode(f"{key}:".encode("utf-8")).decode("ascii")
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "Authorization": f"Basic {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        if err.code == 404:
            return None
        raise OccupancyError(f"http={err.code}", "err") from err
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError) as err:
        raise OccupancyError("run probe failed", "err") from err
    if not isinstance(payload, dict):
        raise OccupancyError("unexpected run payload", "err")
    return payload


def fetch_run_status(agent_id: str, run_id: str) -> str:
    if not agent_id or not run_id:
        return "none"
    payload = _api_get(f"/v1/agents/{agent_id}/runs/{run_id}", _run_timeout())
    if payload is None:
        return "none"
    run = list_catalog.unwrap_entity(payload, "run")
    if not isinstance(run, dict):
        return "none"
    return str(run.get("status") or "")


def occupancy_from_api(*, bot_id: str = "") -> OccupancySummary:
    catalog = list_catalog.fetch_catalog_from_api()
    return occupancy_from_catalog(catalog, fetch_run_status, bot_id=bot_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Print CLOUD_OCCUPANCY from a paginated GET /v1/agents catalog "
            "(nextCursor beyond limit=100)."
        ),
    )
    parser.parse_args(argv)
    bot_id = (os.environ.get("GCS_BOT_AGENT_ID") or "").strip()
    try:
        summary = occupancy_from_api(bot_id=bot_id)
    except list_catalog.CatalogError as err:
        print(format_occupancy_err(err.reason, str(err)), file=sys.stderr)
        return 1
    except OccupancyError as err:
        print(format_occupancy_err(err.reason, str(err)), file=sys.stderr)
        return 1
    print(format_occupancy_line(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
