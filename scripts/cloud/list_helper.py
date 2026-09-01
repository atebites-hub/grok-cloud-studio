#!/usr/bin/env python3
"""Cursor Cloud list helper: print latest-run runStatus, not only agent ACTIVE.

Agent status is durable membership (ACTIVE until archive). Execution state
lives on the latest run. ACTIVE + FINISHED leftovers are not live workers.

Used by plugins/cursor-cloud MCP ``cloud_list``. Does not replace bash
``list.sh`` (that path is a separate change). Never prints API keys.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

IN_FLIGHT = frozenset({"CREATING", "RUNNING"})
DEFAULT_API_BASE = "https://api.cursor.com"


def unwrap(data: Any, key: str) -> Any:
    if isinstance(data, dict) and key in data and "id" not in data:
        inner = data[key]
        if isinstance(inner, dict):
            return inner
    return data


def map_run_status(raw: Any) -> str:
    status = str(raw or "").strip()
    return status.upper() if status else "none"


def format_list_row(agent: dict[str, Any], run_status: str) -> str:
    agent_id = str(agent.get("id") or "")
    agent_status = str(agent.get("status") or "")
    name = str(agent.get("name") or "")
    url = str(agent.get("url") or "")
    run_id = str(agent.get("latestRunId") or "")
    return (
        f"id={agent_id} status={agent_status} runStatus={run_status} "
        f"name={name} url={url} latestRunId={run_id}"
    )


def is_live_worker(_agent_status: str, run_status: str) -> bool:
    """True only when the latest run is in-flight. Agent ACTIVE is not enough."""
    return map_run_status(run_status) in IN_FLIGHT


def _redact(text: str, key: str) -> str:
    if key and text:
        return text.replace(key, "[redacted]")
    return text


def load_api_key() -> str:
    key = (os.environ.get("CURSOR_API_KEY") or "").strip()
    if key:
        return key
    env_path = Path(os.environ.get("CURSOR_AGENT_ENV") or (Path.home() / ".config" / "cursor" / "agent.env"))
    if not env_path.is_file():
        return ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        if name.strip() == "CURSOR_API_KEY":
            return value.strip().strip("'\"")
    return ""


def api_base() -> str:
    return (os.environ.get("CURSOR_API_BASE") or DEFAULT_API_BASE).rstrip("/")


def request_timeout() -> float:
    try:
        raw = float(os.environ.get("CLOUD_CURL_MAX_TIME") or "120")
    except ValueError:
        raw = 120.0
    return min(raw, 15.0)


def api_get(path: str, key: str, timeout: float) -> tuple[dict[str, Any] | None, int]:
    url = f"{api_base()}{path}"
    token = base64.b64encode(f"{key}:".encode("utf-8")).decode("ascii")
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "Authorization": f"Basic {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            code = int(getattr(resp, "status", 200) or 200)
            if isinstance(payload, dict):
                return payload, code
            return None, code
    except urllib.error.HTTPError as exc:
        return None, int(exc.code)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
        return None, 0


def fetch_run_status(agent_id: str, run_id: str, key: str, timeout: float) -> str:
    if not agent_id or not run_id:
        return "none"
    payload, code = api_get(f"/v1/agents/{agent_id}/runs/{run_id}", key, timeout)
    if code != 200 or not payload:
        return "none"
    run = unwrap(payload, "run")
    if not isinstance(run, dict):
        return "none"
    return map_run_status(run.get("status"))


def list_cloud_agents(*, limit: int = 20) -> tuple[str, bool]:
    key = load_api_key()
    if not key:
        return "error: CURSOR_API_KEY is not set", False
    if limit < 1:
        limit = 20
    timeout = request_timeout()
    payload, code = api_get(f"/v1/agents?limit={limit}", key, timeout)
    if code != 200 or not payload:
        return _redact(f"error: list failed http={code or '000'}", key), False
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        return "CLOUD_LIST empty", True
    lines: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        agent = unwrap(item, "agent")
        if not isinstance(agent, dict):
            continue
        agent_id = str(agent.get("id") or "")
        run_id = str(agent.get("latestRunId") or "")
        run_status = fetch_run_status(agent_id, run_id, key, timeout)
        lines.append(format_list_row(agent, run_status))
    text = "\n".join(lines) if lines else "CLOUD_LIST empty"
    return _redact(text, key), True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="List Cursor Cloud agents with latest-run runStatus (RUNNING vs FINISHED)."
    )
    parser.add_argument("limit", nargs="?", default="20")
    parser.add_argument("--limit", dest="limit_flag")
    args = parser.parse_args(argv)
    raw = str(args.limit_flag or args.limit or "20")
    try:
        limit = int(raw)
    except ValueError:
        print("error: limit must be an integer", file=sys.stderr)
        return 2
    text, ok = list_cloud_agents(limit=limit)
    sys.stdout.write(text if text.endswith("\n") else text + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
