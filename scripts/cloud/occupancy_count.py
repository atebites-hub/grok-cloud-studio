#!/usr/bin/env python3
"""Occupancy counts from a paginated Agent.list / GET /v1/agents catalog.

Walks nextCursor beyond the API max of 100 (hive dump was 439). Counts
latest-run runStatus via listRuns (GET /v1/agents/{id}/runs collection);
CREATING maps as RUNNING toward floor 8. Leftover ACTIVE+FINISHED is not
a worker. Split Palemon vs GCS per bound repo (palemon= gcs= cap=
palemon_must= gcs_must=). Fail-closed if a catalog page or listRuns
errors — never fake running=0 from a partial list.

Distinct from leftover occupancy GCS #132 (listRuns concurrency/timeout).
Distinct from #142 catalog nextCursor paginate. Palemon Linear is Living
Sky (LIV). Never prints API keys. Never Grok Bot as Extra High occupancy
(skip GCS_BOT_AGENT_ID).
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
import latest_run  # noqa: E402
import list_catalog  # noqa: E402

FetchRun = Callable[[str, str], str]
FetchRuns = Callable[[str], list[dict[str, Any]]]
MEMBERSHIP_NOT_LIVENESS = frozenset({"ACTIVE", "IDLE", ""})
DEFAULT_FLOOR = 8
STUDIO_REPO_NAME = "grok-cloud-studio"
GAME_REPO_NAME = "pale" + "mon"


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
    palemon: int = 0
    gcs: int = 0
    cap: int = DEFAULT_FLOOR
    palemon_must: int = 1
    gcs_must: int = 1


def floor_cap(raw: str | None = None) -> int:
    text = (raw if raw is not None else os.environ.get("GCS_CLOUD_MIN_RUNNING") or "").strip()
    if not text:
        return DEFAULT_FLOOR
    try:
        value = int(text)
    except ValueError:
        return DEFAULT_FLOOR
    return value if value > 0 else DEFAULT_FLOOR


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
        f"creating={summary.creating} listed={summary.listed} pages={summary.pages} "
        f"palemon={summary.palemon} gcs={summary.gcs} cap={summary.cap} "
        f"palemon_must={summary.palemon_must} gcs_must={summary.gcs_must}"
    )


def format_occupancy_err(reason: str, message: str = "") -> str:
    extra = f" {message}" if message else ""
    return f"CLOUD_OCCUPANCY_ERR reason={reason}{extra}".rstrip()


def count_running(summary: OccupancySummary) -> int:
    """In-flight latest-runs. CREATING maps as RUNNING toward the floor."""
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


def _norm_repo(url: str) -> str:
    text = (url or "").strip().lower()
    if text.startswith("git@github.com:"):
        text = "https://github.com/" + text.split(":", 1)[1]
    if text.startswith("github.com/"):
        text = "https://" + text
    if text.endswith(".git"):
        text = text[:-4]
    return text.rstrip("/")


def agent_repo_urls(item: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    repo = item.get("repo")
    if isinstance(repo, str) and repo.strip():
        urls.append(repo.strip())
    repos = item.get("repos") or item.get("repositories") or []
    if isinstance(repos, list):
        for entry in repos:
            if isinstance(entry, str) and entry.strip():
                urls.append(entry.strip())
            elif isinstance(entry, dict):
                found = str(entry.get("url") or entry.get("repository") or "").strip()
                if found:
                    urls.append(found)
    source = item.get("source")
    if isinstance(source, dict):
        found = str(source.get("repository") or source.get("url") or "").strip()
        if found:
            urls.append(found)
    return urls


def run_repo_urls(run: dict[str, Any] | None) -> list[str]:
    if not isinstance(run, dict):
        return []
    git = run.get("git")
    if not isinstance(git, dict):
        return []
    branches = git.get("branches") or []
    if not isinstance(branches, list):
        return []
    urls: list[str] = []
    for branch in branches:
        if not isinstance(branch, dict):
            continue
        found = str(branch.get("repoUrl") or branch.get("url") or "").strip()
        if found:
            urls.append(found)
    return urls


def floor_kind(urls: list[str]) -> str:
    """Bound-repo floor: Palemon game vs grok-cloud-studio. Basename only."""
    for url in urls:
        name = _norm_repo(url).rsplit("/", 1)[-1]
        if name == STUDIO_REPO_NAME:
            return "gcs"
        if name == GAME_REPO_NAME:
            return "palemon"
    return "other"


def occupancy_from_catalog(
    catalog: list_catalog.CatalogResult,
    fetch_run_status: FetchRun | None = None,
    *,
    fetch_runs: FetchRuns | None = None,
    bot_id: str = "",
    cap: int | None = None,
) -> OccupancySummary:
    """Count occupancy from a complete paginated catalog.

    When fetch_runs is set, latest runStatus comes from listRuns (collection),
    not a stale catalog latestRunId. Callers must pass a catalog that already
    walked nextCursor. A page error must raise before this helper so we never
    print running=0 from leftovers.
    """
    bot = (bot_id or "").strip()
    limit = floor_cap() if cap is None else cap
    running = leftover_active = creating = 0
    palemon = gcs = 0
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
        run: dict[str, Any] | None = None
        if fetch_runs is not None:
            runs = fetch_runs(agent_id)
            run = latest_run.pick_latest_run(runs)
            run_status = normalize_run_status(latest_run.run_status(run) if run else "none")
        elif fetch_run_status is not None:
            run_id = _latest_run_id(row)
            if run_id:
                run_status = normalize_run_status(fetch_run_status(agent_id, run_id))
            else:
                inline = row.get("runStatus") or row.get("run_status")
                run_status = normalize_run_status(inline)
        else:
            inline = row.get("runStatus") or row.get("run_status")
            run_status = normalize_run_status(inline)
        kind = classify_row(_agent_status(row), run_status)
        urls = agent_repo_urls(row) + run_repo_urls(run)
        bucket = floor_kind(urls)
        if kind in {"running", "creating"}:
            running += 1
            if kind == "creating":
                creating += 1
            if bucket == "palemon":
                palemon += 1
            elif bucket == "gcs":
                gcs += 1
        elif kind == "leftover_active":
            leftover_active += 1
    return OccupancySummary(
        running=running,
        leftover_active=leftover_active,
        creating=creating,
        listed=listed,
        pages=catalog.pages,
        palemon=palemon,
        gcs=gcs,
        cap=limit,
        palemon_must=1 if palemon < limit else 0,
        gcs_must=1 if gcs < limit else 0,
    )


def _run_timeout() -> float:
    try:
        raw = float(os.environ.get("CLOUD_CURL_MAX_TIME") or "120")
    except ValueError:
        raw = 120.0
    return min(max(raw, 1.0), 15.0)


def _api_get(path: str, timeout: float) -> dict[str, Any] | list[Any] | None:
    """JSON object or list, or None on 404. OccupancyError on other failures."""
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
    if isinstance(payload, list):
        return payload
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


def fetch_runs(agent_id: str) -> list[dict[str, Any]]:
    """listRuns analog: GET /v1/agents/{id}/runs collection."""
    if not agent_id:
        return []
    payload = _api_get(f"/v1/agents/{agent_id}/runs", _run_timeout())
    if payload is None:
        return []
    return latest_run.unwrap_runs(payload)


def occupancy_from_api(*, bot_id: str = "") -> OccupancySummary:
    catalog = list_catalog.fetch_catalog_from_api()
    return occupancy_from_catalog(catalog, fetch_runs=fetch_runs, bot_id=bot_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Print CLOUD_OCCUPANCY from a paginated GET /v1/agents catalog "
            "(nextCursor beyond limit=100). Latest runStatus via listRuns; "
            "CREATING maps as RUNNING; Palemon vs GCS toward floor 8."
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
