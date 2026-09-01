#!/usr/bin/env python3
"""Director Extra High result JSON: bound repos[0].url plus run context."""
from __future__ import annotations

import json
import sys
from typing import Any

BoundRepo = dict[str, str]


def unwrap(data: Any, key: str) -> Any:
    if isinstance(data, dict) and key in data and "id" not in data:
        inner = data[key]
        if isinstance(inner, dict):
            return inner
    return data


def normalize_repo_url(url: str) -> str:
    trimmed = url.strip()
    if not trimmed:
        return ""
    if trimmed.lower().startswith("http://") or trimmed.lower().startswith("https://"):
        return trimmed
    return "https://" + trimmed.lstrip("/")


def bound_repos(agent: dict[str, Any] | None) -> list[BoundRepo]:
    if not isinstance(agent, dict):
        return []
    raw = agent.get("repos")
    if not isinstance(raw, list):
        return []
    out: list[BoundRepo] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not isinstance(url, str) or not url.strip():
            continue
        entry: BoundRepo = {"url": url.strip()}
        ref = item.get("startingRef")
        if isinstance(ref, str) and ref.strip():
            entry["startingRef"] = ref.strip()
        out.append(entry)
    return out


def bound_repo_url(agent: dict[str, Any] | None, run: dict[str, Any] | None = None) -> str | None:
    """Prefer GET /v1/agents bound repos[0].url; else run git.branches[].repoUrl."""
    repos = bound_repos(agent)
    if repos:
        return normalize_repo_url(repos[0]["url"])
    if not isinstance(run, dict):
        return None
    git = run.get("git")
    branches = git.get("branches") if isinstance(git, dict) else None
    if not isinstance(branches, list):
        return None
    for item in branches:
        if not isinstance(item, dict):
            continue
        repo_url = item.get("repoUrl")
        if isinstance(repo_url, str) and repo_url.strip():
            return normalize_repo_url(repo_url)
    return None


def _run_error(err: Any) -> dict[str, str] | None:
    if isinstance(err, str):
        return {"message": err}
    if not isinstance(err, dict):
        return None
    if "message" not in err:
        return {"message": json.dumps(err)}
    return err


def director_result(agent: dict[str, Any] | None, run: dict[str, Any] | None = None) -> dict[str, Any]:
    agent = agent if isinstance(agent, dict) else {}
    run = run if isinstance(run, dict) else {}
    branches: list[str] = []
    pr: str | None = None
    git = run.get("git") or {}
    for item in (git.get("branches") or []) if isinstance(git, dict) else []:
        if not isinstance(item, dict):
            continue
        if item.get("branch"):
            branches.append(str(item["branch"]))
        if item.get("prUrl") and not pr:
            pr = str(item["prUrl"])
    status = run.get("status") or None
    repos = bound_repos(agent)
    result_text = run.get("result") or ""
    if isinstance(result_text, str):
        result_text = result_text.strip() or None
    else:
        result_text = None
    return {
        "agentId": agent.get("id") or "",
        "name": agent.get("name") or "",
        "url": agent.get("url") or "",
        "runId": run.get("id") or agent.get("latestRunId") or None,
        "status": status,
        "agentStatus": agent.get("status") or None,
        "runStatus": status,
        "prUrl": pr,
        "branches": branches,
        "branch": branches[0] if branches else None,
        "summary": None,
        "result": result_text,
        "error": _run_error(run.get("error")),
        "repoUrl": bound_repo_url(agent, run),
        "repos": repos,
    }


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        print("usage: result_payload.py AGENT.json RUN.json", file=sys.stderr)
        return 2
    with open(args[0], encoding="utf-8") as fh:
        agent = unwrap(json.load(fh), "agent")
    with open(args[1], encoding="utf-8") as fh:
        run = unwrap(json.load(fh), "run")
    if not isinstance(agent, dict):
        agent = {}
    if not isinstance(run, dict):
        run = {}
    print(json.dumps(director_result(agent, run), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
