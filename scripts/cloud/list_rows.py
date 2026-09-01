#!/usr/bin/env python3
"""Format Cursor Cloud list compact rows with latest-run runStatus and prUrl.

Agent `status` stays ACTIVE until archive. Capacity is the latest run
(`RUNNING` vs `FINISHED`). Fetch latest runs in parallel so Directors do
not N-serial `status.sh`. Missing/404 run → runStatus=none prUrl=none.
"""
from __future__ import annotations

import base64
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


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


def pick_pr_url(run: dict[str, Any] | None) -> str:
    if not isinstance(run, dict):
        return "none"
    git = run.get("git") if isinstance(run.get("git"), dict) else {}
    for branch in git.get("branches") or []:
        if not isinstance(branch, dict):
            continue
        url = str(branch.get("prUrl") or branch.get("pr_url") or "").strip()
        if url:
            return url
    top = str(run.get("prUrl") or run.get("pr_url") or "").strip()
    return top or "none"


def _api_base() -> str:
    return (os.environ.get("CURSOR_API_BASE") or "https://api.cursor.com").rstrip("/")


def _list_timeout() -> float:
    try:
        raw = float(os.environ.get("CLOUD_CURL_MAX_TIME") or "120")
    except ValueError:
        raw = 120.0
    return max(1.0, raw)


def fetch_run(
    base: str,
    key: str,
    agent_id: str,
    run_id: str,
    timeout: float,
) -> tuple[str, str]:
    """Return (runStatus, prUrl). Missing/failed fetch → ('none', 'none')."""
    url = f"{base}/v1/agents/{agent_id}/runs/{run_id}"
    token = base64.b64encode(f"{key}:".encode("utf-8")).decode("ascii")
    req = Request(
        url,
        headers={"Accept": "application/json", "Authorization": f"Basic {token}"},
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
        return "none", "none"
    run = unwrap_run(payload)
    if not isinstance(run, dict):
        return "none", "none"
    return normalize_run_status(str(run.get("status") or "")), pick_pr_url(run)


def _row_from_item(
    item: dict[str, Any],
    *,
    base: str,
    key: str,
    timeout: float,
) -> dict[str, str]:
    agent_id = str(item.get("id") or "")
    run_id = str(item.get("latestRunId") or "")
    run_status = "none"
    pr_url = "none"
    if agent_id and run_id:
        run_status, pr_url = fetch_run(base, key, agent_id, run_id, timeout)
    return {
        "id": agent_id,
        "status": str(item.get("status") or ""),
        "runStatus": run_status,
        "prUrl": pr_url or "none",
        "name": str(item.get("name") or ""),
        "url": str(item.get("url") or ""),
        "latestRunId": run_id,
    }


def annotate_list_items(
    items: list[dict[str, Any]],
    *,
    base: str,
    key: str,
    timeout: float,
) -> list[dict[str, str]]:
    """Attach latest-run runStatus/prUrl. Fetches /runs/ in parallel."""
    if not items:
        return []
    workers = min(32, len(items))

    def _one(item: dict[str, Any]) -> dict[str, str]:
        return _row_from_item(item, base=base, key=key, timeout=timeout)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(_one, items))


def format_list_row(item: dict[str, str]) -> str:
    pr = str(item.get("prUrl") or "none") or "none"
    return " ".join(
        [
            f"id={item.get('id') or ''}",
            f"status={item.get('status') or ''}",
            f"runStatus={normalize_run_status(str(item.get('runStatus') or ''))}",
            f"prUrl={pr}",
            f"name={item.get('name') or ''}",
            f"url={item.get('url') or ''}",
            f"latestRunId={item.get('latestRunId') or ''}",
        ]
    )


def format_list_body(body_path: str) -> int:
    with open(body_path, encoding="utf-8") as fh:
        data = json.load(fh)
    raw_items = data.get("items") or []
    items = [i for i in raw_items if isinstance(i, dict)]
    rows = annotate_list_items(
        items,
        base=_api_base(),
        key=os.environ.get("CURSOR_API_KEY") or "",
        timeout=_list_timeout(),
    )
    for row in rows:
        sys.stdout.write(format_list_row(row) + "\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help"}:
        sys.stderr.write("usage: list_rows.py LIST_BODY.json\n")
        return 0 if args and args[0] in {"-h", "--help"} else 2
    return format_list_body(args[0])


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except OSError:
            pass
        raise SystemExit(0)
