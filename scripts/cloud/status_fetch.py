#!/usr/bin/env python3
"""Parallel REST status for one or more Cursor Cloud bc-ids.

Prints runStatus per id on the same line as id=. Used by status.sh when the
SDK is not selected (CURSOR_API_BASE / CLOUD_FORCE_REST). Capacity beats pass
many ids in one process so they do not serial-timeout get_agent_run.

Never prints API keys.
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

Row = dict[str, Any]


def request_timeout() -> float:
    try:
        raw = float(os.environ.get("CLOUD_CURL_MAX_TIME") or "120")
    except ValueError:
        raw = 120.0
    return max(raw, 1.0)


def api_base() -> str:
    return (os.environ.get("CURSOR_API_BASE") or "https://api.cursor.com").rstrip("/")


def api_key() -> str:
    return os.environ.get("CURSOR_API_KEY") or ""


def auth_header(key: str) -> str:
    token = base64.b64encode(f"{key}:".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def empty_row(agent_id: str) -> Row:
    return {
        "id": agent_id,
        "agentId": agent_id,
        "name": "",
        "url": "",
        "latestRunId": "",
        "agentStatus": "unknown",
        "runStatus": "none",
        "status": "none",
    }


def unwrap(data: Any, key: str) -> dict[str, Any]:
    if isinstance(data, dict) and key in data and "id" not in data:
        inner = data[key]
        if isinstance(inner, dict):
            return inner
    return data if isinstance(data, dict) else {}


def normalize_run_status(status: str | None) -> str:
    text = (status or "").strip()
    if not text:
        return "none"
    upper = text.upper()
    if upper == "NONE":
        return "none"
    return upper


def http_get(path: str, timeout: float) -> tuple[int, Any]:
    url = f"{api_base()}{path}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": auth_header(api_key()),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            code = int(getattr(resp, "status", 200) or 200)
            try:
                return code, json.loads(raw)
            except json.JSONDecodeError:
                return code, {}
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            payload = {}
        return int(exc.code), payload
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return 0, {}


def fetch_one(agent_id: str, timeout: float) -> Row:
    code, payload = http_get(f"/v1/agents/{agent_id}", timeout)
    agent = unwrap(payload, "agent")
    if code < 200 or code >= 300 or not agent:
        return empty_row(agent_id)
    run_id = str(agent.get("latestRunId") or "")
    run_status = "none"
    if run_id:
        rcode, run_payload = http_get(f"/v1/agents/{agent_id}/runs/{run_id}", timeout)
        run = unwrap(run_payload, "run")
        if 200 <= rcode < 300:
            run_status = normalize_run_status(str(run.get("status") or ""))
    aid = str(agent.get("id") or agent_id)
    return {
        "id": aid,
        "agentId": aid,
        "name": str(agent.get("name") or ""),
        "url": str(agent.get("url") or ""),
        "latestRunId": run_id,
        "agentStatus": str(agent.get("status") or "unknown"),
        "runStatus": run_status,
        "status": run_status,
    }


def fetch_many(ids: list[str], timeout: float) -> list[Row]:
    if not ids:
        return []
    if len(ids) == 1:
        return [fetch_one(ids[0], timeout)]
    workers = min(16, len(ids))
    by_id: dict[str, Row] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(fetch_one, agent_id, timeout): agent_id for agent_id in ids}
        for fut in as_completed(futs):
            agent_id = futs[fut]
            try:
                by_id[agent_id] = fut.result()
            except Exception:
                by_id[agent_id] = empty_row(agent_id)
    return [by_id[agent_id] for agent_id in ids]


def format_line(row: Row) -> str:
    return (
        f"id={row.get('id') or ''} "
        f"agentStatus={row.get('agentStatus') or 'unknown'} "
        f"runStatus={row.get('runStatus') or 'none'} "
        f"url={row.get('url') or ''} "
        f"latestRunId={row.get('latestRunId') or ''}"
    )


def collect_ids(raw_ids: list[str]) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for raw in raw_ids:
        for part in raw.split(","):
            agent_id = part.strip()
            if not agent_id or agent_id in seen:
                continue
            seen.add(agent_id)
            ids.append(agent_id)
    return ids


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("ids", nargs="*")
    args = parser.parse_args(argv)
    ids = collect_ids(args.ids)
    if not ids:
        print("Usage: status_fetch.py [--json] AGENT_ID [AGENT_ID...]", file=sys.stderr)
        return 2
    if not api_key():
        print("error: CURSOR_API_KEY is not set", file=sys.stderr)
        return 1
    rows = fetch_many(ids, request_timeout())
    if args.json:
        payload: Any = rows[0] if len(rows) == 1 else rows
        sys.stdout.write(json.dumps(payload) + "\n")
        return 0
    for row in rows:
        sys.stdout.write(format_line(row) + "\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except OSError:
            pass
        raise SystemExit(0)
