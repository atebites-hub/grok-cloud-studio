#!/usr/bin/env python3
"""Cursor Cloud runStatus vs leftover agent ACTIVE; Director RUNNING floor.

Agent `status` stays ACTIVE until archive. Workers are latest-run
`runStatus` in {RUNNING, CREATING}. ACTIVE+FINISHED leftovers are not workers.

Directors must cloud_launch until the target repo has at least
GCS_CLOUD_MIN_RUNNING (default 8) in-flight runs. Never Bot CloudAgent.
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

DEFAULT_MIN_RUNNING = 8
IN_FLIGHT_RUN = frozenset({"RUNNING", "CREATING"})
_KV_RE = re.compile(r"(\w+)=(\S*)")


def min_running(raw: str | None = None) -> int:
    text = (raw if raw is not None else os.environ.get("GCS_CLOUD_MIN_RUNNING") or "").strip()
    if not text:
        return DEFAULT_MIN_RUNNING
    try:
        value = int(text)
    except ValueError:
        return DEFAULT_MIN_RUNNING
    return value if value > 0 else DEFAULT_MIN_RUNNING


def normalize_run_status(status: str | None) -> str:
    text = (status or "").strip()
    if not text:
        return "none"
    upper = text.upper()
    if upper == "NONE":
        return "none"
    return upper


def is_in_flight_run(status: str | None) -> bool:
    return normalize_run_status(status) in IN_FLIGHT_RUN


def must_launch_cloud(*, running_count: int, cap: int | None = None) -> bool:
    limit = min_running() if cap is None else cap
    if limit <= 0:
        return False
    return running_count < limit


def _norm_repo(url: str) -> str:
    text = (url or "").strip().lower()
    if text.startswith("git@github.com:"):
        text = "https://github.com/" + text.split(":", 1)[1]
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


def row_matches_repo(item: dict[str, Any], repo: str | None) -> bool:
    if not (repo or "").strip():
        return True
    wanted = _norm_repo(repo)
    urls = agent_repo_urls(item)
    if not urls:
        return True
    return any(_norm_repo(url) == wanted for url in urls)


def count_in_flight(rows: list[dict[str, Any]], repo: str | None = None) -> int:
    n = 0
    for row in rows:
        if not row_matches_repo(row, repo):
            continue
        if is_in_flight_run(str(row.get("runStatus") or row.get("run_status") or "")):
            n += 1
    return n


def unwrap_run(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    if "id" not in payload and isinstance(payload.get("run"), dict):
        inner = payload["run"]
        if isinstance(inner, dict):
            return inner
    return payload


def fetch_run_status(
    base: str,
    key: str,
    agent_id: str,
    run_id: str,
    timeout: float,
) -> str:
    url = f"{base.rstrip('/')}/v1/agents/{agent_id}/runs/{run_id}"
    token = base64.b64encode(f"{key}:".encode("utf-8")).decode("ascii")
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "Authorization": f"Basic {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
        return "none"
    run = unwrap_run(payload)
    if not isinstance(run, dict):
        return "none"
    return normalize_run_status(str(run.get("status") or ""))


def annotate_list_items(
    items: list[dict[str, Any]],
    *,
    base: str,
    key: str,
    timeout: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        row = dict(item)
        agent_id = str(item.get("id") or "")
        run_id = str(item.get("latestRunId") or "")
        row["runStatus"] = "none"
        if agent_id and run_id:
            row["runStatus"] = fetch_run_status(base, key, agent_id, run_id, timeout)
        urls = agent_repo_urls(item)
        row["repo"] = urls[0] if urls else ""
        rows.append(row)
    return rows


def format_list_row(item: dict[str, Any]) -> str:
    agent_status = str(item.get("agentStatus") or item.get("status") or "")
    parts = [
        f"id={item.get('id') or ''}",
        f"agentStatus={agent_status}",
        f"runStatus={normalize_run_status(str(item.get('runStatus') or ''))}",
        f"name={item.get('name') or ''}",
        f"url={item.get('url') or ''}",
        f"latestRunId={item.get('latestRunId') or ''}",
    ]
    repo = str(item.get("repo") or "")
    if repo:
        parts.append(f"repo={repo}")
    return " ".join(parts)


def parse_list_output(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("CLOUD_"):
            continue
        if "runStatus=" not in stripped and "id=" not in stripped:
            continue
        fields = {m.group(1): m.group(2) for m in _KV_RE.finditer(stripped)}
        if "id" not in fields:
            continue
        rows.append(
            {
                "id": fields.get("id") or "",
                "status": fields.get("agentStatus") or fields.get("status") or "",
                "agentStatus": fields.get("agentStatus") or fields.get("status") or "",
                "runStatus": normalize_run_status(fields.get("runStatus")),
                "name": fields.get("name") or "",
                "url": fields.get("url") or "",
                "latestRunId": fields.get("latestRunId") or "",
                "repo": fields.get("repo") or "",
            }
        )
    return rows


def must_launch_reason(*, running_count: int, cap: int) -> str:
    if running_count >= cap:
        return "at-floor"
    return "below-floor"


def decide(
    *,
    running_count: int,
    cap: int | None = None,
    repo: str = "",
) -> dict[str, Any]:
    limit = min_running() if cap is None else cap
    must = must_launch_cloud(running_count=running_count, cap=limit)
    return {
        "running": running_count,
        "cap": limit,
        "repo": repo,
        "must_launch": must,
        "reason": must_launch_reason(running_count=running_count, cap=limit),
    }


def format_decision(decision: dict[str, Any]) -> str:
    must = 1 if decision["must_launch"] else 0
    repo = decision.get("repo") or "-"
    return (
        f"CLOUD_RUNNING={decision['running']} cap={decision['cap']} repo={repo}\n"
        f"CLOUD_MUST_LAUNCH={must} reason={decision['reason']}\n"
    )


def _list_timeout() -> float:
    try:
        raw = float(os.environ.get("CLOUD_CURL_MAX_TIME") or "120")
    except ValueError:
        raw = 120.0
    return min(raw, 15.0)


def cmd_format_list(body_path: str) -> int:
    with open(body_path, encoding="utf-8") as fh:
        data = json.load(fh)
    items = data.get("items") or []
    if not isinstance(items, list):
        items = []
    base = (os.environ.get("CURSOR_API_BASE") or "https://api.cursor.com").rstrip("/")
    key = os.environ.get("CURSOR_API_KEY") or ""
    rows = annotate_list_items(
        [i for i in items if isinstance(i, dict)],
        base=base,
        key=key,
        timeout=_list_timeout(),
    )
    for row in rows:
        sys.stdout.write(format_list_row(row) + "\n")
    return 0


def cmd_decide_from_list(*, repo: str, cap: int | None) -> int:
    text = sys.stdin.read()
    sys.stdout.write(text)
    if text and not text.endswith("\n"):
        sys.stdout.write("\n")
    rows = parse_list_output(text)
    n = count_in_flight(rows, repo=repo or None)
    decision = decide(running_count=n, cap=cap, repo=repo)
    sys.stdout.write(format_decision(decision))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    fmt = sub.add_parser("format-list")
    fmt.add_argument("body")
    dec = sub.add_parser("decide-from-list")
    dec.add_argument("--repo", default="")
    dec.add_argument("--cap", type=int, default=None)
    args = parser.parse_args(argv)
    if args.cmd == "format-list":
        return cmd_format_list(args.body)
    if args.cmd == "decide-from-list":
        return cmd_decide_from_list(repo=args.repo, cap=args.cap)
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except OSError:
            pass
        raise SystemExit(0)
