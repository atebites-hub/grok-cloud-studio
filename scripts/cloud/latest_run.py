"""Resolve the latest Extra High run for wait-notify / FLEET_DONE.

Leftover FINISHED is not terminal while a newer run is CREATING or RUNNING.
GET /v1/agents/{id}/runs (collection) is the source of latest, not a pinned
leftover run id or a stale agent latestRunId.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

IN_FLIGHT = frozenset({"CREATING", "RUNNING"})
TERMINAL = frozenset({"FINISHED", "ERROR", "CANCELLED", "EXPIRED"})


def run_status(run: dict[str, Any] | None) -> str:
    if not isinstance(run, dict):
        return ""
    return str(run.get("status") or run.get("runStatus") or "").strip().upper()


def unwrap_entity(data: Any, key: str) -> Any:
    if isinstance(data, dict) and key in data and "id" not in data:
        inner = data[key]
        if isinstance(inner, dict):
            return inner
    return data


def unwrap_runs(payload: Any) -> list[dict[str, Any]]:
    """Extract run dicts from GET /v1/agents/{id}/runs."""
    if isinstance(payload, list):
        items: Any = payload
    elif isinstance(payload, dict):
        items = payload.get("items") or payload.get("runs") or []
        if not items and payload.get("id") and (
            "status" in payload or "runStatus" in payload
        ):
            items = [payload]
    else:
        items = []
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        run = unwrap_entity(item, "run")
        if isinstance(run, dict) and (run.get("id") or run.get("status") or run.get("runStatus")):
            out.append(run)
    return out


def created_at_ms(run: dict[str, Any]) -> int:
    for key in ("createdAtMs", "created_at_ms"):
        val = run.get(key)
        if isinstance(val, (int, float)) and val > 0:
            return int(val)
    for key in ("createdAt", "created_at"):
        val = run.get(key)
        if isinstance(val, (int, float)):
            num = int(val)
            return num if num > 1_000_000_000_000 else num * 1000
        if isinstance(val, str) and val.strip():
            raw = val.strip().replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(raw)
            except ValueError:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
    return 0


def pick_latest_run(runs: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not runs:
        return None
    indexed = list(enumerate(runs))
    indexed.sort(key=lambda pair: (created_at_ms(pair[1]), pair[0]))
    return indexed[-1][1]


def waiter_observe(
    runs: list[dict[str, Any]],
    pinned: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Run wait-notify should treat as current.

    In-flight CREATING/RUNNING always wins over leftover FINISHED, including
    when --run / latestRunId still names the leftover.
    """
    combined: list[dict[str, Any]] = list(runs)
    if isinstance(pinned, dict):
        pid = str(pinned.get("id") or "")
        if pid and not any(str(row.get("id") or "") == pid for row in combined):
            combined.append(pinned)
    in_flight = [row for row in combined if run_status(row) in IN_FLIGHT]
    if in_flight:
        return pick_latest_run(in_flight)
    return pick_latest_run(combined)


def may_fleet_done(run: dict[str, Any] | None) -> bool:
    return bool(run) and run_status(run) in TERMINAL
