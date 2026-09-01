#!/usr/bin/env python3
"""Find a live Extra High with the same --name and runStatus=RUNNING.

LIV-59 anti-twin: leftover ACTIVE+FINISHED shells do not count as twins.
Never Bot CloudAgent (GCS_BOT_AGENT_ID is skipped). Palemon Linear is
Living Sky (LIV).

Exit codes:
  0 — live twin found; stdout is `id=… name=… runStatus=RUNNING`
  1 — no live twin
  2 — list/probe failed or a name-matched Extra High runStatus is unresolved
      (fail closed; do not remint blindly)
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
from typing import Any

FetchRun = Callable[[str, str], str | None]
FetchLatest = Callable[[str], str | None]


class TwinProbeError(RuntimeError):
    """GET /v1/agents (or a name-matched run) could not be read."""


def run_status_upper(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return "none"
    upper = text.upper()
    if upper == "NONE":
        return "none"
    return upper


def is_bot_agent(agent_id: str, bot_id: str) -> bool:
    bot = (bot_id or "").strip()
    return bool(bot) and (agent_id or "").strip() == bot


def unwrap(data: Any, key: str) -> Any:
    if isinstance(data, dict) and key in data and "id" not in data:
        inner = data[key]
        if isinstance(inner, dict):
            return inner
    return data


def _nested_latest_run(raw: dict[str, Any]) -> dict[str, Any] | None:
    latest = raw.get("latestRun") or raw.get("latest_run")
    if isinstance(latest, dict):
        return latest
    return None


def run_id_from_item(raw: dict[str, Any]) -> str:
    run_id = str(raw.get("latestRunId") or raw.get("latest_run_id") or "")
    if run_id:
        return run_id
    latest = _nested_latest_run(raw)
    if latest is None:
        return ""
    return str(latest.get("id") or latest.get("runId") or latest.get("run_id") or "")


def inline_run_status(raw: dict[str, Any]) -> str:
    status = raw.get("runStatus") or raw.get("run_status")
    if status:
        return run_status_upper(str(status))
    latest = _nested_latest_run(raw)
    if latest is None:
        return "none"
    return run_status_upper(str(latest.get("status") or latest.get("runStatus") or ""))


def find_live_name_twin(
    items: list[dict[str, Any]],
    wanted_name: str,
    *,
    bot_id: str = "",
    fetch_run_status: FetchRun,
    fetch_latest_run_id: FetchLatest | None = None,
) -> dict[str, str] | None:
    """Return the first non-Bot agent with this name whose latest run is RUNNING.

    Name-matched Extra Highs whose runStatus cannot be read raise TwinProbeError
    (fail closed; do not remint blindly). Scan every same-name row so an
    unreadable leftover cannot hide a later RUNNING twin.
    """
    wanted = wanted_name or ""
    if not wanted:
        return None
    unresolved = False
    for raw in items:
        if not isinstance(raw, dict):
            continue
        row = unwrap(raw, "agent")
        if not isinstance(row, dict):
            row = raw
        agent_id = str(row.get("id") or row.get("agentId") or "")
        if not agent_id or is_bot_agent(agent_id, bot_id):
            continue
        name = str(row.get("name") or "")
        if name != wanted:
            continue
        inline = inline_run_status(row)
        run_id = run_id_from_item(row)
        if inline == "RUNNING":
            return {
                "id": agent_id,
                "name": name,
                "runStatus": "RUNNING",
                "latestRunId": run_id,
            }
        if not run_id and fetch_latest_run_id is not None:
            try:
                run_id = str(fetch_latest_run_id(agent_id) or "")
            except TwinProbeError:
                unresolved = True
                continue
        if not run_id:
            unresolved = True
            continue
        try:
            fetched = fetch_run_status(agent_id, run_id)
        except TwinProbeError:
            unresolved = True
            continue
        status = run_status_upper(fetched)
        if status == "RUNNING":
            return {
                "id": agent_id,
                "name": name,
                "runStatus": "RUNNING",
                "latestRunId": run_id,
            }
        if status == "none":
            unresolved = True
    if unresolved:
        raise TwinProbeError("name-matched Extra High runStatus unresolved")
    return None


def _list_timeout() -> float:
    try:
        raw = float(os.environ.get("CLOUD_CURL_MAX_TIME") or "120")
    except ValueError:
        raw = 120.0
    return min(max(raw, 1.0), 30.0)


def _api_get(path: str) -> dict[str, Any] | None:
    """JSON object, or None on 404. TwinProbeError on other failures. Never prints keys."""
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
    except urllib.error.HTTPError as err:
        if err.code == 404:
            return None
        raise TwinProbeError(f"http={err.code}") from err
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError) as err:
        raise TwinProbeError("probe failed") from err
    if not isinstance(payload, dict):
        raise TwinProbeError("unexpected payload")
    return payload


def fetch_latest_run_id(agent_id: str) -> str | None:
    payload = _api_get(f"/v1/agents/{agent_id}")
    if payload is None:
        return None
    agent = unwrap(payload, "agent")
    if not isinstance(agent, dict):
        return None
    return run_id_from_item(agent) or None


def fetch_run_status(agent_id: str, run_id: str) -> str | None:
    payload = _api_get(f"/v1/agents/{agent_id}/runs/{run_id}")
    if payload is None:
        return None
    run = unwrap(payload, "run")
    if not isinstance(run, dict):
        return None
    return str(run.get("status") or "")


def load_list_items() -> list[dict[str, Any]]:
    raw_limit = (os.environ.get("CLOUD_LIST_LIMIT") or "50").strip()
    limit = raw_limit if raw_limit.isdigit() else "50"
    payload = _api_get(f"/v1/agents?limit={limit}")
    if payload is None:
        raise TwinProbeError("list not found")
    items = payload.get("items")
    if items is None and isinstance(payload.get("agents"), list):
        items = payload["agents"]
    if not isinstance(items, list):
        raise TwinProbeError("list missing items")
    return [row for row in items if isinstance(row, dict)]


def format_twin(twin: dict[str, str]) -> str:
    return f"id={twin['id']} name={twin['name']} runStatus={twin['runStatus']}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True, help="Extra High --name to guard")
    args = parser.parse_args(argv)
    wanted = args.name
    if not wanted:
        return 1
    try:
        items = load_list_items()
        twin = find_live_name_twin(
            items,
            wanted,
            bot_id=os.environ.get("GCS_BOT_AGENT_ID") or "",
            fetch_run_status=fetch_run_status,
            fetch_latest_run_id=fetch_latest_run_id,
        )
    except TwinProbeError as err:
        print(f"error: name-twin probe failed ({err})", file=sys.stderr)
        return 2
    if twin is None:
        return 1
    sys.stdout.write(format_twin(twin) + "\n")
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
