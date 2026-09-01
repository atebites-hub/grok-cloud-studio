#!/usr/bin/env python3
"""Occupancy counts from Agent.list + listRuns.

Bounded concurrency, per-call timeout, fail-closed on ERR so capacity beats
do not hang. Existence ACTIVE/IDLE is not liveness. Palemon Linear is Living
Sky (LIV). Never Bot CloudAgent. Never prints API keys.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from typing import Any, Callable

DEFAULT_CONCURRENCY = 8
DEFAULT_TIMEOUT_SEC = 15.0
DEFAULT_DEADLINE_SEC = 30.0
DEFAULT_LIMIT = 100
LIST_RUNS_LIMIT = 20
MEMBERSHIP_NOT_LIVENESS = frozenset({"ACTIVE", "IDLE", ""})


class OccupancyError(RuntimeError):
    """list or listRuns failed; occupancy is unknown (fail closed)."""

    def __init__(self, message: str, reason: str = "err") -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class OccupancySummary:
    running: int
    leftover_active: int
    creating: int
    listed: int


def unwrap_entity(data: Any, key: str) -> Any:
    if isinstance(data, dict) and key in data and "id" not in data:
        inner = data[key]
        if isinstance(inner, dict):
            return inner
    return data


def normalize_run_status(raw: Any) -> str:
    status = str(raw or "").strip()
    if not status or status.upper() == "NONE":
        return "none"
    return status.upper()


def normalize_agent_status(raw: Any) -> str:
    status = str(raw or "").strip()
    return status.upper() if status else ""


def _created_at(run: dict[str, Any]) -> float:
    raw = run.get("createdAt")
    if raw is None:
        raw = run.get("created_at")
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def pick_latest_run(items: list[Any] | None) -> dict[str, Any] | None:
    runs: list[dict[str, Any]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        run = unwrap_entity(item, "run")
        if isinstance(run, dict):
            runs.append(run)
    if not runs:
        return None
    return max(runs, key=_created_at)


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
        f"creating={summary.creating} listed={summary.listed}"
    )


def format_occupancy_err(reason: str, message: str = "") -> str:
    extra = f" {message}" if message else ""
    return f"CLOUD_OCCUPANCY_ERR reason={reason}{extra}".rstrip()


def _agent_id(raw: dict[str, Any]) -> str:
    return str(raw.get("id") or raw.get("agentId") or "").strip()


def _agent_status(raw: dict[str, Any]) -> str:
    return str(raw.get("status") or raw.get("agentStatus") or "")


def map_with_concurrency(
    items: list[Any],
    worker: Callable[[Any], Any],
    *,
    concurrency: int,
    timeout_sec: float,
    deadline_sec: float,
) -> list[Any]:
    """Run worker(item) with a worker cap. Fail-closed on timeout or exception.

    Does not wait for hung workers after timeout (shutdown wait=False) so a
    capacity beat is bounded even when listRuns never returns.
    """
    if not items:
        return []
    workers = max(1, min(int(concurrency), len(items)))
    timeout_sec = max(float(timeout_sec), 0.05)
    deadline_mono = time.monotonic() + max(float(deadline_sec), timeout_sec)
    results: list[Any] = [None] * len(items)
    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        futs = {pool.submit(worker, item): idx for idx, item in enumerate(items)}
        pending = set(futs)
        while pending:
            remaining = deadline_mono - time.monotonic()
            if remaining <= 0:
                raise OccupancyError("occupancy deadline", "deadline")
            wait_for = min(timeout_sec, remaining)
            done, pending = wait(pending, timeout=wait_for, return_when=FIRST_COMPLETED)
            if not done:
                raise OccupancyError("listRuns timeout", "timeout")
            for fut in done:
                idx = futs[fut]
                try:
                    results[idx] = fut.result()
                except OccupancyError:
                    raise
                except Exception as err:
                    raise OccupancyError(str(err) or "listRuns err", "err") from err
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return results


def occupancy_from_agents(
    agents: list[Any],
    fetch_runs: Callable[[str], list[Any]],
    *,
    concurrency: int = DEFAULT_CONCURRENCY,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    deadline_sec: float = DEFAULT_DEADLINE_SEC,
    bot_id: str = "",
) -> OccupancySummary:
    bot = (bot_id or "").strip()
    parsed: list[dict[str, Any]] = []
    for raw in agents or []:
        if not isinstance(raw, dict):
            continue
        row = unwrap_entity(raw, "agent")
        if not isinstance(row, dict):
            row = raw
        agent_id = _agent_id(row)
        if not agent_id:
            continue
        if bot and agent_id == bot:
            continue
        parsed.append(row)

    def worker(row: dict[str, Any]) -> tuple[str, str]:
        agent_id = _agent_id(row)
        items = fetch_runs(agent_id)
        latest = pick_latest_run(items if isinstance(items, list) else [])
        run_status = normalize_run_status(latest.get("status") if latest else None)
        return (_agent_status(row), run_status)

    classified = map_with_concurrency(
        parsed,
        worker,
        concurrency=concurrency,
        timeout_sec=timeout_sec,
        deadline_sec=deadline_sec,
    )
    running = leftover_active = creating = 0
    for agent_status, run_status in classified:
        kind = classify_row(agent_status, run_status)
        if kind == "running":
            running += 1
        elif kind == "creating":
            creating += 1
        elif kind == "leftover_active":
            leftover_active += 1
    return OccupancySummary(
        running=running,
        leftover_active=leftover_active,
        creating=creating,
        listed=len(parsed),
    )


def _env_float(name: str, default: float, *, hi: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    if value <= 0:
        return default
    return min(value, hi)


def _env_int(name: str, default: int, *, lo: int, hi: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    if value <= 0:
        return default
    return min(max(value, lo), hi)


def list_runs_timeout_sec() -> float:
    if (os.environ.get("CLOUD_LIST_RUNS_TIMEOUT_SEC") or "").strip():
        return max(_env_float("CLOUD_LIST_RUNS_TIMEOUT_SEC", DEFAULT_TIMEOUT_SEC, hi=15.0), 0.05)
    if (os.environ.get("CLOUD_CURL_MAX_TIME") or "").strip():
        return max(min(_env_float("CLOUD_CURL_MAX_TIME", DEFAULT_TIMEOUT_SEC, hi=15.0), 15.0), 0.05)
    return DEFAULT_TIMEOUT_SEC


def occupancy_deadline_sec(timeout: float) -> float:
    raw = (os.environ.get("CLOUD_OCCUPANCY_DEADLINE_SEC") or "").strip()
    if not raw:
        return max(DEFAULT_DEADLINE_SEC, timeout)
    try:
        value = float(raw)
    except ValueError:
        return max(DEFAULT_DEADLINE_SEC, timeout)
    if value <= 0:
        return max(DEFAULT_DEADLINE_SEC, timeout)
    return min(value, 120.0)


def _is_timeout_err(err: BaseException) -> bool:
    if isinstance(err, TimeoutError):
        return True
    text = str(err).lower()
    return "timed out" in text or "timeout" in text


def _api_get(path: str, timeout: float) -> dict[str, Any]:
    """JSON object. 404 on listRuns → empty items. Other failures OccupancyError."""
    base = (os.environ.get("CURSOR_API_BASE") or "https://api.cursor.com").rstrip("/")
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
        if err.code == 404 and "/runs" in path:
            return {"items": []}
        raise OccupancyError(f"http={err.code}", "err") from err
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError) as err:
        reason = "timeout" if _is_timeout_err(err) else "err"
        raise OccupancyError("probe failed", reason) from err
    if not isinstance(payload, dict):
        raise OccupancyError("unexpected payload", "err")
    return payload


def fetch_agents(limit: int, timeout: float) -> list[Any]:
    payload = _api_get(f"/v1/agents?limit={limit}", timeout)
    items = payload.get("items") or []
    if not isinstance(items, list):
        raise OccupancyError("unexpected list payload", "err")
    return items


def fetch_list_runs(agent_id: str, timeout: float) -> list[Any]:
    payload = _api_get(f"/v1/agents/{agent_id}/runs?limit={LIST_RUNS_LIMIT}", timeout)
    items = payload.get("items") or payload.get("runs") or []
    if not isinstance(items, list):
        return []
    return items


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Print CLOUD_OCCUPANCY from Agent.list + listRuns (REST analog).",
    )
    parser.add_argument("--limit", default=None, help="Agent.list limit (default 100)")
    args = parser.parse_args(argv)
    raw_limit = (
        args.limit
        or os.environ.get("CLOUD_OCCUPANCY_LIMIT")
        or os.environ.get("CLOUD_LIST_LIMIT")
        or str(DEFAULT_LIMIT)
    )
    try:
        limit = int(raw_limit)
    except ValueError:
        limit = DEFAULT_LIMIT
    if limit <= 0:
        limit = DEFAULT_LIMIT
    timeout = list_runs_timeout_sec()
    concurrency = _env_int("CLOUD_OCCUPANCY_CONCURRENCY", DEFAULT_CONCURRENCY, lo=1, hi=32)
    deadline = occupancy_deadline_sec(timeout)
    bot_id = (os.environ.get("GCS_BOT_AGENT_ID") or "").strip()
    try:
        agents = fetch_agents(limit, timeout)
        summary = occupancy_from_agents(
            agents,
            lambda aid: fetch_list_runs(aid, timeout),
            concurrency=concurrency,
            timeout_sec=timeout,
            deadline_sec=deadline,
            bot_id=bot_id,
        )
    except OccupancyError as err:
        print(format_occupancy_err(err.reason, str(err)), file=sys.stderr)
        return 1
    print(format_occupancy_line(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
