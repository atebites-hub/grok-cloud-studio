#!/usr/bin/env python3
"""Detect Cursor Cloud follow-up HTTP 409 / agent_busy.

Directors must CLOUD_FOLLOWUP_ERR and must not launch a second unique
--name twin. Distinct from leftover GCS #35 waiter 429 backoff. Does not
remint GCS #49 RUNNING probe refuse. Never Bot CloudAgent.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any


def parse_http_code(value: str | int | None) -> int:
    raw = str(value or "").strip()
    if not raw:
        return 0
    try:
        return int(raw)
    except ValueError:
        return 0


def _walk_agent_busy(value: Any) -> bool:
    if isinstance(value, dict):
        for key, inner in value.items():
            key_l = str(key).lower()
            if key_l in {"code", "error", "type", "reason"} and "agent_busy" in str(
                inner
            ).lower():
                return True
            if _walk_agent_busy(inner):
                return True
        return False
    if isinstance(value, list):
        return any(_walk_agent_busy(item) for item in value)
    if isinstance(value, str) and "agent_busy" in value.lower():
        return True
    return False


def is_busy_conflict(
    *,
    http_code: str | int | None,
    body: Any = None,
    body_text: str | None = None,
) -> bool:
    """True when POST /runs (or SDK send) is HTTP 409 or names agent_busy.

    HTTP 429 is not busy — that is waiter rate-limit, not a twin-launch cue.
    """
    code = parse_http_code(http_code)
    if code == 409:
        return True
    if code == 429:
        return False
    if _walk_agent_busy(body):
        return True
    text = (body_text or "").lower()
    return "agent_busy" in text


def err_line(*, http_code: str | int | None = 409, agent_id: str = "") -> str:
    code = parse_http_code(http_code) or 409
    line = f"CLOUD_FOLLOWUP_ERR http={code} agent_busy=1"
    aid = (agent_id or "").strip()
    if aid:
        line += f" id={aid}"
    return line


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in {"--check", "--emit"}:
        args = args[1:]
    if not args:
        return 2
    http = args[0]
    body_path = args[1] if len(args) > 1 else ""
    payload: Any = None
    text = ""
    if body_path and os.path.isfile(body_path):
        with open(body_path, encoding="utf-8") as fh:
            text = fh.read()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = None
    if is_busy_conflict(http_code=http, body=payload, body_text=text):
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
