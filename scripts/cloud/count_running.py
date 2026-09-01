#!/usr/bin/env python3
"""Count Cursor Cloud runStatus=RUNNING per bound repo.

GET /v1/agents list items omit bound repos. Load GET /v1/agents/{id} and
the latest run so Directors see RUNNING counts per git remote. Leftover
agent ACTIVE is membership, not capacity. CREATING is not RUNNING.

Palemon Linear is Living Sky (LIV), not Black Swan. Never Bot CloudAgent.
This is the per-repo RUNNING counter. It does not remint list --repo
(GCS #50) or list runStatus rows (GCS #29).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Any

_SCHEME_RE = re.compile(r"^https?://", re.I)
_GITHUB_HOST_RE = re.compile(r"^github\.com/", re.I)
_GIT_SSH_PREFIX = "git@github.com:"


def repo_key(value: str | None) -> str:
    """Canonical owner/name from org/name, https URL, .git suffix, or SSH."""
    text = (value or "").strip()
    if not text:
        return ""
    if text.lower().startswith(_GIT_SSH_PREFIX):
        text = text.split(":", 1)[1]
    text = _SCHEME_RE.sub("", text)
    text = _GITHUB_HOST_RE.sub("", text)
    text = text.rstrip("/")
    if text.lower().endswith(".git"):
        text = text[:-4]
    return text.lower()


def unwrap(data: Any, key: str) -> Any:
    if isinstance(data, dict) and key in data and "id" not in data:
        inner = data[key]
        if isinstance(inner, dict):
            return inner
    return data


def run_status(run: dict[str, Any] | None) -> str:
    if not isinstance(run, dict):
        return "none"
    status = str(run.get("status") or "").strip()
    if not status:
        return "none"
    upper = status.upper()
    if upper == "NONE":
        return "none"
    return upper


def is_running(status: str | None) -> bool:
    return (status or "").strip().upper() == "RUNNING"


def agent_repo_urls(agent: dict[str, Any] | None, run: dict[str, Any] | None = None) -> list[str]:
    urls: list[str] = []
    if isinstance(agent, dict):
        repo = agent.get("repo")
        if isinstance(repo, str) and repo.strip():
            urls.append(repo.strip())
        repos = agent.get("repos")
        if isinstance(repos, list):
            for entry in repos:
                if isinstance(entry, str) and entry.strip():
                    urls.append(entry.strip())
                elif isinstance(entry, dict):
                    found = str(entry.get("url") or entry.get("repository") or "").strip()
                    if found:
                        urls.append(found)
        source = agent.get("source")
        if isinstance(source, dict):
            found = str(source.get("repository") or source.get("url") or "").strip()
            if found:
                urls.append(found)
    if isinstance(run, dict):
        git = run.get("git")
        branches = git.get("branches") if isinstance(git, dict) else None
        if isinstance(branches, list):
            for item in branches:
                if not isinstance(item, dict):
                    continue
                found = str(item.get("repoUrl") or item.get("url") or "").strip()
                if found:
                    urls.append(found)
    return urls


def matches_repo(
    agent: dict[str, Any] | None,
    run: dict[str, Any] | None,
    wanted: str,
) -> bool:
    key = repo_key(wanted)
    if not key:
        return True
    urls = agent_repo_urls(agent, run)
    if not urls:
        return False
    return any(repo_key(url) == key for url in urls)


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


def bound_repo_key(agent: dict[str, Any], run: dict[str, Any]) -> str:
    urls = agent_repo_urls(agent, run)
    if not urls:
        return ""
    return repo_key(urls[0])


def count_running_by_repo(rows: list[tuple[str, str]]) -> dict[str, int]:
    """Count RUNNING (not leftover ACTIVE) per canonical repo key."""
    counts: dict[str, int] = {}
    for key, status in rows:
        if not key:
            continue
        counts.setdefault(key, 0)
        if is_running(status):
            counts[key] += 1
    return counts


def format_count_line(repo: str, running: int) -> str:
    return f"CLOUD_RUNNING repo={repo} running={running}"


def format_counts(counts: dict[str, int], wanted: str = "") -> list[str]:
    key = repo_key(wanted)
    if key:
        return [format_count_line(key, counts.get(key, 0))]
    if not counts:
        return ["CLOUD_RUNNING empty"]
    return [format_count_line(repo, counts[repo]) for repo in sorted(counts)]


def collect_from_list(items: list[Any], wanted: str = "") -> dict[str, int]:
    rows: list[tuple[str, str]] = []
    wanted_key = repo_key(wanted)
    for raw in items:
        if not isinstance(raw, dict):
            continue
        agent_id = str(raw.get("id") or "")
        run_id = str(raw.get("latestRunId") or "")
        agent: dict[str, Any] = dict(raw)
        run: dict[str, Any] = {}
        if agent_id:
            detail = fetch_agent(agent_id)
            if detail:
                agent = {**raw, **detail}
        if agent_id and run_id:
            run = fetch_run(agent_id, run_id)
        if wanted_key and not matches_repo(agent, run, wanted_key):
            continue
        key = bound_repo_key(agent, run)
        if not key:
            continue
        status = run_status(run) if run_id else "none"
        rows.append((key, status))
    return count_running_by_repo(rows)


def count_from_body(body_path: str, repo: str = "") -> int:
    with open(body_path, encoding="utf-8") as fh:
        data = json.load(fh)
    items = data.get("items") or []
    if not isinstance(items, list):
        items = []
    counts = collect_from_list(items, repo)
    for line in format_counts(counts, repo):
        sys.stdout.write(line + "\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("body", help="JSON body from GET /v1/agents")
    parser.add_argument(
        "--repo",
        default="",
        help="Count only agents bound to org/name or https://github.com/org/name",
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
