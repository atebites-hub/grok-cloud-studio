#!/usr/bin/env python3
"""Format Cursor Cloud list rows with runStatus (and model when the API exposes it).

Agent `status` stays ACTIVE until archive. Live workers are latest-run
`runStatus=RUNNING`. Leftover ACTIVE + FINISHED shells are not workers.
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
from pathlib import Path
from typing import Any

# Path bootstrap so `python3 scripts/cloud/list_rows.py` and importlib tests
# can load sibling extra_high_model.py. Not an inline import.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
from extra_high_model import extract_model_id, normalize_model_id

_KV_RE = re.compile(r"(\w+)=(\S*)")
LIVE_RUN = "RUNNING"
IN_FLIGHT_RUN = frozenset({"RUNNING", "CREATING"})


def normalize_run_status(status: str | None) -> str:
    text = (status or "").strip()
    if not text:
        return "none"
    upper = text.upper()
    if upper == "NONE":
        return "none"
    return upper


def unwrap_run(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    if "id" not in payload and isinstance(payload.get("run"), dict):
        inner = payload["run"]
        if isinstance(inner, dict):
            return inner
    return payload


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
    git = item.get("git") if isinstance(item.get("git"), dict) else {}
    for branch in git.get("branches") or []:
        if isinstance(branch, dict):
            found = str(branch.get("repoUrl") or "").strip()
            if found:
                urls.append(found)
    return urls


def is_live_worker(row: dict[str, Any]) -> bool:
    """True only for latest-run RUNNING. ACTIVE leftover + FINISHED is not a worker."""
    return normalize_run_status(str(row.get("runStatus") or row.get("run_status") or "")) == LIVE_RUN


def is_in_flight(row: dict[str, Any]) -> bool:
    return normalize_run_status(str(row.get("runStatus") or row.get("run_status") or "")) in IN_FLIGHT_RUN


def fetch_run(
    base: str,
    key: str,
    agent_id: str,
    run_id: str,
    timeout: float,
) -> tuple[str, str]:
    """Return (runStatus, model_id). Missing/failed fetch → ('none', '')."""
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
        return "none", ""
    run = unwrap_run(payload)
    if not isinstance(run, dict):
        return "none", ""
    status = normalize_run_status(str(run.get("status") or ""))
    model = extract_model_id(run) or extract_model_id(payload)
    return status, model


def annotate_list_items(
    items: list[dict[str, Any]],
    *,
    base: str,
    key: str,
    timeout: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        agent_id = str(item.get("id") or "")
        run_id = str(item.get("latestRunId") or "")
        run_status = "none"
        model = extract_model_id(item)
        if agent_id and run_id:
            fetched_status, fetched_model = fetch_run(base, key, agent_id, run_id, timeout)
            run_status = fetched_status
            if fetched_model:
                model = fetched_model
        urls = agent_repo_urls(item)
        rows.append(
            {
                "id": agent_id,
                "status": str(item.get("status") or ""),
                "runStatus": run_status,
                "model": model or "none",
                "name": str(item.get("name") or ""),
                "url": str(item.get("url") or ""),
                "latestRunId": run_id,
                "repo": urls[0] if urls else "",
            }
        )
    return rows


def format_list_row(item: dict[str, Any]) -> str:
    model = str(item.get("model") or "none") or "none"
    parts = [
        f"id={item.get('id') or ''}",
        f"status={item.get('status') or ''}",
        f"runStatus={normalize_run_status(str(item.get('runStatus') or ''))}",
        f"model={model}",
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
        if "id=" not in stripped:
            continue
        fields = {m.group(1): m.group(2) for m in _KV_RE.finditer(stripped)}
        if "id" not in fields:
            continue
        rows.append(
            {
                "id": fields.get("id") or "",
                "status": fields.get("status") or "",
                "runStatus": normalize_run_status(fields.get("runStatus")),
                "model": normalize_model_id(fields.get("model")) or "none",
                "name": fields.get("name") or "",
                "url": fields.get("url") or "",
                "latestRunId": fields.get("latestRunId") or "",
                "repo": fields.get("repo") or "",
            }
        )
    return rows


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    fmt = sub.add_parser("format-list")
    fmt.add_argument("body")
    args = parser.parse_args(argv)
    if args.cmd == "format-list":
        return cmd_format_list(args.body)
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
