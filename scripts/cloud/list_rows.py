#!/usr/bin/env python3
"""Format Cursor Cloud agent list rows with latest-run runStatus.

GET /v1/agents status stays ACTIVE until archive. Execution state lives on
GET /v1/agents/{id}/runs/{latestRunId}. Agent ACTIVE is membership, not
liveness: leftover FINISHED grunts must not look like spinning workers.

A missing or failed run fetch prints runStatus=none so the list still succeeds.
Never prints API keys.

Living Sky LIV-67. This helper only formats list rows with latest-run
status. It does not add sibling list filters, a capacity floor, or MCP list
tools. Never Bot CloudAgent.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

_FETCH_WORKERS = 8
_FETCH_TIMEOUT_CAP_SEC = 15.0


def unwrap_entity(data: Any, key: str) -> Any:
    if isinstance(data, dict) and key in data and "id" not in data:
        inner = data[key]
        if isinstance(inner, dict):
            return inner
    return data


def normalize_run_status(raw: Any) -> str:
    status = str(raw or "").strip()
    return status.upper() if status else "none"


def format_list_row(
    *,
    agent_id: str,
    agent_status: str,
    run_status: str,
    name: str,
    url: str,
    run_id: str,
) -> str:
    return (
        f"id={agent_id} status={agent_status} runStatus={run_status} "
        f"name={name} url={url} latestRunId={run_id}"
    )


def _run_fetch_timeout() -> float:
    raw = os.environ.get("CLOUD_CURL_MAX_TIME") or "120"
    try:
        return min(float(raw), _FETCH_TIMEOUT_CAP_SEC)
    except ValueError:
        return _FETCH_TIMEOUT_CAP_SEC


def fetch_run_status(base: str, key: str, agent_id: str, run_id: str, timeout: float) -> str:
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
    if not isinstance(payload, dict):
        return "none"
    run = unwrap_entity(payload, "run")
    if not isinstance(run, dict):
        return "none"
    return normalize_run_status(run.get("status"))


def _agent_fields(item: Any) -> tuple[str, str, str, str, str]:
    if not isinstance(item, dict):
        return "", "", "", "", ""
    agent = unwrap_entity(item, "agent")
    if not isinstance(agent, dict):
        agent = item
    return (
        str(agent.get("id") or ""),
        str(agent.get("status") or ""),
        str(agent.get("name") or ""),
        str(agent.get("url") or ""),
        str(agent.get("latestRunId") or ""),
    )


def format_list_lines(items: list[Any]) -> list[str]:
    base = (os.environ.get("CURSOR_API_BASE") or "https://api.cursor.com").rstrip("/")
    key = os.environ.get("CURSOR_API_KEY") or ""
    timeout = _run_fetch_timeout()
    parsed = [_agent_fields(item) for item in items]
    run_status_by_index = ["none"] * len(parsed)
    jobs: list[tuple[int, str, str]] = [
        (idx, agent_id, run_id)
        for idx, (agent_id, _status, _name, _url, run_id) in enumerate(parsed)
        if agent_id and run_id and key
    ]
    if jobs:
        workers = min(_FETCH_WORKERS, len(jobs))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            pending = {
                pool.submit(fetch_run_status, base, key, agent_id, run_id, timeout): idx
                for idx, agent_id, run_id in jobs
            }
            for fut in as_completed(pending):
                idx = pending[fut]
                try:
                    run_status_by_index[idx] = fut.result()
                except Exception:
                    run_status_by_index[idx] = "none"
    lines: list[str] = []
    for idx, (agent_id, agent_status, name, url, run_id) in enumerate(parsed):
        lines.append(
            format_list_row(
                agent_id=agent_id,
                agent_status=agent_status,
                run_status=run_status_by_index[idx],
                name=name,
                url=url,
                run_id=run_id,
            )
        )
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print agent list rows with runStatus.")
    parser.add_argument("body_json", help="Path to GET /v1/agents JSON body")
    args = parser.parse_args(argv)
    with open(args.body_json, encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        items = data.get("items") or []
    elif isinstance(data, list):
        items = data
    else:
        items = []
    if not isinstance(items, list):
        items = []
    for line in format_list_lines(items):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
