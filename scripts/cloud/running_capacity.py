#!/usr/bin/env python3
"""Count RUNNING Cursor Cloud runs for GCS_CLOUD_REPO.

Do not treat agent status ACTIVE + runStatus FINISHED as workers.
Print runStatus. Default floor GCS_CLOUD_MIN_RUNNING=8.

If playability/art work is in progress and RUNNING < N, CLOUD_MUST_LAUNCH=1.
Stdlib only. Never prints API keys.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_MIN_RUNNING = 8
RUNNING_STATUS = "RUNNING"
DEFAULT_LIST_LIMIT = 50

PLAYABILITY_ART_KINDS = frozenset(
    {
        "playability",
        "art",
        "gameplay",
        "visual",
        "animation",
        "content-play",
    }
)

_PLAYABILITY_ART_RE = re.compile(
    r"\b("
    r"playability|playable|gameplay|art-director|"
    r"art pass|concept art|ui art|tileset|sprite|"
    r"visual polish|\bart\b"
    r")\b",
    re.IGNORECASE,
)


def configured_min_running(override: int | None = None) -> int:
    if override is not None:
        return max(0, int(override))
    raw = (os.environ.get("GCS_CLOUD_MIN_RUNNING") or "").strip()
    if raw.isdigit():
        return int(raw)
    return DEFAULT_MIN_RUNNING


def is_playability_or_art(work_kind: str = "", prompt: str = "") -> bool:
    kind = (work_kind or "").strip().lower()
    if kind in PLAYABILITY_ART_KINDS:
        return True
    blob = f"{work_kind} {prompt}".strip()
    if not blob:
        return False
    return bool(_PLAYABILITY_ART_RE.search(blob))


def must_launch_cloud_floor(
    *,
    work_kind: str = "",
    prompt: str = "",
    running_count: int,
    min_running: int | None = None,
) -> bool:
    if not is_playability_or_art(work_kind, prompt):
        return False
    floor = configured_min_running(min_running)
    return int(running_count) < int(floor)


def normalize_repo(url: str) -> str:
    text = (url or "").strip().rstrip("/")
    if text.endswith(".git"):
        text = text[:-4]
    return text.lower()


def agent_repo_urls(agent: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    repos = agent.get("repos") or agent.get("repositories") or []
    if isinstance(repos, list):
        for item in repos:
            if isinstance(item, dict):
                for key in ("url", "repository", "repo"):
                    val = item.get(key)
                    if val:
                        urls.append(str(val))
            elif isinstance(item, str) and item.strip():
                urls.append(item)
    source = agent.get("source")
    if isinstance(source, dict):
        for key in ("repository", "repo", "url", "repoUrl"):
            val = source.get(key)
            if val:
                urls.append(str(val))
    for key in ("repository", "repo", "repoUrl"):
        val = agent.get(key)
        if val:
            urls.append(str(val))
    return urls


def agent_matches_repo(agent: dict[str, Any], repo: str) -> bool:
    want = normalize_repo(repo)
    if not want:
        return True
    urls = agent_repo_urls(agent)
    if not urls:
        return True
    return any(normalize_repo(url) == want for url in urls)


def _unwrap(data: Any, key: str) -> Any:
    if isinstance(data, dict) and key in data and "id" not in data:
        inner = data[key]
        if isinstance(inner, dict):
            return inner
    return data


def extract_run_status(agent: dict[str, Any], run_payload: dict[str, Any] | None = None) -> str:
    if run_payload:
        run = _unwrap(run_payload, "run")
        if isinstance(run, dict):
            for key in ("status", "runStatus"):
                val = run.get(key)
                if val:
                    return str(val).upper()
    for key in ("runStatus", "latestRunStatus"):
        val = agent.get(key)
        if val:
            return str(val).upper()
    nested = agent.get("latestRun") or agent.get("run")
    if isinstance(nested, dict):
        val = nested.get("status") or nested.get("runStatus")
        if val:
            return str(val).upper()
    return ""


def extract_agent_status(agent: dict[str, Any]) -> str:
    val = agent.get("agentStatus") or agent.get("status") or ""
    return str(val).upper() if val else "ACTIVE"


def annotate_agents(
    items: list[dict[str, Any]],
    *,
    repo: str,
    run_by_id: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    known = run_by_id or {}
    for raw in items:
        if not isinstance(raw, dict):
            continue
        agent = _unwrap(raw, "agent")
        if not isinstance(agent, dict):
            continue
        if not agent_matches_repo(agent, repo):
            continue
        agent_id = str(agent.get("id") or agent.get("agentId") or "")
        run_id = str(agent.get("latestRunId") or agent.get("runId") or "")
        run_status = ""
        if run_id and run_id in known:
            run_status = str(known[run_id]).upper()
        if not run_status:
            run_status = extract_run_status(agent) or "none"
        urls = agent_repo_urls(agent)
        matched_repo = urls[0] if urls else repo
        rows.append(
            {
                "id": agent_id,
                "name": str(agent.get("name") or ""),
                "agentStatus": extract_agent_status(agent),
                "runStatus": run_status,
                "runId": run_id,
                "repo": matched_repo,
            }
        )
    return rows


def count_running(rows: list[dict[str, str]]) -> int:
    return sum(1 for row in rows if (row.get("runStatus") or "").upper() == RUNNING_STATUS)


def format_rows(rows: list[dict[str, str]]) -> list[str]:
    lines: list[str] = []
    for row in rows:
        lines.append(
            " ".join(
                [
                    f"id={row.get('id') or ''}",
                    f"agentStatus={row.get('agentStatus') or 'unknown'}",
                    f"runStatus={row.get('runStatus') or 'none'}",
                    f"name={row.get('name') or ''}",
                    f"repo={row.get('repo') or ''}",
                ]
            )
        )
    return lines


def must_launch_reason(
    *,
    work_kind: str,
    prompt: str,
    running_count: int,
    floor: int,
) -> str:
    if not is_playability_or_art(work_kind, prompt):
        return "not-playability-art"
    if running_count < floor:
        return "playability-art-below-floor"
    return "at-floor"


def _api_base() -> str:
    return (os.environ.get("CURSOR_API_BASE") or "https://api.cursor.com").rstrip("/")


def _api_key() -> str:
    return (os.environ.get("CURSOR_API_KEY") or "").strip()


def _http_get_json(path: str) -> dict[str, Any] | None:
    key = _api_key()
    if not key:
        return None
    url = f"{_api_base()}{path}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("Accept", "application/json")
    token = base64.b64encode(f"{key}:".encode("utf-8")).decode("ascii")
    req.add_header("Authorization", f"Basic {token}")
    timeout = float(os.environ.get("CLOUD_CURL_MAX_TIME") or "30")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            blob = resp.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def fetch_agents(limit: int) -> list[dict[str, Any]]:
    data = _http_get_json(f"/v1/agents?limit={int(limit)}")
    if not data:
        return []
    items = data.get("items")
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    return []


def fetch_run_status(agent_id: str, run_id: str) -> str:
    if not agent_id or not run_id:
        return ""
    path = f"/v1/agents/{urllib.parse.quote(agent_id)}/runs/{urllib.parse.quote(run_id)}"
    data = _http_get_json(path)
    if not data:
        return ""
    return extract_run_status({}, data)


def collect_rows(*, repo: str, limit: int) -> list[dict[str, str]]:
    items = fetch_agents(limit)
    run_by_id: dict[str, str] = {}
    for item in items:
        if not agent_matches_repo(item, repo):
            continue
        run_id = str(item.get("latestRunId") or "")
        agent_id = str(item.get("id") or "")
        if run_id:
            status = fetch_run_status(agent_id, run_id)
            if status:
                run_by_id[run_id] = status
    return annotate_agents(items, repo=repo, run_by_id=run_by_id)


def target_repo() -> str:
    for name in ("GCS_CLOUD_REPO", "CLOUD_REPO_URL", "CURSOR_CLOUD_REPO"):
        val = (os.environ.get(name) or "").strip()
        if val:
            return val
    return ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Print Cursor Cloud runStatus rows and CLOUD_MUST_LAUNCH for playability/art."
    )
    parser.add_argument("--work-kind", default="", help="playability, art, qa, ...")
    parser.add_argument("--prompt", default="", help="Optional work prompt for kind detection")
    parser.add_argument("--repo", default="", help="Override GCS_CLOUD_REPO")
    parser.add_argument("--min", type=int, default=None, help="Override GCS_CLOUD_MIN_RUNNING")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIST_LIMIT)
    args = parser.parse_args(argv)

    repo = (args.repo or target_repo()).strip()
    if not repo:
        print("CLOUD_RUNNING_ERR missing GCS_CLOUD_REPO", file=sys.stderr)
        return 1
    if not _api_key():
        print("CLOUD_RUNNING_ERR missing CURSOR_API_KEY", file=sys.stderr)
        return 1

    floor = configured_min_running(args.min)
    rows = collect_rows(repo=repo, limit=max(1, int(args.limit)))
    for line in format_rows(rows):
        print(line)
    running = count_running(rows)
    launch = must_launch_cloud_floor(
        work_kind=args.work_kind,
        prompt=args.prompt,
        running_count=running,
        min_running=floor,
    )
    reason = must_launch_reason(
        work_kind=args.work_kind,
        prompt=args.prompt,
        running_count=running,
        floor=floor,
    )
    print(f"CLOUD_RUNNING count={running} min={floor} repo={repo}")
    print(f"CLOUD_MUST_LAUNCH={1 if launch else 0} reason={reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
