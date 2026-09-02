#!/usr/bin/env python3
"""Hive occupancy: Extra High floor is latest-run RUNNING/CREATING.

Agent status=ACTIVE is membership (stays ACTIVE until archive), not occupancy.
Leftover ACTIVE+FINISHED must not count as hive occupancy.

Does not vendor Hermes. Does not restack GCS #47 command-center tools.
Never Bot CloudAgent. Unique remaining vs list occupancy filter #78:
CREATING is occupancy.
"""
from __future__ import annotations

from typing import Iterable

IN_FLIGHT = frozenset({"RUNNING", "CREATING"})


def normalize_run_status(raw: str | None) -> str:
    status = str(raw or "").strip()
    if not status:
        return "none"
    upper = status.upper()
    if upper == "NONE":
        return "none"
    return upper


def is_hive_occupancy(run_status: str | None, agent_status: str = "") -> bool:
    """True only for latest-run RUNNING/CREATING. Agent ACTIVE is ignored."""
    del agent_status
    return normalize_run_status(run_status) in IN_FLIGHT


def include_occupancy_row(agent_status: str, run_status: str) -> bool:
    return is_hive_occupancy(run_status, agent_status=agent_status)


def format_occupancy_row(
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


def parse_list_row(line: str) -> dict[str, str]:
    text = (line or "").strip()
    if not text or text.startswith("CLOUD_"):
        return {}
    fields: dict[str, str] = {}
    for tok in text.split():
        if "=" in tok:
            key, _, value = tok.partition("=")
            fields[key] = value
    return fields


def occupancy_ids_from_list_stdout(stdout: str) -> frozenset[str]:
    ids: set[str] = set()
    for line in (stdout or "").splitlines():
        fields = parse_list_row(line)
        agent_id = fields.get("id") or ""
        if not agent_id:
            continue
        if include_occupancy_row(fields.get("status") or "", fields.get("runStatus") or ""):
            ids.add(agent_id)
    return frozenset(ids)


def count_occupancy_from_list_stdout(stdout: str) -> int:
    return len(occupancy_ids_from_list_stdout(stdout))


def occupancy_row_lines(lines: Iterable[str]) -> list[str]:
    kept: list[str] = []
    for line in lines:
        text = str(line).rstrip("\n")
        if not text:
            continue
        fields = parse_list_row(text)
        if include_occupancy_row(fields.get("status") or "", fields.get("runStatus") or ""):
            kept.append(text)
    return kept


def occupancy_report(lines: Iterable[str]) -> str:
    """Director floor listing: occupancy rows plus CLOUD_OCCUPANCY n=N."""
    kept = occupancy_row_lines(lines)
    out = [f"CLOUD_OCCUPANCY n={len(kept)}"]
    if not kept:
        out.append("CLOUD_LIST empty")
    else:
        out.extend(kept)
    return "\n".join(out) + "\n"
