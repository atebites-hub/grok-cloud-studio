#!/usr/bin/env python3
"""Fail-closed Extra High model pin: grok-4.6 (dashboard alias cursor-grok-4.6-xhigh).

Create requests always send grok-4.6 / effort=xhigh / fast=false. If the API
exposes a model on the create response and it is not Extra High, callers must
print CLOUD_LAUNCH_ERR and must not count the agent as a worker.
Missing model on the response is allowed — v1 agent/run objects often omit it.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

EXTRA_HIGH_MODEL_ID = "grok-4.6"
EXTRA_HIGH_MODEL_IDS = frozenset({"grok-4.6", "cursor-grok-4.6-xhigh"})


def normalize_model_id(raw: Any) -> str:
    if raw is None:
        return ""
    if isinstance(raw, dict):
        for key in ("id", "name", "originalModelName", "modelId"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, dict):
                nested = normalize_model_id(value)
                if nested:
                    return nested
        return ""
    text = str(raw).strip()
    return text


def extract_model_id(payload: Any) -> str:
    """Return a model id if the create/list/run payload exposes one."""
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload.strip()
    if not isinstance(payload, dict):
        return ""
    for key in ("model", "originalModelName", "modelId", "model_id"):
        if key not in payload:
            continue
        found = normalize_model_id(payload.get(key))
        if found:
            return found
    for nested_key in ("agent", "run"):
        nested = payload.get(nested_key)
        if isinstance(nested, dict):
            found = extract_model_id(nested)
            if found:
                return found
    return ""


def is_extra_high_model(model_id: Any) -> bool:
    """True when the API omitted the model, or when it is grok-4.6 Extra High."""
    text = normalize_model_id(model_id)
    if not text:
        return True
    return text.lower() in EXTRA_HIGH_MODEL_IDS


def create_response_ok(payload: Any) -> tuple[bool, str]:
    found = extract_model_id(payload)
    if not found:
        return True, ""
    return is_extra_high_model(found), found


def cmd_check(body_path: str) -> int:
    with open(body_path, encoding="utf-8") as fh:
        payload = json.load(fh)
    ok, found = create_response_ok(payload)
    if ok:
        return 0
    print(f"error: create model is {found}, want grok-4.6", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    check = sub.add_parser("check")
    check.add_argument("body")
    args = parser.parse_args(argv)
    if args.cmd == "check":
        return cmd_check(args.body)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
