#!/usr/bin/env python3
"""Paginated Extra High catalog: GET /v1/agents beyond the API max of 100.

Cloud Agents list pages are newest-first, ``limit`` max 100, and continue via
``nextCursor`` (omitted when the catalog is exhausted). A hive dump of 439
agents is five pages; stopping at 100 undercounts occupancy.

Any page error is fail-closed (``CatalogError`` reason=page). Never treat a
partial catalog as an empty floor. Palemon Linear is Living Sky (LIV).
Never prints API keys. Never Grok Bot as Extra High occupancy.
"""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

API_PAGE_MAX = 100
DEFAULT_MAX_PAGES = 50
DEFAULT_API_BASE = "https://api.cursor.com"

FetchPage = Callable[[str | None, int], dict[str, Any]]


class CatalogError(RuntimeError):
    """A catalog page could not be read; occupancy is unknown (fail closed)."""

    def __init__(self, message: str, reason: str = "page") -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class CatalogResult:
    items: list[Any]
    pages: int

    @property
    def listed(self) -> int:
        return len(self.items)


def next_cursor_of(payload: dict[str, Any] | None) -> str | None:
    """Return the next page cursor, or None when the catalog is exhausted.

    ``nextCursor`` is omitted when there are no more pages — it is not
    returned as JSON null. Treat missing, null, and blank as stop.
    """
    if not isinstance(payload, dict):
        return None
    raw = payload.get("nextCursor")
    if raw is None:
        raw = payload.get("next_cursor")
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def unwrap_entity(data: Any, key: str) -> Any:
    if isinstance(data, dict) and key in data and "id" not in data:
        inner = data[key]
        if isinstance(inner, dict):
            return inner
    return data


def items_from_payload(payload: dict[str, Any]) -> list[Any]:
    items = payload.get("items")
    if items is None and isinstance(payload.get("agents"), list):
        items = payload["agents"]
    if not isinstance(items, list):
        raise CatalogError("unexpected list payload", "page")
    return items


def fetch_catalog(
    fetch_page: FetchPage,
    *,
    page_size: int = API_PAGE_MAX,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> CatalogResult:
    """Walk GET /v1/agents pages until nextCursor is omitted.

    Raises CatalogError(reason=page) on a page failure or if max_pages is
    hit while a cursor remains (incomplete catalog — fail closed).
    """
    limit = page_size if page_size > 0 else API_PAGE_MAX
    if limit > API_PAGE_MAX:
        limit = API_PAGE_MAX
    pages_cap = max_pages if max_pages > 0 else DEFAULT_MAX_PAGES
    collected: list[Any] = []
    seen: set[str] = set()
    cursor: str | None = None
    pages = 0
    while pages < pages_cap:
        payload = fetch_page(cursor, limit)
        if not isinstance(payload, dict):
            raise CatalogError("unexpected list payload", "page")
        pages += 1
        for raw in items_from_payload(payload):
            if not isinstance(raw, dict):
                continue
            row = unwrap_entity(raw, "agent")
            if not isinstance(row, dict):
                row = raw
            agent_id = str(row.get("id") or row.get("agentId") or "").strip()
            if agent_id:
                if agent_id in seen:
                    continue
                seen.add(agent_id)
            collected.append(row if isinstance(row, dict) else raw)
        nxt = next_cursor_of(payload)
        if not nxt:
            return CatalogResult(items=collected, pages=pages)
        cursor = nxt
    raise CatalogError("catalog truncated: max pages", "page")


def _request_timeout() -> float:
    try:
        raw = float(os.environ.get("CLOUD_CURL_MAX_TIME") or "120")
    except ValueError:
        raw = 120.0
    return min(max(raw, 1.0), 15.0)


def _is_timeout_err(err: BaseException) -> bool:
    if isinstance(err, TimeoutError):
        return True
    text = str(err).lower()
    return "timed out" in text or "timeout" in text


def catalog_path(*, limit: int, cursor: str | None) -> str:
    params: dict[str, str] = {"limit": str(limit)}
    if cursor:
        params["cursor"] = cursor
    return "/v1/agents?" + urllib.parse.urlencode(params)


def api_get_page(path: str, timeout: float) -> dict[str, Any]:
    """JSON object for one catalog page. Fail-closed CatalogError on errors."""
    base = (os.environ.get("CURSOR_API_BASE") or DEFAULT_API_BASE).rstrip("/")
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
        raise CatalogError(f"http={err.code}", "page") from err
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError) as err:
        reason = "page"
        extra = "timeout" if _is_timeout_err(err) else "probe failed"
        raise CatalogError(extra, reason) from err
    if not isinstance(payload, dict):
        raise CatalogError("unexpected payload", "page")
    return payload


def max_pages_from_env() -> int:
    raw = (os.environ.get("CLOUD_OCCUPANCY_MAX_PAGES") or "").strip()
    if not raw:
        return DEFAULT_MAX_PAGES
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MAX_PAGES
    if value <= 0:
        return DEFAULT_MAX_PAGES
    return min(value, 200)


def fetch_catalog_from_api(
    *,
    page_size: int = API_PAGE_MAX,
    max_pages: int | None = None,
    timeout: float | None = None,
) -> CatalogResult:
    wait = _request_timeout() if timeout is None else timeout
    cap = max_pages_from_env() if max_pages is None else max_pages

    def fetch_page(cursor: str | None, limit: int) -> dict[str, Any]:
        return api_get_page(catalog_path(limit=limit, cursor=cursor), wait)

    return fetch_catalog(fetch_page, page_size=page_size, max_pages=cap)
