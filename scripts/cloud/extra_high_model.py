#!/usr/bin/env python3
"""Fail-closed Extra High model pin: grok-4.6 (dashboard alias cursor-grok-4.6-xhigh).

Create and follow-up requests always send grok-4.6 / effort=xhigh / fast=false.
No CURSOR_CLOUD_MODEL / CURSOR_CLOUD_EFFORT override. If the API exposes a
model on the create or send/run response and it is not Extra High, callers must
print CLOUD_LAUNCH_ERR / CLOUD_FOLLOWUP_ERR and must not count the agent as a
worker. Missing model on the response is allowed — v1 objects often omit it.
"""
from __future__ import annotations

import argparse
import json
import os
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


def extra_high_model_object() -> dict[str, Any]:
    return {
        "id": EXTRA_HIGH_MODEL_ID,
        "params": [
            {"id": "effort", "value": "xhigh"},
            {"id": "fast", "value": "false"},
        ],
    }


def cmd_check(body_path: str) -> int:
    with open(body_path, encoding="utf-8") as fh:
        payload = json.load(fh)
    ok, found = create_response_ok(payload)
    if ok:
        return 0
    print(f"error: create model is {found}, want grok-4.6", file=sys.stderr)
    return 2


def cmd_followup_body() -> int:
    prompt = os.environ.get("CLOUD_PROMPT_TEXT") or ""
    print(json.dumps({"prompt": {"text": prompt}, "model": extra_high_model_object()}))
    return 0


def cmd_launch_body() -> int:
    prompt = os.environ.get("CLOUD_PROMPT_TEXT") or ""
    name = os.environ.get("CLOUD_AGENT_NAME") or ""
    repo = os.environ.get("GCS_CLOUD_REPO") or ""
    ref = os.environ.get("GCS_CLOUD_REF") or "main"
    if not repo:
        print("GCS_CLOUD_REPO missing", file=sys.stderr)
        return 2
    body: dict[str, Any] = {
        "prompt": {"text": prompt},
        "model": extra_high_model_object(),
        "repos": [{"url": repo, "startingRef": ref}],
        "autoCreatePR": True,
    }
    if name:
        body["name"] = name
    print(json.dumps(body))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    check = sub.add_parser("check")
    check.add_argument("body")
    sub.add_parser("followup-body")
    sub.add_parser("launch-body")
    args = parser.parse_args(argv)
    if args.cmd == "check":
        return cmd_check(args.body)
    if args.cmd == "followup-body":
        return cmd_followup_body()
    if args.cmd == "launch-body":
        return cmd_launch_body()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
