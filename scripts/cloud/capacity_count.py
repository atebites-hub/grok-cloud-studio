#!/usr/bin/env python3
"""Per-repo RUNNING floor for capacity beats (LIV-67).

Count latest-run ``runStatus=RUNNING`` only. Leftover agent
``status=ACTIVE`` with ``runStatus=FINISHED`` is membership, not capacity.
``CREATING`` is not ``RUNNING``. Unbound agents are dropped.

Capacity beats call this helper (``scripts/cloud/capacity-count.sh``).
Do not remint GCS #78 / #73 / #82 list running filters. Never Bot CloudAgent.
Never prints API keys. Stdlib only.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

DEFAULT_MIN_RUNNING = 8
DEFAULT_LIST_LIMIT = 50
RUNNING = "RUNNING"
FINISHED = "FINISHED"

_GIT_SSH_PREFIX = "git@github.com:"


def min_running(raw: str | None = None) -> int:
    """GCS_CLOUD_MIN_RUNNING, default 8."""
    text = (raw if raw is not None else os.environ.get("GCS_CLOUD_MIN_RUNNING") or "").strip()
    if not text:
        return DEFAULT_MIN_RUNNING
    try:
        value = int(text)
    except ValueError:
        return DEFAULT_MIN_RUNNING
    if value < 0:
        return DEFAULT_MIN_RUNNING
    return value


def normalize_repo(value: str | None) -> str:
    """Canonical owner/name from org/name, https URL, .git suffix, or SSH."""
    text = (value or "").strip()
    if not text:
        return ""
    if text.lower().startswith(_GIT_SSH_PREFIX):
        text = text.split(":", 1)[1]
    lowered = text.lower()
    for prefix in (
        "https://github.com/",
        "http://github.com/",
        "https://www.github.com/",
        "http://www.github.com/",
        "github.com/",
    ):
        if lowered.startswith(prefix):
            text = text[len(prefix) :]
            break
    text = text.rstrip("/")
    if text.lower().endswith(".git"):
        text = text[:-4]
    return text.strip().lower().rstrip("/")


def normalize_run_status(raw: str | None) -> str:
    text = (raw or "").strip()
    if not text:
        return "none"
    upper = text.upper()
    if upper == "NONE":
        return "none"
    return upper


def counts_toward_running_floor(agent_status: str | None, run_status: str | None) -> bool:
    """True only for latest-run RUNNING. Agent ACTIVE is ignored."""
    _membership = agent_status
    return normalize_run_status(run_status) == RUNNING


def is_leftover_active_finished(agent_status: str | None, run_status: str | None) -> bool:
    """Leftover shell: still ACTIVE until archive, latest run already FINISHED."""
    agent = (agent_status or "").strip().upper()
    return agent == "ACTIVE" and normalize_run_status(run_status) == FINISHED


def unwrap(data: Any, key: str) -> Any:
    if isinstance(data, dict) and key in data and "id" not in data:
        inner = data[key]
        if isinstance(inner, dict):
            return inner
    return data


def _collect_repo_urls(payload: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    repo = payload.get("repo")
    if isinstance(repo, str) and repo.strip():
        urls.append(repo.strip())
    repos = payload.get("repos") or payload.get("repositories") or []
    if isinstance(repos, list):
        for item in repos:
            if isinstance(item, str) and item.strip():
                urls.append(item.strip())
            elif isinstance(item, dict):
                found = str(
                    item.get("url") or item.get("repository") or item.get("repo") or ""
                ).strip()
                if found:
                    urls.append(found)
    source = payload.get("source")
    if isinstance(source, dict):
        found = str(
            source.get("repository") or source.get("url") or source.get("repoUrl") or ""
        ).strip()
        if found:
            urls.append(found)
    git = payload.get("git")
    if isinstance(git, dict):
        for branch in git.get("branches") or []:
            if not isinstance(branch, dict):
                continue
            found = str(branch.get("repoUrl") or branch.get("url") or "").strip()
            if found:
                urls.append(found)
    return urls


def row_repo_urls(row: dict[str, Any]) -> list[str]:
    return _collect_repo_urls(row)


def _row_matches_repo(row: dict[str, Any], wanted: str) -> bool:
    key = normalize_repo(wanted)
    if not key:
        return False
    urls = row_repo_urls(row)
    if not urls:
        return False
    return any(normalize_repo(url) == key for url in urls)


def _row_run_status(row: dict[str, Any]) -> str:
    status = row.get("runStatus")
    if status is None:
        status = row.get("run_status")
    return normalize_run_status(str(status) if status is not None else "")


def _row_agent_status(row: dict[str, Any]) -> str:
    return str(row.get("agentStatus") or row.get("status") or "").strip()


def count_running_for_repo(rows: list[dict[str, Any]], repo: str) -> int:
    """Count runStatus=RUNNING on this bound remote. Unbound rows do not count."""
    n = 0
    for row in rows:
        if not _row_matches_repo(row, repo):
            continue
        if counts_toward_running_floor(_row_agent_status(row), _row_run_status(row)):
            n += 1
    return n


def count_leftover_active_finished_for_repo(rows: list[dict[str, Any]], repo: str) -> int:
    """Count ACTIVE+FINISHED leftovers on this bound remote. Not the floor."""
    n = 0
    for row in rows:
        if not _row_matches_repo(row, repo):
            continue
        if is_leftover_active_finished(_row_agent_status(row), _row_run_status(row)):
            n += 1
    return n


def floor_snapshot(
    running: int,
    leftover_active: int = 0,
    min_running_override: int | None = None,
) -> dict[str, int]:
    """RUNNING floor vs leftover ACTIVE membership. must_launch when running < floor."""
    floor = min_running() if min_running_override is None else min_running_override
    deficit = max(0, floor - running)
    return {
        "running": int(running),
        "leftover_active": int(leftover_active),
        "floor": floor,
        "deficit": deficit,
        "must_launch": 1 if deficit > 0 else 0,
    }


def format_capacity_line(repo: str, snap: dict[str, int]) -> str:
    key = normalize_repo(repo) or (repo or "").strip()
    return (
        f"CLOUD_CAPACITY repo={key} running={snap['running']} "
        f"floor={snap['floor']} leftover_active={snap['leftover_active']} "
        f"must_launch={snap['must_launch']} deficit={snap['deficit']}"
    )


def _list_timeout() -> float:
    try:
        raw = float(os.environ.get("CLOUD_CURL_MAX_TIME") or "120")
    except ValueError:
        raw = 120.0
    return min(raw, 15.0)


def _api_get(path: str) -> dict[str, Any] | None:
    base = (os.environ.get("CURSOR_API_BASE") or "https://api.cursor.com").rstrip("/")
    key = os.environ.get("CURSOR_API_KEY") or ""
    url = f"{base}{path}"
    token = base64.b64encode(f"{key}:".encode("utf-8")).decode("ascii")
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "Authorization": f"Basic {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=_list_timeout()) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def fetch_agent(agent_id: str) -> dict[str, Any]:
    payload = _api_get(f"/v1/agents/{agent_id}")
    if payload is None:
        return {}
    agent = unwrap(payload, "agent")
    return agent if isinstance(agent, dict) else {}


def fetch_run(agent_id: str, run_id: str) -> dict[str, Any]:
    payload = _api_get(f"/v1/agents/{agent_id}/runs/{run_id}")
    if payload is None:
        return {}
    run = unwrap(payload, "run")
    return run if isinstance(run, dict) else {}


def _annotate_item(raw: dict[str, Any]) -> dict[str, Any] | None:
    agent_id = str(raw.get("id") or raw.get("agentId") or "").strip()
    if not agent_id:
        return None
    detail = fetch_agent(agent_id)
    agent = {**raw, **detail} if detail else dict(raw)
    run_id = str(agent.get("latestRunId") or raw.get("latestRunId") or "").strip()
    run: dict[str, Any] = {}
    if run_id:
        run = fetch_run(agent_id, run_id)
    urls = _collect_repo_urls(agent)
    if run:
        for extra in _collect_repo_urls(run):
            if extra not in urls:
                urls.append(extra)
    if not urls:
        return None
    status = normalize_run_status(str(run.get("status") or run.get("runStatus") or ""))
    if status == "none" and not run_id:
        status = "none"
    elif status == "none" and run_id and not run:
        status = "none"
    return {
        "id": agent_id,
        "status": str(agent.get("status") or raw.get("status") or ""),
        "agentStatus": str(agent.get("status") or raw.get("status") or ""),
        "runStatus": status,
        "latestRunId": run_id,
        "repo": urls[0],
        "repos": urls,
    }


def collect_from_list(items: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    pending = [item for item in items if isinstance(item, dict)]
    if not pending:
        return rows
    workers = min(8, max(1, len(pending)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_annotate_item, item) for item in pending]
        for fut in as_completed(futures):
            try:
                row = fut.result()
            except Exception:
                continue
            if row:
                rows.append(row)
    return rows


def wanted_repo(cli_repo: str = "") -> str:
    if (cli_repo or "").strip():
        return cli_repo.strip()
    for name in ("GCS_CLOUD_REPO", "CLOUD_REPO_URL", "CURSOR_CLOUD_REPO"):
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def emit_capacity_lines(rows: list[dict[str, Any]], repo: str) -> list[str]:
    key = wanted_repo(repo)
    if key:
        running = count_running_for_repo(rows, key)
        leftover = count_leftover_active_finished_for_repo(rows, key)
        snap = floor_snapshot(running, leftover_active=leftover)
        return [format_capacity_line(key, snap)]
    seen: dict[str, None] = {}
    for row in rows:
        urls = row_repo_urls(row)
        if not urls:
            continue
        slug = normalize_repo(urls[0])
        if slug:
            seen.setdefault(slug, None)
    if not seen:
        return ["CLOUD_CAPACITY empty"]
    lines: list[str] = []
    for slug in sorted(seen):
        running = count_running_for_repo(rows, slug)
        leftover = count_leftover_active_finished_for_repo(rows, slug)
        snap = floor_snapshot(running, leftover_active=leftover)
        lines.append(format_capacity_line(slug, snap))
    return lines


def count_from_body(body_path: str, repo: str = "") -> int:
    with open(body_path, encoding="utf-8") as fh:
        data = json.load(fh)
    items = data.get("items") or data.get("agents") or []
    if not isinstance(items, list):
        items = []
    rows = collect_from_list(items)
    for line in emit_capacity_lines(rows, repo):
        sys.stdout.write(line + "\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("body", help="JSON body from GET /v1/agents")
    parser.add_argument(
        "--repo",
        default="",
        help="Bound remote (org/name or https URL). Default: GCS_CLOUD_REPO.",
    )
    args = parser.parse_args(argv)
    return count_from_body(args.body, args.repo)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except OSError:
            pass
        raise SystemExit(0)
